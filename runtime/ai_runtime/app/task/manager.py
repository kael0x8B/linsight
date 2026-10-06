import asyncio
import base64
import contextlib
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from PIL import Image
from pydantic import SecretStr

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.plate_input import package_plate_input, plate_capabilities
from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.event.evidence import EvidenceBuffer
from ai_runtime.app.event.store import OfflineEventStore, PendingDeliveryBatch
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.model.deployed import DeployedModelRegistry
from ai_runtime.app.model.pool import ModelLease, ModelPool
from ai_runtime.app.rule.contracts import RuleTransition
from ai_runtime.app.rule.engine import RuleEngine
from ai_runtime.app.stream.frames import CapturedFrame
from ai_runtime.app.task.contracts import (
    TaskGlobalSettings,
    TaskInferenceParameters,
    TaskOverlayFrame,
    TaskStartRequest,
    TaskStatus,
)
from ai_runtime.app.task.inference import TaskFrameInference


class StreamProcess(Protocol):
    returncode: int | None
    stdout: asyncio.StreamReader | None

    async def wait(self) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


@dataclass
class SharedCameraStream:
    camera_id: int
    source_url: SecretStr
    settings: RuntimeSettings
    subscribers: dict[int, asyncio.Queue[CapturedFrame]] = field(default_factory=dict)
    diagnostic_id: str = field(default_factory=lambda: str(uuid4()))
    _runner: asyncio.Task[None] | None = None
    _process: StreamProcess | None = None
    _started: asyncio.Event = field(default_factory=asyncio.Event)
    _start_error: Exception | None = None
    _closing: bool = False
    frames: int = 0
    dropped_frames: int = 0
    reconnects: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)
    _process_starts: int = 0
    decode_backend: str = "SOFTWARE_FFMPEG"
    hardware_decode_failures: int = 0

    async def start(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run(), name=f"task-camera-{self.camera_id}")
        await asyncio.wait_for(self._started.wait(), self.settings.task_startup_seconds)
        if self._start_error is not None:
            raise RuntimeError("camera stream failed to start") from self._start_error

    async def stop(self) -> None:
        self._closing = True
        await self._stop_process()
        if self._runner is not None:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner

    async def _run(self) -> None:
        retry_seconds = 0.5
        while not self._closing:
            try:
                if self._process_starts:
                    self.reconnects += 1
                self._process_starts += 1
                self._process = await self._create_process()
                self._started.set()
                assert self._process.stdout is not None
                await self._read_jpeg_frames(self._process.stdout)
                await self._process.wait()
            except (FileNotFoundError, OSError) as error:
                self._start_error = error
                self._started.set()
            finally:
                self._process = None
            if self._closing or not self.subscribers:
                return
            await asyncio.sleep(retry_seconds)
            retry_seconds = min(retry_seconds * 2, 8.0)

    async def _read_jpeg_frames(self, stdout: asyncio.StreamReader) -> None:
        buffer = bytearray()
        while not self._closing:
            chunk = await stdout.read(64 * 1024)
            if not chunk:
                return
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                if start < 0 or end < 0:
                    if len(buffer) > 8 * 1024 * 1024:
                        buffer.clear()
                    break
                frame = CapturedFrame(bytes(buffer[start : end + 2]), time.time_ns() // 1_000_000)
                del buffer[: end + 2]
                self.frames += 1
                for queue in tuple(self.subscribers.values()):
                    if queue.full():
                        with contextlib.suppress(asyncio.QueueEmpty):
                            queue.get_nowait()
                        self.dropped_frames += 1
                    queue.put_nowait(frame)

    async def _create_process(self) -> StreamProcess:
        source = self.source_url.get_secret_value()
        args = [self.settings.ffmpeg_binary, "-nostdin", "-hide_banner", "-loglevel", "error"]
        if source.lower().startswith("rtsp://"):
            args.extend(["-rtsp_transport", "tcp"])
        args.extend(
            [
                "-i",
                source,
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"fps={self.settings.task_capture_fps}",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                # Keep inference detail stable: default MJPEG rate control progressively
                # raises quantization on a continuous stream, even at VGA resolution.
                "-q:v",
                str(self.settings.task_capture_jpeg_quality),
                "pipe:1",
            ]
        )
        return await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def _stop_process(self) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), 3.0)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()


class TaskRunner:
    def __init__(
        self,
        request: TaskStartRequest,
        queue: asyncio.Queue[CapturedFrame],
        stream: SharedCameraStream,
        model_pool: ModelPool,
        settings: RuntimeSettings,
        event_store: OfflineEventStore,
        model_lease: ModelLease = (),
    ) -> None:
        self._model_lease = model_lease
        self.request = request
        self.queue = queue
        self.stream = stream
        self.model_pool = model_pool
        self.frame_path = settings.runtime_data_root / "tasks" / request.run_id / "latest.jpg"
        self.diagnostic_id = str(uuid4())
        self.status = "RUNNING"
        self.error_code: str | None = None
        self.error_message: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._started_monotonic = time.monotonic()
        self._last_inference_monotonic = 0.0
        self._next_inference_pts: float | None = None
        self._inference_stream_id: str | None = None
        self._analyzed_frames = 0
        self._inference_millis = 0
        self._preprocess_millis = 0
        self._postprocess_millis = 0
        self._total_millis = 0
        self._execution_devices: list[str] = []
        self._model_timings: list[dict] = []
        self._preprocess_samples: deque[int] = deque(maxlen=512)
        self._inference_samples: deque[int] = deque(maxlen=512)
        self._postprocess_samples: deque[int] = deque(maxlen=512)
        self._total_samples: deque[int] = deque(maxlen=512)
        self._capture_to_result_samples: deque[int] = deque(maxlen=512)
        self._decode_samples: deque[int] = deque(maxlen=512)
        self._plate_package = package_plate_input(request.pipeline) is not None
        plate_tracking = "ocr.license-plate" in plate_capabilities(request.pipeline).values()
        self._tracker = IoUTracker(
            motion_classes=frozenset({"license_plate"}) if plate_tracking else frozenset(),
            stationary_reacquire_millis=4000 if plate_tracking else 1500,
        )
        self._postprocessor = CapabilityPostprocessor(request.pipeline, request.parameters)
        descriptor = request.pipeline.get("algorithmPackage")
        self._package = (
            PackageRunner(
                settings.runtime_data_root,
                descriptor,
                request.parameters.algorithm,
                request.model_bindings,
                model_pool,
            )
            if descriptor
            else None
        )
        self._rule_engine = (
            RuleEngine(
                request.task_id, request.camera_id, request.rule,
                identity_deduplication=plate_tracking,
            )
            if request.rule is not None
            else None
        )
        self._rule_transitions: asyncio.Queue[RuleTransition] = asyncio.Queue(maxsize=100)
        self._confirmed_events = 0
        self._latest_overlay: TaskOverlayFrame | None = None
        self._last_overlay_image_stamp: tuple[str, int] | None = None
        self._last_rule_state = "DISABLED" if request.rule is None else "IDLE"
        self._evidence = EvidenceBuffer(
            request=request,
            store=event_store,
            root=settings.runtime_data_root,
            ffmpeg_binary=settings.ffmpeg_binary,
            pre_seconds=settings.evidence_pre_seconds,
            post_seconds=settings.evidence_post_seconds,
            fps=settings.evidence_video_fps,
        )

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"ai-task-{self.request.task_id}")

    async def release_models(self) -> None:
        lease, self._model_lease = self._model_lease, ()
        if lease:
            await self.model_pool.release(lease)

    async def stop(self) -> None:
        self.status = "STOPPED"
        try:
            if self._task is not None:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            await self._evidence.close()
        finally:
            await self.release_models()

    async def _run(self) -> None:
        try:
            if self._package:
                await self._package.start()
            self.frame_path.parent.mkdir(parents=True, exist_ok=True)
            while True:
                interval = 1.0 / self.request.parameters.sample_fps
                captured = await self.queue.get()
                frame = captured.data
                now = time.monotonic()
                timestamp_millis = captured.timestamp_millis
                if (captured.stream_id and self._inference_stream_id
                        and captured.stream_id != self._inference_stream_id):
                    self._tracker.reset()
                if self._rule_engine is not None:
                    self._rule_engine.max_observation_gap_millis = round(
                        max(5, interval * 3) * 1000
                    )
                    if (
                        captured.stream_id
                        and self._inference_stream_id
                        and captured.stream_id != self._inference_stream_id
                    ):
                        self._rule_engine.interrupt_observation()
                await self._evidence.observe_frame(frame, timestamp_millis)
                if captured.source_pts is not None and captured.stream_id:
                    if self._inference_stream_id != captured.stream_id:
                        self._inference_stream_id = captured.stream_id
                        self._next_inference_pts = None
                    if (
                        self._next_inference_pts is not None
                        and captured.source_pts < self._next_inference_pts
                    ):
                        continue
                    self._next_inference_pts = max(
                        (self._next_inference_pts or captured.source_pts) + interval * 90_000,
                        captured.source_pts + 1,
                    )
                elif now - self._last_inference_monotonic < interval:
                    continue
                self._last_inference_monotonic = now
                processing_started = time.perf_counter()
                await asyncio.to_thread(self.frame_path.write_bytes, frame)
                results, merged_objects = await self._infer_frame(captured.image)
                self._execution_devices = sorted({result.device for result in results})
                self._model_timings = [
                    {
                        "backend": result.backend,
                        "device": result.device,
                        "preprocessMillis": result.preprocess_millis,
                        "inferenceMillis": result.inference_millis,
                        "postprocessMillis": result.postprocess_millis,
                    }
                    for result in results
                ]
                if self._package:
                    if self._plate_package:
                        merged_objects = self._tracker.update(merged_objects, timestamp_millis)
                    with Image.open(self.frame_path) as package_image:
                        normalized_objects = await self._package.run(
                            merged_objects,
                            package_image.convert("RGB"),
                            timestamp_millis,
                            self.request.parameters,
                            self.request.algorithm_resources,
                        )
                else:
                    normalized_objects = self._postprocessor.before_tracking(merged_objects)
                tracked_objects = (
                    normalized_objects if self._plate_package
                    else self._tracker.update(normalized_objects, timestamp_millis)
                )
                processed_objects = (
                    tracked_objects
                    if self._package
                    else self._postprocessor.after_tracking(tracked_objects, timestamp_millis)
                )
                self._latest_overlay = TaskOverlayFrame(
                    taskId=self.request.task_id,
                    runId=self.request.run_id,
                    cameraId=self.request.camera_id,
                    frameId=f"{self.request.run_id}:{self._analyzed_frames + 1}",
                    timestamp=datetime.fromtimestamp(timestamp_millis / 1_000, tz=UTC),
                    sourceWidth=results[0].source_width,
                    sourceHeight=results[0].source_height,
                    streamId=captured.stream_id,
                    sourcePts=captured.source_pts,
                    frameKey=captured.frame_key,
                    objects=processed_objects,
                    # Video already carries every image on the stamped timeline.
                    # Keep occasional same-frame diagnostic JPEGs, all result metadata,
                    # and every legacy image when no video timestamp is available.
                    imageBase64=self._overlay_image(captured),
                )
                self._capture_to_result_samples.append(
                    max(0, time.time_ns() // 1_000_000 - timestamp_millis)
                )
                if captured.decode_millis is not None:
                    self._decode_samples.append(round(captured.decode_millis))
                if self._rule_engine is not None:
                    if self._package and not self._package.observation_valid:
                        self._rule_engine.interrupt_observation()
                        self._last_rule_state = "OBSERVATION_UNKNOWN"
                        transitions = []
                    else:
                        candidates = (
                            [
                                obj
                                for obj in processed_objects
                                if obj.attributes.get("eventCandidate") is True
                            ]
                            if self._package and not self._plate_package
                            else self._postprocessor.rule_observations(
                                processed_objects, timestamp_millis
                            )
                        )
                        transitions = self._rule_engine.evaluate(candidates, timestamp_millis)
                    for transition in transitions:
                        self._last_rule_state = transition.state
                        if transition.state == "ALARM":
                            self._confirmed_events += 1
                            await self._evidence.start(transition)
                        elif transition.state in {"RECOVERED", "CLOSED"}:
                            self._evidence.enqueue_transition(transition)
                        if self._rule_transitions.full():
                            with contextlib.suppress(asyncio.QueueEmpty):
                                self._rule_transitions.get_nowait()
                        self._rule_transitions.put_nowait(transition)
                self._analyzed_frames += 1
                self._preprocess_millis = sum(result.preprocess_millis for result in results)
                self._inference_millis = sum(result.inference_millis for result in results)
                self._postprocess_millis = sum(result.postprocess_millis for result in results)
                self._total_millis = max(
                    0, int(round((time.perf_counter() - processing_started) * 1000))
                )
                self._preprocess_samples.append(self._preprocess_millis)
                self._inference_samples.append(self._inference_millis)
                self._postprocess_samples.append(self._postprocess_millis)
                self._total_samples.append(self._total_millis)
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError, KeyError, TimeoutError) as error:
            self.status = "FAILED"
            self.error_code = "TASK_INFERENCE_FAILED"
            self.error_message = (
                "算法包处理超时"
                if isinstance(error, TimeoutError)
                else str(error)[:200]
                if self._package
                else type(error).__name__
            )
        finally:
            if self._package:
                await self._package.close()
            await self.release_models()

    def _overlay_image(self, captured: CapturedFrame) -> str | None:
        if len(captured.data) > 262_144:
            return None
        if captured.stream_id and captured.source_pts is not None:
            previous = self._last_overlay_image_stamp
            if (
                previous is not None
                and previous[0] == captured.stream_id
                and 0 <= captured.source_pts - previous[1] < 180_000
            ):
                return None
            self._last_overlay_image_stamp = (captured.stream_id, captured.source_pts)
        return base64.b64encode(captured.data).decode("ascii")

    async def _infer_frame(self, image: Image.Image | None = None):
        return await TaskFrameInference(self.request, self.model_pool, self.frame_path).infer(image)

    def apply_global_settings(self, settings: TaskGlobalSettings) -> None:
        self.request.parameters.confidence = settings.default_confidence
        self.request.parameters.sample_fps = settings.default_fps
        self._evidence.pre_seconds = settings.record_before_seconds
        self._evidence.post_seconds = settings.record_after_seconds
        self._evidence.fps = settings.default_fps

    def snapshot(self) -> TaskStatus:
        elapsed = max(time.monotonic() - self._started_monotonic, 0.001)
        metrics = {
            "schemaVersion": "1.0",
            "inputFps": round(self.stream.frames / elapsed, 3),
            "analysisFps": round(self._analyzed_frames / elapsed, 3),
            "analyzedFrames": self._analyzed_frames,
            "queueDepth": self.queue.qsize(),
            "droppedFrames": self.stream.dropped_frames,
            "executionBackend": "+".join(self._execution_devices) or "PENDING",
            "modelTimings": self._model_timings,
            "preprocessMillis": self._preprocess_millis,
            "inferenceMillis": self._inference_millis,
            "postprocessMillis": self._postprocess_millis,
            "totalLatencyMillis": self._total_millis,
            "preprocessP50Millis": _percentile(self._preprocess_samples, 0.50),
            "preprocessP95Millis": _percentile(self._preprocess_samples, 0.95),
            "preprocessP99Millis": _percentile(self._preprocess_samples, 0.99),
            "inferenceP50Millis": _percentile(self._inference_samples, 0.50),
            "inferenceP95Millis": _percentile(self._inference_samples, 0.95),
            "inferenceP99Millis": _percentile(self._inference_samples, 0.99),
            "postprocessP50Millis": _percentile(self._postprocess_samples, 0.50),
            "postprocessP95Millis": _percentile(self._postprocess_samples, 0.95),
            "postprocessP99Millis": _percentile(self._postprocess_samples, 0.99),
            "totalLatencyP50Millis": _percentile(self._total_samples, 0.50),
            "totalLatencyP95Millis": _percentile(self._total_samples, 0.95),
            "totalLatencyP99Millis": _percentile(self._total_samples, 0.99),
            "captureToResultMillis": (
                self._capture_to_result_samples[-1] if self._capture_to_result_samples else 0
            ),
            "captureToResultP50Millis": _percentile(self._capture_to_result_samples, 0.50),
            "captureToResultP95Millis": _percentile(self._capture_to_result_samples, 0.95),
            "decodeP50Millis": _percentile(self._decode_samples, 0.50),
            "decodeP95Millis": _percentile(self._decode_samples, 0.95),
            "captureBackend": getattr(self.stream, "decode_backend", "UNKNOWN"),
            "hardwareDecodeFailures": getattr(self.stream, "hardware_decode_failures", 0),
            "ruleState": self._last_rule_state,
            "confirmedEvents": self._confirmed_events,
        }
        return TaskStatus(
            taskId=self.request.task_id,
            runId=self.request.run_id,
            configVersion=self.request.config_version,
            status=self.status,
            diagnosticId=self.diagnostic_id,
            metrics=metrics,
            errorCode=self.error_code,
            errorMessage=self.error_message,
        )

    def drain_rule_transitions(self) -> list[RuleTransition]:
        values: list[RuleTransition] = []
        while not self._rule_transitions.empty():
            values.append(self._rule_transitions.get_nowait())
        return values

    def pop_overlay_frame(self) -> TaskOverlayFrame | None:
        value = self._latest_overlay
        self._latest_overlay = None
        return value


class TaskManager:
    def __init__(
        self,
        settings: RuntimeSettings,
        model_pool: ModelPool,
        stream_factory: Callable[[int, SecretStr, RuntimeSettings], SharedCameraStream]
        | None = None,
    ) -> None:
        self.settings = settings
        self.model_pool = model_pool
        self._stream_factory = stream_factory or SharedCameraStream
        self._streams: dict[int, SharedCameraStream] = {}
        self._tasks: dict[int, TaskRunner] = {}
        self._lock = asyncio.Lock()
        self._local_overlays: dict[int, TaskOverlayFrame] = {}
        self._event_store = OfflineEventStore(
            settings.runtime_data_root / "events" / "delivery.sqlite3", retain_history=True
        )

    async def close(self) -> None:
        async with self._lock:
            runners = list(self._tasks.values())
            streams = list(self._streams.values())
            self._tasks.clear()
            self._streams.clear()
        await asyncio.gather(*(runner.stop() for runner in runners), return_exceptions=True)
        await asyncio.gather(*(stream.stop() for stream in streams), return_exceptions=True)
        self._event_store.close()

    @contextlib.asynccontextmanager
    async def camera_samples(self, camera_id: int, source_url: SecretStr):
        subscriber_id = -uuid4().int
        queue: asyncio.Queue[CapturedFrame] = asyncio.Queue(maxsize=1)
        async with self._lock:
            stream = self._streams.get(camera_id)
            if stream is None:
                stream = self._stream_factory(camera_id, source_url, self.settings)
                self._streams[camera_id] = stream
            elif stream.source_url.get_secret_value() != source_url.get_secret_value():
                raise ValueError("camera source differs from the active stream")
            stream.subscribers[subscriber_id] = queue
        try:
            await stream.start()
            yield queue
        finally:
            async with self._lock:
                stream.subscribers.pop(subscriber_id, None)
                stop_stream = not stream.subscribers
                if stop_stream and self._streams.get(camera_id) is stream:
                    self._streams.pop(camera_id)
            if stop_stream:
                await stream.stop()

    async def start_task(self, request: TaskStartRequest) -> TaskStatus:
        _validate_pipeline(request.pipeline, request.rule is not None, request.parameters)
        async with self._lock:
            existing = self._tasks.get(request.task_id)
            if existing is not None:
                if existing.request.run_id == request.run_id:
                    return existing.snapshot()
                raise ValueError("task already has a different active run")
            stream = self._streams.get(request.camera_id)
            if stream is None:
                stream = self._stream_factory(request.camera_id, request.source_url, self.settings)
            elif stream.source_url.get_secret_value() != request.source_url.get_secret_value():
                raise ValueError("camera source changed while shared stream is active")
            lease = await self.model_pool.acquire(
                request.model_bindings.values(),
                DeployedModelRegistry(self.settings.runtime_data_root),
            )
            try:
                queue: asyncio.Queue[CapturedFrame] = asyncio.Queue(maxsize=1)
                runner = TaskRunner(
                    request, queue, stream, self.model_pool, self.settings, self._event_store, lease
                )
                stream.subscribers[request.task_id] = queue
                self._streams[request.camera_id] = stream
                self._tasks[request.task_id] = runner
            except BaseException:
                await self.model_pool.release(lease)
                raise
        try:
            await stream.start()
            runner.start()
            return runner.snapshot()
        except BaseException:
            await self.stop_task(request.task_id, request.run_id)
            raise

    async def stop_task(self, task_id: int, run_id: str) -> TaskStatus:
        async with self._lock:
            runner = self._tasks.get(task_id)
            if runner is None:
                return TaskStatus(
                    taskId=task_id,
                    runId=run_id,
                    configVersion=1,
                    status="STOPPED",
                    diagnosticId=str(uuid4()),
                    metrics={"schemaVersion": "1.0"},
                )
            if runner.request.run_id != run_id:
                raise ValueError("run id does not match active task")
            self._tasks.pop(task_id)
            stream = runner.stream
            stream.subscribers.pop(task_id, None)
            stop_stream = not stream.subscribers
            if stop_stream:
                self._streams.pop(stream.camera_id, None)
        if stop_stream:
            # Release the analysis subscription while its evidence is finalized.
            # Existing preview owners retain the shared encoded source.
            await asyncio.gather(runner.stop(), stream.stop())
        else:
            await runner.stop()
        return runner.snapshot()

    async def apply_task_settings(self, task_id: int, settings: TaskGlobalSettings) -> TaskStatus:
        async with self._lock:
            runner = self._tasks.get(task_id)
            if runner is None:
                raise KeyError("task is not running")
            runner.apply_global_settings(settings)
            return runner.snapshot()

    def statuses(self) -> list[TaskStatus]:
        return [runner.snapshot() for runner in self._tasks.values()]

    def running_requests(self) -> list[TaskStartRequest]:
        """Read-only task contract snapshots used by node-local admission checks."""
        return [
            runner.request.model_copy(deep=True)
            for runner in self._tasks.values()
            if runner.status == "RUNNING"
        ]

    def drain_rule_transitions(self) -> list[RuleTransition]:
        return [
            transition
            for runner in self._tasks.values()
            for transition in runner.drain_rule_transitions()
        ]

    def drain_overlay_frames(self) -> list[TaskOverlayFrame]:
        for task_id in self._tasks:
            self.latest_overlay(task_id)
        return [
            frame
            for runner in self._tasks.values()
            if (frame := runner.pop_overlay_frame()) is not None
        ]

    @property
    def event_store(self):
        return self._event_store

    def latest_overlay(self, task_id: int):
        runner = self._tasks.get(task_id)
        if runner is None:
            self._local_overlays.pop(task_id, None)
            return None
        frame = runner._latest_overlay
        if frame is not None:
            previous = self._local_overlays.get(task_id)
            if frame.image_base64 is None and previous is not None:
                frame = frame.model_copy(update={"image_base64": previous.image_base64})
            self._local_overlays[task_id] = frame
        return self._local_overlays.get(task_id)

    def pending_event_deliveries(self) -> PendingDeliveryBatch:
        return PendingDeliveryBatch(
            events=self._event_store.list_events(),
            transitions=self._event_store.list_transitions(),
        )

    def acknowledge_event(self, source_event_id: str) -> None:
        self._event_store.acknowledge_event(source_event_id)

    def defer_event(self, source_event_id: str) -> None:
        self._event_store.defer_event(source_event_id)

    def acknowledge_transition(self, delivery_key: str) -> None:
        self._event_store.acknowledge_transition(delivery_key)

    def defer_transition(self, delivery_key: str) -> None:
        self._event_store.defer_transition(delivery_key)

    def dead_letter_transition(self, delivery_key: str, reason: str) -> None:
        self._event_store.dead_letter_transition(delivery_key, reason)

    def observability_metrics(self) -> dict[str, dict]:
        statuses = self.statuses()
        stream_elapsed = {
            camera_id: max(time.monotonic() - stream.started_monotonic, 0.001)
            for camera_id, stream in self._streams.items()
        }

        def metric_values(name: str) -> list[float]:
            return [float(status.metrics.get(name, 0)) for status in statuses]

        return {
            "tasks": {
                "total": len(statuses),
                "running": sum(status.status == "RUNNING" for status in statuses),
                "failed": sum(status.status == "FAILED" for status in statuses),
                "analysisFps": round(
                    sum(float(status.metrics.get("analysisFps", 0)) for status in statuses), 3
                ),
                "queueDepth": sum(int(status.metrics.get("queueDepth", 0)) for status in statuses),
                "preprocessP50Millis": max(metric_values("preprocessP50Millis"), default=0),
                "preprocessP95Millis": max(metric_values("preprocessP95Millis"), default=0),
                "preprocessP99Millis": max(metric_values("preprocessP99Millis"), default=0),
                "inferenceP50Millis": max(metric_values("inferenceP50Millis"), default=0),
                "inferenceP95Millis": max(metric_values("inferenceP95Millis"), default=0),
                "inferenceP99Millis": max(metric_values("inferenceP99Millis"), default=0),
                "postprocessP50Millis": max(metric_values("postprocessP50Millis"), default=0),
                "postprocessP95Millis": max(metric_values("postprocessP95Millis"), default=0),
                "postprocessP99Millis": max(metric_values("postprocessP99Millis"), default=0),
                "totalLatencyP50Millis": max(metric_values("totalLatencyP50Millis"), default=0),
                "totalLatencyP95Millis": max(metric_values("totalLatencyP95Millis"), default=0),
                "totalLatencyP99Millis": max(metric_values("totalLatencyP99Millis"), default=0),
                "confirmedEvents": sum(
                    int(status.metrics.get("confirmedEvents", 0)) for status in statuses
                ),
            },
            "streams": {
                "active": len(self._streams),
                "subscriberCount": sum(
                    len(stream.subscribers) for stream in self._streams.values()
                ),
                "inputFps": round(
                    sum(
                        stream.frames / stream_elapsed[camera_id]
                        for camera_id, stream in self._streams.items()
                    ),
                    3,
                ),
                "frames": sum(stream.frames for stream in self._streams.values()),
                "droppedFrames": sum(stream.dropped_frames for stream in self._streams.values()),
                "reconnects": sum(stream.reconnects for stream in self._streams.values()),
            },
            "delivery": self._event_store.stats(),
        }

    @property
    def active_stream_count(self) -> int:
        return len(self._streams)


def _percentile(values, percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, int((len(ordered) * percentile) - 1e-9)))
    return float(ordered[index])


def _write_detection_crop(
    source_path, destination_path, detected: DetectionObject, padding_ratio: float = 0.05
) -> None:
    from ai_runtime.app.model.plate import rectify_plate

    del padding_ratio  # Rectification owns the validated geometry and bounded fallback border.
    with Image.open(source_path) as source:
        crop, _ = rectify_plate(source.convert("RGB"), detected)
        if destination_path.suffix.lower() == ".png":
            crop.save(destination_path, format="PNG")
        else:
            crop.save(destination_path, format="JPEG", quality=95)


def _validate_pipeline(
    pipeline: dict,
    has_rule: bool = False,
    parameters: TaskInferenceParameters | None = None,
) -> None:
    if pipeline.get("schemaVersion") != "1.0" or not isinstance(pipeline.get("nodes"), list):
        raise ValueError("pipeline schema is invalid")
    acceptance = pipeline.get("acceptance")
    field_validation = (
        parameters is not None
        and parameters.validation_only
        and isinstance(acceptance, dict)
        and acceptance.get("status") in {"PENDING", "BLOCKED_EXTERNAL_ASSETS"}
    )
    if (
        acceptance is not None
        and (not isinstance(acceptance, dict) or acceptance.get("status") != "PASS")
        and not field_validation
    ):
        raise ValueError("pipeline is blocked by production acceptance")
    allowed = {
        "DETECTOR",
        "TRACKER",
        "CLASSIFIER",
        "OCR",
        "RULE",
        "POSE",
        "SEGMENTER",
        "RECOGNIZER",
        "QUALITY",
    }
    capability_pattern = re.compile(r"^[a-z][a-z0-9.-]{1,63}$")
    node_ids: set[str] = set()
    capabilities: dict[str, str] = {}
    for node in pipeline["nodes"]:
        if (
            not isinstance(node, dict)
            or node.get("type") not in allowed
            or not isinstance(node.get("capabilityKey"), str)
            or capability_pattern.fullmatch(node["capabilityKey"]) is None
            or not isinstance(node.get("id"), str)
            or node["id"] in node_ids
        ):
            raise ValueError("pipeline contains an uncontrolled node type")
        node_ids.add(node["id"])
        capabilities[node["id"]] = node["capabilityKey"]
    edges = pipeline.get("edges", [])
    if not isinstance(edges, list):
        raise ValueError("pipeline edges are invalid")
    pairs = {
        (capabilities.get(edge.get("from")), capabilities.get(edge.get("to")))
        for edge in edges
        if isinstance(edge, dict)
    }
    for node in pipeline["nodes"]:
        if "inputMode" in node and (
            node["inputMode"] != "PERSON_CROPS"
            or node["capabilityKey"] != "behavior.phone-call"
            or ("detector.person", "behavior.phone-call") not in pairs
        ):
            raise ValueError("person-crop input requires a person-to-phone-call chain")
    rule_capabilities = {
        capability for capability in capabilities.values() if capability.startswith("rule.")
    }
    if rule_capabilities.intersection(capabilities.values()) and not has_rule:
        raise ValueError("rule pipeline requires a bound rule version")
    if "rule.area-intrusion" in capabilities.values():
        required = {
            ("detector.person", "tracker.iou"),
            ("tracker.iou", "rule.area-intrusion"),
        }
        if not has_rule or not required.issubset(pairs):
            raise ValueError("area intrusion pipeline requires detector, tracker and bound rule")
    required_chains = {
        "ppe.helmet": {
            ("detector.person", "ppe.helmet"),
            ("ppe.helmet", "tracker.iou"),
        },
        "ppe.reflective-vest": {
            ("detector.person", "ppe.reflective-vest"),
            ("ppe.reflective-vest", "tracker.iou"),
        },
        "behavior.smoking": {("behavior.smoking", "tracker.iou")},
        "behavior.phone-call": {("behavior.phone-call", "tracker.iou")},
        "behavior.fall": {("behavior.fall", "tracker.iou")},
        "detector.vehicle": {("detector.vehicle", "tracker.iou")},
        "ocr.license-plate": {
            ("detector.license-plate", "ocr.license-plate"),
            ("ocr.license-plate", "tracker.iou"),
        },
        "rule.person-intrusion": {
            ("detector.person", "tracker.iou"),
            ("tracker.iou", "rule.person-intrusion"),
        },
        "rule.person-absence": {
            ("detector.person", "tracker.iou"),
            ("tracker.iou", "rule.person-absence"),
        },
    }
    detector_capability = next(
        (value for value in capabilities.values() if value.startswith("detector.")),
        "detector.coco",
    )
    for rule_capability in {
        "rule.roi",
        "rule.count",
        "rule.line-crossing",
        "rule.direction",
        "rule.stationary",
        "rule.distance",
    }:
        required_chains[rule_capability] = {
            (detector_capability, "tracker.iou"),
            ("tracker.iou", rule_capability),
        }
    for capability, required in required_chains.items():
        if capability in capabilities.values() and not required.issubset(pairs):
            raise ValueError(f"{capability} pipeline is missing its controlled chain")
    # Behavior nodes emit per-frame candidates.  Alarm confirmation belongs to
    # the bound RuleEngine; legacy task temporal parameters are compatibility
    # fields and therefore must not gate whether the pipeline can start.
