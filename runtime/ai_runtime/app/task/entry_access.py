"""Bounded, explicitly initiated entrance enrollment and 1:N sessions."""

import asyncio
import hashlib
import io
import time
from collections import Counter, OrderedDict, deque
from pathlib import Path
from typing import Literal
from uuid import UUID

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, model_validator

from ai_runtime.app.model.contracts import BoundingBox
from ai_runtime.app.model.face_pair import FaceQualityError


class EntryReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: int = Field(alias="entryId", gt=0)
    path: Path
    sha256: str = Field(pattern="^[0-9a-f]{64}$")


class EntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    session_id: UUID = Field(alias="sessionId")
    mode: Literal["ENROLL", "IDENTIFY"]
    consent_confirmed: StrictBool = Field(alias="consentConfirmed")
    camera_id: int = Field(alias="cameraId", ge=0)
    model_version_id: int = Field(alias="modelVersionId", gt=0)
    source_url: SecretStr | None = Field(default=None, alias="sourceUrl")
    expires_at_millis: int = Field(alias="expiresAtMillis", gt=0)
    references: list[EntryReference] = Field(min_length=1, max_length=256)
    roi: BoundingBox
    similarity_threshold: float = Field(alias="similarityThreshold", ge=0.1, le=1)
    ambiguity_margin: float = Field(alias="ambiguityMargin", ge=0.01, le=0.5)
    temporal_n: int = Field(alias="temporalN", ge=2, le=10)
    temporal_m: int = Field(alias="temporalM", ge=2, le=15)

    @model_validator(mode="after")
    def validate_request(self):
        if not self.consent_confirmed or self.temporal_n > self.temporal_m:
            raise ValueError("invalid consent or temporal window")
        if self.mode == "IDENTIFY" and (self.camera_id <= 0 or self.source_url is None):
            raise ValueError("camera required")
        if self.mode == "ENROLL" and len(self.references) != 1:
            raise ValueError("one enrollment reference required")
        if len({v.entry_id for v in self.references}) != len(self.references):
            raise ValueError("duplicate reference identities")
        r = self.roi
        if r.width <= 0 or r.height <= 0 or r.x + r.width > 1 or r.y + r.height > 1:
            raise ValueError("invalid entrance ROI")
        return self


class EntryAccessRuntime:
    def __init__(self, tasks, pool, root: Path):
        self.tasks, self.pool, self.root = tasks, pool, root
        self._active: dict[UUID, asyncio.Task] = {}
        self._cameras: set[int] = set()
        self._used: dict[UUID, int] = {}
        self._features: OrderedDict[tuple[int, str], tuple] = OrderedDict()

    def cancel(self, session_id: UUID):
        task = self._active.get(session_id)
        if task:
            task.cancel()

    async def run(self, request: EntryRequest) -> dict:
        if (
            sum(p.stat().st_size for p in (self.root / "entry-evidence").rglob("*") if p.is_file())
            > 200 * 1024 * 1024
        ):
            raise ValueError("entrance evidence backlog exceeds disk budget")
        now = time.time_ns() // 1_000_000
        self._used = {key: until for key, until in self._used.items() if until > now}
        if request.session_id in self._used or len(self._used) >= 256:
            raise ValueError("session already used or replay cache full")
        if not now < request.expires_at_millis <= now + 120_000:
            raise ValueError("session expired or exceeds deadline")
        if len(self._active) >= 2 or (
            request.mode == "IDENTIFY" and request.camera_id in self._cameras
        ):
            raise ValueError("entrance busy")
        self._used[request.session_id] = request.expires_at_millis + 120_000
        self._active[request.session_id] = asyncio.current_task()
        if request.mode == "IDENTIFY":
            self._cameras.add(request.camera_id)
        result = {
            "schemaVersion": "1.0",
            "status": "QUALITY_RETRY",
            "reason": "NO_FRESH_FRAME",
            "sampledFrames": 0,
            "matchedFrames": 0,
            "liveness": "NOT_VERIFIED",
            "backend": "UNAVAILABLE",
            "device": "UNAVAILABLE",
            "entryId": None,
        }
        window = deque(maxlen=request.temporal_m)
        frame_times = deque(maxlen=request.temporal_m)
        frames = []
        try:
            remaining = min(120, (request.expires_at_millis - now) / 1000)
            async with asyncio.timeout(remaining):
                features = []
                for reference in request.references:
                    if hashlib.sha256(reference.path.read_bytes()).hexdigest() != reference.sha256:
                        raise ValueError("reference SHA256 mismatch")
                    key = (request.model_version_id, reference.sha256)
                    cached = self._features.get(key)
                    if cached is None:
                        try:
                            with Image.open(reference.path) as image:
                                feature, _, backend, device = await self.pool.extract_face(
                                    request.model_version_id, image
                                )
                        except FaceQualityError as error:
                            result.update(
                                status="REFERENCE_INVALID",
                                reason=str(error),
                                backend=error.backend,
                                device=error.device,
                            )
                            return result
                        cached = (feature, backend, device)
                        self._features[key] = cached
                        while len(self._features) > 256:
                            self._features.popitem(last=False)
                    self._features.move_to_end(key)
                    features.append(cached[0])
                    result.update(backend=cached[1], device=cached[2])
                if request.mode == "ENROLL":
                    result.update(status="REFERENCE_READY", reason=None)
                    return result
                matrix = np.stack(features)
                # Live acquisition is independently bounded to 30 seconds, including cancellation.
                last_stamp = time.time_ns() // 1_000_000
                async with asyncio.timeout(30):
                    async with self.tasks.camera_samples(
                        request.camera_id, request.source_url
                    ) as queue:
                        while result["sampledFrames"] < 90:
                            frame = await queue.get()
                            current = time.time_ns() // 1_000_000
                            if (
                                frame.timestamp_millis <= last_stamp + 200
                                or not 0 <= current - frame.timestamp_millis <= 2000
                            ):
                                continue
                            last_stamp = frame.timestamp_millis
                            if sum(len(item.data) for item in frames) < 24 * 1024 * 1024:
                                frames.append(frame)
                            result["sampledFrames"] += 1
                            try:
                                with Image.open(io.BytesIO(frame.data)) as image:
                                    r = request.roi
                                    crop = image.crop(
                                        (
                                            round(r.x * image.width),
                                            round(r.y * image.height),
                                            round((r.x + r.width) * image.width),
                                            round((r.y + r.height) * image.height),
                                        )
                                    )
                                    feature, face, backend, device = await self.pool.extract_face(
                                        request.model_version_id, crop
                                    )
                                    scores = np.clip(matrix @ feature, -1, 1)
                                    order = np.argsort(scores)[::-1]
                                    best = float(scores[order[0]])
                                    second = float(scores[order[1]]) if len(order) > 1 else -1
                                    identity = (
                                        request.references[int(order[0])].entry_id
                                        if best >= request.similarity_threshold
                                        and best - second >= request.ambiguity_margin
                                        else 0
                                    )
                                    # Ambiguous candidates require a retry.
                                    if (
                                        best >= request.similarity_threshold
                                        and best - second < request.ambiguity_margin
                                    ):
                                        identity = None
                                    window.append(identity)
                                    frame_times.append(frame.timestamp_millis)
                                    result.update(
                                        similarity=best,
                                        backend=backend,
                                        device=device,
                                        reason="AMBIGUOUS_MATCH" if identity is None else None,
                                    )
                                    box = face.box / [
                                        crop.width,
                                        crop.height,
                                        crop.width,
                                        crop.height,
                                    ]
                                    result["bbox"] = {
                                        "x": r.x + float(box[0]) * r.width,
                                        "y": r.y + float(box[1]) * r.height,
                                        "width": float(box[2] - box[0]) * r.width,
                                        "height": float(box[3] - box[1]) * r.height,
                                    }
                            except FaceQualityError as error:
                                window.append(None)
                                frame_times.append(frame.timestamp_millis)
                                result["reason"] = str(error)
                            latest = window[-1]
                            votes = Counter(window)
                            if (
                                len(window) == request.temporal_m
                                and latest is not None
                                and votes[latest] >= request.temporal_n
                            ):
                                result.update(
                                    status="MATCH" if latest else "IDENTITY_UNCONFIRMED",
                                    entryId=latest or None,
                                    matchedFrames=votes[latest],
                                    firstSeenMillis=frame_times[0],
                                    lastSeenMillis=frame.timestamp_millis,
                                    durationMs=frame.timestamp_millis - frame_times[0],
                                    sourceWidth=image.width,
                                    sourceHeight=image.height,
                                )
                                await self._evidence(request.session_id, frames, result)
                                return result
                return result
        except TimeoutError:
            result.update(status="EXPIRED")
            return result
        except asyncio.CancelledError:
            result.update(status="CANCELLED", reason="SESSION_CANCELLED")
            return result
        finally:
            self._active.pop(request.session_id, None)
            if request.mode == "IDENTIFY":
                self._cameras.discard(request.camera_id)

    async def _evidence(self, session_id: UUID, frames: list, result: dict):
        if not frames:
            return
        directory = self.root / "entry-evidence" / str(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        snapshot = directory / "snapshot.jpg"
        snapshot.write_bytes(frames[-1].data)
        result["snapshotPath"] = str(snapshot.resolve())
        # Evidence contains only this explicitly initiated session, not pre-session surveillance.
        video = directory / "session.mp4"
        duration = max(0.2, (frames[-1].timestamp_millis - frames[0].timestamp_millis) / 1000)
        fps = max(1, min(10, (len(frames) - 1) / duration))
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-y",
            str(video),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(process.communicate(b"".join(frame.data for frame in frames)), 8)
            if process.returncode == 0 and video.stat().st_size:
                result["videoPath"] = str(video.resolve())
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
