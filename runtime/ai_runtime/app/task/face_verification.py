"""Short, explicitly initiated camera verification; never a background search."""

import asyncio
import io
import time
from collections import deque
from pathlib import Path
from typing import Literal
from uuid import UUID

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from ai_runtime.app.model.contracts import BoundingBox
from ai_runtime.app.model.face_pair import FaceQualityError


class FaceVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    session_id: UUID = Field(alias="sessionId")
    consent_confirmed: Literal[True] = Field(alias="consentConfirmed")
    camera_id: int = Field(alias="cameraId", gt=0)
    model_version_id: int = Field(alias="modelVersionId", gt=0)
    reference_path: Path = Field(alias="referencePath")
    source_url: SecretStr = Field(alias="sourceUrl")
    expires_at_millis: int = Field(alias="expiresAtMillis", gt=0)
    roi: BoundingBox
    similarity_threshold: float = Field(alias="similarityThreshold", ge=0.1, le=1)
    temporal_n: int = Field(default=3, alias="temporalN", ge=2, le=10)
    temporal_m: int = Field(default=5, alias="temporalM", ge=2, le=15)
    validation_only: Literal[True] = Field(alias="validationOnly")

    @model_validator(mode="after")
    def validate_window(self):
        if self.temporal_n > self.temporal_m:
            raise ValueError("temporalN cannot exceed temporalM")
        if (
            self.roi.width <= 0
            or self.roi.height <= 0
            or self.roi.x + self.roi.width > 1
            or self.roi.y + self.roi.height > 1
        ):
            raise ValueError("ROI must lie within the camera image")
        return self


class FaceVerificationResult(BaseModel):
    session_id: UUID = Field(alias="sessionId")
    status: Literal["MATCH", "NOT_CONFIRMED", "REFERENCE_INVALID", "EXPIRED"]
    reason: str | None = None
    sampled_frames: int = Field(alias="sampledFrames", ge=0)
    matched_frames: int = Field(alias="matchedFrames", ge=0)
    similarity: float | None = None
    backend: str = "ONNX_RUNTIME_FACE_PAIR_SFACE"
    device: str = "CPU"
    liveness: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    validation_only: Literal[True] = Field(default=True, alias="validationOnly")


class FaceVerificationService:
    def __init__(self, tasks, pool) -> None:
        self.tasks = tasks
        self.pool = pool
        self._active_cameras: set[int] = set()
        self._sessions: dict[UUID, tuple[int, FaceVerificationResult | None]] = {}

    async def verify(self, request: FaceVerificationRequest) -> FaceVerificationResult:
        now = time.time_ns() // 1_000_000
        self._sessions = {key: value for key, value in self._sessions.items() if value[0] > now}
        if request.session_id in self._sessions:
            raise ValueError("verification session already used")
        if not now < request.expires_at_millis <= now + 30_000:
            raise ValueError("verification session expired or exceeds 30 seconds")
        if request.camera_id in self._active_cameras or len(self._active_cameras) >= 2:
            raise ValueError("camera verification is busy")
        if len(self._sessions) >= 128:
            raise ValueError("verification session limit reached")
        # No await between checking and reserving: only one request owns a camera.
        self._active_cameras.add(request.camera_id)
        self._sessions[request.session_id] = (request.expires_at_millis + 60_000, None)
        samples = 0
        window: deque[bool] = deque(maxlen=request.temporal_m)
        similarity = None
        reason = "NO_FRESH_FRAME"
        backend, device = "UNAVAILABLE", "UNAVAILABLE"

        def result(status: str) -> FaceVerificationResult:
            return FaceVerificationResult(
                sessionId=request.session_id,
                status=status,
                reason=reason,
                sampledFrames=samples,
                matchedFrames=sum(window),
                similarity=similarity,
                backend=backend,
                device=device,
            )

        try:
            with Image.open(request.reference_path) as reference_file:
                reference = reference_file.convert("RGB")
            try:
                baseline = await self.pool.compare_faces(
                    request.model_version_id, reference, reference
                )
                backend, device = (
                    baseline.get("backend", "UNAVAILABLE"),
                    baseline.get("device", "UNAVAILABLE"),
                )
            except FaceQualityError as error:
                reason = str(error)
                return result("REFERENCE_INVALID")
            remaining = (request.expires_at_millis - time.time_ns() // 1_000_000) / 1000
            if remaining <= 0:
                return result("EXPIRED")
            async with asyncio.timeout(remaining):
                samples_context = self.tasks.camera_samples(request.camera_id, request.source_url)
                async with samples_context as queue:
                    last_stamp = now
                    while True:
                        frame = await queue.get()
                        current = time.time_ns() // 1_000_000
                        if (
                            frame.timestamp_millis < now
                            or frame.timestamp_millis <= last_stamp + 250
                            or not 0 <= current - frame.timestamp_millis <= 2000
                        ):
                            continue
                        last_stamp = frame.timestamp_millis
                        with Image.open(io.BytesIO(frame.data)) as image:
                            roi = request.roi
                            crop = image.crop(
                                (
                                    round(roi.x * image.width),
                                    round(roi.y * image.height),
                                    round((roi.x + roi.width) * image.width),
                                    round((roi.y + roi.height) * image.height),
                                )
                            )
                            try:
                                comparison = await self.pool.compare_faces(
                                    request.model_version_id,
                                    reference,
                                    crop,
                                )
                                similarity = comparison["similarity"]
                                window.append(similarity >= request.similarity_threshold)
                                reason = None if window[-1] else "IDENTITY_NOT_CONFIRMED"
                            except FaceQualityError as error:
                                window.append(False)
                                similarity = None
                                reason = str(error)
                        samples += 1
                        if time.time_ns() // 1_000_000 >= request.expires_at_millis:
                            return result("EXPIRED")
                        if (
                            len(window) == request.temporal_m
                            and window[-1]
                            and sum(window) >= request.temporal_n
                        ):
                            return result("MATCH")
                        if samples >= 30:
                            return result("NOT_CONFIRMED")
        except TimeoutError:
            return result("NOT_CONFIRMED")
        finally:
            self._active_cameras.discard(request.camera_id)
