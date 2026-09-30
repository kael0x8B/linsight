import asyncio
import contextlib
import logging
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from ai_runtime.app.event.store import OfflineEventStore, PendingEvent
from ai_runtime.app.rule.contracts import RuleTransition
from ai_runtime.app.task.contracts import TaskStartRequest

LOGGER = logging.getLogger(__name__)


@dataclass
class _Capture:
    transition: RuleTransition
    payload: dict
    frames: list[tuple[int, bytes]]
    end_millis: int
    directory: Path


@dataclass
class EvidenceBuffer:
    request: TaskStartRequest
    store: OfflineEventStore
    root: Path
    ffmpeg_binary: str
    pre_seconds: float
    post_seconds: float
    fps: float
    _ring: deque[tuple[int, bytes]] = field(default_factory=deque)
    _captures: dict[str, _Capture] = field(default_factory=dict)
    _encoding: asyncio.Queue[_Capture] = field(default_factory=lambda: asyncio.Queue(maxsize=4))
    _encoder: asyncio.Task[None] | None = None

    async def observe_frame(self, frame: bytes, timestamp_millis: int) -> None:
        # Bursty decoding can emit two observations in the same millisecond.
        # Keep the latest image at that instant without inventing elapsed time.
        if self._ring and self._ring[-1][0] == timestamp_millis:
            self._ring[-1] = (timestamp_millis, frame)
        else:
            self._ring.append((timestamp_millis, frame))
        cutoff = timestamp_millis - round(self.pre_seconds * 1000)
        # Keep the last observation before the boundary as well. Slow inference
        # must not shorten the pre-event window by an entire sampling interval.
        while len(self._ring) > 1 and self._ring[1][0] <= cutoff:
            self._ring.popleft()
        completed: list[_Capture] = []
        for capture in self._captures.values():
            if capture.frames and capture.frames[-1][0] == timestamp_millis:
                capture.frames[-1] = (timestamp_millis, frame)
            elif not capture.frames or capture.frames[-1][0] < capture.end_millis:
                capture.frames.append((timestamp_millis, frame))
            if timestamp_millis >= capture.end_millis:
                completed.append(capture)
        for capture in completed:
            if self._encoding.full():
                break
            self._captures.pop(capture.transition.source_event_id, None)
            self._queue_encoding(capture)

    def _queue_encoding(self, capture: _Capture) -> None:
        self._encoding.put_nowait(capture)
        if self._encoder is None:
            self._encoder = asyncio.create_task(self._encode_pending())

    async def _encode_pending(self) -> None:
        while True:
            capture = await self._encoding.get()
            try:
                await asyncio.to_thread(self._finalize, capture)
            finally:
                self._encoding.task_done()

    async def close(self) -> None:
        """Drain evidence before the owning Runtime closes the durable store."""
        if self._captures and self._encoder is None:
            self._encoder = asyncio.create_task(self._encode_pending())
        for capture in list(self._captures.values()):
            await self._encoding.put(capture)
        self._captures.clear()
        await self._encoding.join()
        if self._encoder is not None:
            self._encoder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._encoder
            self._encoder = None

    async def start(self, transition: RuleTransition) -> None:
        if transition.source_event_id in self._captures:
            return
        directory = self.root / "events" / transition.source_event_id
        directory.mkdir(parents=True, exist_ok=True)
        snapshot_path = directory / "snapshot.jpg"
        latest = self._ring[-1][1] if self._ring else b""
        if latest:
            await asyncio.to_thread(snapshot_path.write_bytes, latest)
        payload = self._payload(transition)
        capture = _Capture(
            transition=transition,
            payload=payload,
            frames=list(self._ring),
            end_millis=transition.occurred_at_millis + round(self.post_seconds * 1000),
            directory=directory,
        )
        self.store.upsert_event(
            PendingEvent.model_validate(
                {
                    "sourceEventId": transition.source_event_id,
                    "payload": payload,
                    "snapshotPath": snapshot_path,
                    "finalized": False,
                }
            )
        )
        if self.post_seconds == 0:
            if self._encoding.full():
                self._captures[transition.source_event_id] = capture
            else:
                self._queue_encoding(capture)
        else:
            self._captures[transition.source_event_id] = capture

    def enqueue_transition(self, transition: RuleTransition) -> None:
        self.store.enqueue_transition(
            {
                "sourceEventId": transition.source_event_id,
                "state": transition.state,
                "occurredTime": transition.occurred_at_millis,
            }
        )

    def _payload(self, transition: RuleTransition) -> dict:
        confidence = transition.object_snapshot.get("confidence")
        first_seen = transition.occurred_at_millis - _duration_millis(self.request.rule)
        return {
            "sourceEventId": transition.source_event_id,
            "activityId": transition.activity_id,
            "dedupKey": transition.dedup_key,
            "taskId": self.request.task_id,
            "taskRunId": self.request.run_id,
            "cameraId": self.request.camera_id,
            "algorithmId": self.request.algorithm_id,
            "pipelineVersionId": self.request.pipeline_version_id,
            "modelVersionId": self.request.model_version_id,
            "ruleId": self.request.rule_id,
            "ruleVersionId": self.request.rule_version_id,
            "eventType": transition.event_type,
            "severity": transition.severity,
            "occurredTime": transition.occurred_at_millis,
            "firstSeenTime": first_seen,
            "lastSeenTime": transition.occurred_at_millis,
            "durationMs": transition.occurred_at_millis - first_seen,
            "maxConfidence": confidence,
            "trackId": transition.track_id,
            "objectSnapshot": transition.object_snapshot,
            "taskSnapshot": {
                "taskId": self.request.task_id,
                "runId": self.request.run_id,
                "configVersion": self.request.config_version,
                "cameraId": self.request.camera_id,
                **(
                    {"displayNames": self.request.display_names.model_dump(exclude_none=True)}
                    if self.request.display_names is not None
                    else {}
                ),
                "modelBindings": self.request.model_bindings,
                "parameters": self.request.parameters.model_dump(by_alias=True),
            },
            "pipelineSnapshot": self.request.pipeline,
            "modelSnapshot": {
                "modelVersionId": self.request.model_version_id,
                "modelBindings": self.request.model_bindings,
            },
            "ruleSnapshot": transition.rule_snapshot,
        }

    def _finalize(self, capture: _Capture) -> None:
        video_path: Path | None = capture.directory / "evidence.mp4"
        error: str | None = None
        frames_dir = capture.directory / "frames"
        try:
            frames_dir.mkdir(parents=True, exist_ok=True)
            if not capture.frames:
                raise ValueError("evidence capture has no frames")
            timeline = ["ffconcat version 1.0"]
            for index, (timestamp, content) in enumerate(capture.frames):
                name = f"frame-{index:06d}.jpg"
                (frames_dir / name).write_bytes(content)
                timeline.append(f"file '{name}'")
                if index + 1 < len(capture.frames):
                    elapsed_millis = capture.frames[index + 1][0] - timestamp
                    if elapsed_millis <= 0:
                        raise ValueError("evidence timestamps must increase")
                    timeline.append(f"duration {elapsed_millis / 1000:.3f}")
            manifest = frames_dir / "timeline.ffconcat"
            manifest.write_text("\n".join(timeline) + "\n")
            # Concat can carry the preceding frame duration over at EOF. Hold
            # the final observation for just one encoded output frame instead.
            duration = (capture.frames[-1][0] - capture.frames[0][0]) / 1000 + 1 / self.fps
            subprocess.run(  # noqa: S603 - argv is fixed except configured ffmpeg binary and paths
                [
                    self.ffmpeg_binary,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "1",
                    "-i",
                    str(manifest),
                    # This is the encoded output cadence, not an assumption
                    # about how often the inference loop supplied a frame.
                    "-r",
                    str(self.fps),
                    # FFmpeg 4.4 on deployed RK3588 nodes uses -vsync rather
                    # than the newer -fps_mode option.
                    "-vsync",
                    "cfr",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-threads",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-t",
                    f"{duration:.3f}",
                    str(video_path),
                ],
                check=True,
                timeout=120,
            )
        except (OSError, ValueError, subprocess.SubprocessError) as caught:
            video_path = None
            error = type(caught).__name__
            LOGGER.warning(
                "Evidence video failed taskId=%s sourceEventId=%s errorType=%s frames=%s",
                self.request.task_id,
                capture.transition.source_event_id,
                error,
                len(capture.frames),
            )
        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)
        self.store.finalize_event(capture.transition.source_event_id, video_path, error)


def _duration_millis(rule) -> int:
    if rule is None:
        return 0
    result = 0.0

    def collect(node: dict) -> None:
        nonlocal result
        if node.get("type") == "DURATION":
            result = float(node.get("seconds", 0))
        for child in node.get("children", []):
            collect(child)

    collect(rule.condition)
    return round(result * 1000)
