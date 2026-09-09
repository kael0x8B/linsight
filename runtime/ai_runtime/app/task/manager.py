import asyncio
import base64
import contextlib
import math
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

from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.event.evidence import EvidenceBuffer
from ai_runtime.app.event.store import OfflineEventStore, PendingDeliveryBatch
from ai_runtime.app.model.contracts import DetectionObject, ModelTestParameters, ModelTestRequest
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
        self._tracker = IoUTracker()
        self._postprocessor = CapabilityPostprocessor(request.pipeline, request.parameters)
        self._rule_engine = (
            RuleEngine(request.task_id, request.camera_id, request.rule)
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
            self.frame_path.parent.mkdir(parents=True, exist_ok=True)
            while True:
                interval = 1.0 / self.request.parameters.sample_fps
                captured = await self.queue.get()
                frame = captured.data
                now = time.monotonic()
                timestamp_millis = captured.timestamp_millis
                await self._evidence.observe_frame(frame, timestamp_millis)
                if captured.source_pts is not None and captured.stream_id:
                    if self._inference_stream_id != captured.stream_id:
                        self._inference_stream_id = captured.stream_id
                        self._next_inference_pts = None
                    if (self._next_inference_pts is not None
                            and captured.source_pts < self._next_inference_pts):
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
                    {"backend": result.backend, "device": result.device,
                     "preprocessMillis": result.preprocess_millis,
                     "inferenceMillis": result.inference_millis,
                     "postprocessMillis": result.postprocess_millis}
                    for result in results
                ]
                normalized_objects = self._postprocessor.before_tracking(merged_objects)
                tracked_objects = self._tracker.update(normalized_objects)
                processed_objects = self._postprocessor.after_tracking(
                    tracked_objects, timestamp_millis
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
                self._capture_to_result_samples.append(max(
                    0, time.time_ns() // 1_000_000 - timestamp_millis
                ))
                if captured.decode_millis is not None:
                    self._decode_samples.append(round(captured.decode_millis))
                if self._rule_engine is not None:
                    transitions = self._rule_engine.evaluate(
                        self._postprocessor.event_candidates(processed_objects), timestamp_millis
                    )
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
        except (OSError, ValueError, KeyError) as error:
            self.status = "FAILED"
            self.error_code = "TASK_INFERENCE_FAILED"
            self.error_message = type(error).__name__
        finally:
            await self.release_models()

    def _overlay_image(self, captured: CapturedFrame) -> str | None:
        if len(captured.data) > 262_144:
            return None
        if captured.stream_id and captured.source_pts is not None:
            previous = self._last_overlay_image_stamp
            if (previous is not None and previous[0] == captured.stream_id
                    and 0 <= captured.source_pts - previous[1] < 180_000):
                return None
            self._last_overlay_image_stamp = (captured.stream_id, captured.source_pts)
        return base64.b64encode(captured.data).decode("ascii")

    async def _infer_frame(self, image: Image.Image | None = None):
        parameters = ModelTestParameters(
            schemaVersion="1.0",
            confidence=self.request.parameters.confidence,
            nmsThreshold=self.request.parameters.nms_threshold,
            inputWidth=self.request.parameters.input_width,
            inputHeight=self.request.parameters.input_height,
            outputCoordinates="NORMALIZED_XYWH",
        )
        capabilities = {
            node["id"]: node["capabilityKey"]
            for node in self.request.pipeline.get("nodes", [])
            if isinstance(node, dict) and "id" in node and "capabilityKey" in node
        }
        crop_nodes = [node for node in self.request.pipeline.get("nodes", [])
                      if node.get("inputMode") == "PERSON_CROPS"]
        if crop_nodes:
            return await self._infer_person_behavior(crop_nodes, capabilities, parameters, image)
        ocr_nodes = {
            node_id
            for node_id, capability in capabilities.items()
            if capability == "ocr.license-plate"
        }
        if not ocr_nodes:
            requests = [
                ModelTestRequest(
                    modelVersionId=model_version_id,
                    imagePath=self.frame_path,
                    parameters=parameters,
                )
                for model_version_id in dict.fromkeys(self.request.model_bindings.values())
            ]
            image_argument = {"image": image} if image is not None else {}
            if len(requests) > 1 and all(
                self.model_pool.is_loaded(value.model_version_id, "RKNPU") for value in requests
            ):
                # Independent full-frame NPU models can overlap CPU preparation /
                # output decoding with the other model's device execution. Keep
                # at most two in flight and merge only completed same-frame results.
                results = []
                for offset in range(0, len(requests), 2):
                    batch = await asyncio.gather(*(
                        self.model_pool.test(value, **image_argument)
                        for value in requests[offset:offset + 2]
                    ), return_exceptions=True)
                    for value in batch:
                        if isinstance(value, BaseException):
                            raise value
                        results.append(value)
            else:
                results = [
                    await self.model_pool.test(value, **image_argument) for value in requests
                ]
            return results, [item for result in results for item in result.objects]

        if len(ocr_nodes) != 1:
            raise ValueError("license plate pipeline must contain exactly one OCR node")
        ocr_node = next(iter(ocr_nodes))
        ocr_model_id = self.request.model_bindings.get(ocr_node)
        if ocr_model_id is None:
            raise ValueError("license plate OCR node has no model binding")
        detector_nodes = {
            node_id
            for node_id, capability in capabilities.items()
            if capability in {"detector.license-plate", "detector.vehicle"}
        }
        if not any(capabilities[node_id] == "detector.license-plate" for node_id in detector_nodes):
            raise ValueError("license plate OCR requires a plate detector binding")
        full_frame_results = {}
        for node_id in detector_nodes:
            model_version_id = self.request.model_bindings.get(node_id)
            if model_version_id is None:
                raise ValueError(f"pipeline node has no model binding: {node_id}")
            full_frame_results[node_id] = await self.model_pool.test(
                ModelTestRequest(
                    modelVersionId=model_version_id,
                    imagePath=self.frame_path,
                    parameters=parameters,
                ),
                **({"image": image} if image is not None else {}),
            )
        plate_detections = [
            detected
            for node_id, result in full_frame_results.items()
            if capabilities[node_id] == "detector.license-plate"
            for detected in result.objects
            if detected.class_name == "license_plate"
        ]
        ocr_results = []
        enriched_plates = []
        for index, plate in enumerate(plate_detections):
            crop_path = self.frame_path.parent / f"plate-crop-{index}.jpg"
            try:
                await asyncio.to_thread(_write_detection_crop, self.frame_path, crop_path, plate)
                ocr_result = await self.model_pool.test(
                    ModelTestRequest(
                        modelVersionId=ocr_model_id,
                        imagePath=crop_path,
                        parameters=parameters,
                    )
                )
                ocr_results.append(ocr_result)
                best = max(ocr_result.objects, key=lambda value: value.confidence, default=None)
                attributes = dict(plate.attributes)
                if best is not None:
                    attributes.update(best.attributes)
                enriched_plates.append(plate.model_copy(update={"attributes": attributes}))
            finally:
                crop_path.unlink(missing_ok=True)
        non_plate_objects = [
            detected
            for result in full_frame_results.values()
            for detected in result.objects
            if detected.class_name != "license_plate"
        ]
        results = [*full_frame_results.values(), *ocr_results]
        return results, [*non_plate_objects, *enriched_plates]

    async def _infer_person_behavior(self, crop_nodes, capabilities, parameters, image):
        """Classify each detected person, never a whole multi-person camera frame."""
        if len(crop_nodes) != 1:
            raise ValueError("behavior pipeline requires exactly one person-crop model")
        behavior_node = crop_nodes[0]
        target_class = {"behavior.phone-call": "phone_call"}.get(
            behavior_node.get("capabilityKey")
        )
        detectors = [node_id for node_id, capability in capabilities.items()
                     if capability == "detector.person"]
        if target_class is None or len(detectors) != 1:
            raise ValueError("person-crop behavior requires a behavior and person detector")
        detector_id = self.request.model_bindings[detectors[0]]
        behavior_id = self.request.model_bindings[behavior_node["id"]]
        owned_image = image is None
        source = image if image is not None else Image.open(self.frame_path).convert("RGB")
        try:
            detection = await self.model_pool.test(ModelTestRequest(
                modelVersionId=detector_id, imagePath=self.frame_path, parameters=parameters,
            ), image=source)
            results = [detection]
            objects = []
            # Bounded CPU work on the 2 GB gateway; smaller people remain unclassified.
            people = sorted((obj for obj in detection.objects if obj.class_name == "person"
                             and obj.confidence >= self.request.parameters.person_confidence),
                            key=lambda obj: obj.bbox.width * obj.bbox.height, reverse=True)[:10]
            for person in people:
                box = person.bbox
                left = max(0, int(box.x * source.width))
                top = max(0, int(box.y * source.height))
                right = min(source.width, int((box.x + box.width) * source.width))
                bottom = min(source.height, int((box.y + box.height) * source.height))
                if right - left < 32 or bottom - top < 64:
                    continue
                with source.crop((left, top, right, bottom)) as crop:
                    result = await self.model_pool.test(ModelTestRequest(
                        modelVersionId=behavior_id, imagePath=self.frame_path,
                        parameters=parameters,
                    ), image=crop)
                results.append(result)
                accepted_labels = {target_class}
                if target_class == "phone_call":
                    accepted_labels.add("calling")  # Upstream action model's canonical class.
                candidates = (obj for obj in result.objects if obj.class_name in accepted_labels)
                candidate = max(candidates,
                                key=lambda obj: obj.confidence, default=None)
                if candidate is not None:
                    objects.append(candidate.model_copy(update={
                        "class_name": target_class,
                        "bbox": person.bbox,
                        "attributes": {**candidate.attributes, "behaviorPersonAssociated": True},
                    }))
            return results, objects
        finally:
            if owned_image:
                source.close()

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
    with Image.open(source_path) as source:
        source = source.convert("RGB")
        width, height = source.size
        corner_keys = [(f"corner{index}X", f"corner{index}Y") for index in range(1, 5)]
        has_all_corners = all(
            x_key in detected.attributes and y_key in detected.attributes
            for x_key, y_key in corner_keys
        )
        if has_all_corners:
            corners = [
                (
                    float(detected.attributes[x_key]) * width,
                    float(detected.attributes[y_key]) * height,
                )
                for x_key, y_key in corner_keys
            ]
            if all(math.isfinite(coordinate) for point in corners for coordinate in point):
                top_left, top_right, bottom_right, bottom_left = corners
                target_width = max(
                    math.dist(top_left, top_right),
                    math.dist(bottom_left, bottom_right),
                )
                target_height = max(
                    math.dist(top_left, bottom_left),
                    math.dist(top_right, bottom_right),
                )
                if target_width >= 2 and target_height >= 2:
                    # PIL QUAD consumes source coordinates as UL, LL, LR, UR.
                    quadrilateral = (
                        *top_left,
                        *bottom_left,
                        *bottom_right,
                        *top_right,
                    )
                    source.transform(
                        (round(target_width), round(target_height)),
                        Image.Transform.QUAD,
                        quadrilateral,
                        resample=Image.Resampling.BICUBIC,
                    ).save(destination_path, format="JPEG", quality=95)
                    return
        box = detected.bbox
        pad_x = box.width * padding_ratio
        pad_y = box.height * padding_ratio
        left = max(0, int((box.x - pad_x) * width))
        top = max(0, int((box.y - pad_y) * height))
        right = min(width, int((box.x + box.width + pad_x) * width + 0.999))
        bottom = min(height, int((box.y + box.height + pad_y) * height + 0.999))
        if right <= left or bottom <= top:
            raise ValueError("license plate detector returned an empty crop")
        source.crop((left, top, right, bottom)).save(destination_path, format="JPEG", quality=95)


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
    behavior_capabilities = {
        "behavior.fall",
        "behavior.phone-call",
        "behavior.smoking",
    }
    if behavior_capabilities.intersection(capabilities.values()) and parameters is not None:
        if parameters.temporal_n <= 1 and parameters.duration_seconds <= 0:
            raise ValueError("behavior pipeline cannot enable single-frame confirmation")
