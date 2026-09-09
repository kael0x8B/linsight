from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NormalizedBoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def must_stay_inside_frame(self) -> "NormalizedBoundingBox":
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("bbox must stay inside normalized frame")
        return self


class OverlayObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_id: str | None = Field(default=None, alias="trackId", max_length=128)
    class_name: str = Field(alias="class", min_length=1, max_length=128)
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: NormalizedBoundingBox
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class OverlayFrameData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(alias="sessionId", min_length=1, max_length=64)
    camera_id: int = Field(alias="cameraId", gt=0)
    frame_id: str = Field(alias="frameId", min_length=1, max_length=128)
    timestamp: datetime
    source_width: int = Field(alias="sourceWidth", gt=0)
    source_height: int = Field(alias="sourceHeight", gt=0)
    objects: list[OverlayObject] = Field(default_factory=list, max_length=512)
    task_id: int | None = Field(default=None, alias="taskId", gt=0)
    run_id: str | None = Field(default=None, alias="runId", min_length=36, max_length=36)
    image_base64: str | None = Field(default=None, alias="imageBase64", max_length=349_528)


class OverlayEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["preview.overlay.frame"] = "preview.overlay.frame"
    version: Literal["1.0"] = "1.0"
    message_id: str = Field(default_factory=lambda: str(uuid4()), alias="messageId")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="occurredAt")
    trace_id: str | None = Field(default=None, alias="traceId", max_length=64)
    data: OverlayFrameData
