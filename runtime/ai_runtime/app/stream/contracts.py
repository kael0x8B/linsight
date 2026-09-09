from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ProbeStageName(StrEnum):
    DNS = "DNS"
    TCP = "TCP"
    AUTH = "AUTH"
    STREAM = "STREAM"
    KEYFRAME = "KEYFRAME"


class ProbeStageStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StreamProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: int = Field(gt=0)
    protocol: str = Field(pattern="^(RTSP|ONVIF)$")
    host: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._:\[\]-]+$")
    port: int = Field(ge=1, le=65535)
    stream_uri: SecretStr
    username: SecretStr | None = None
    password: SecretStr | None = None
    timeout_seconds: float = Field(default=12.0, ge=3.0, le=30.0)

    @field_validator("stream_uri")
    @classmethod
    def stream_uri_must_not_be_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("stream_uri must not be empty")
        return value


class ProbeStageResult(BaseModel):
    name: ProbeStageName
    status: ProbeStageStatus
    duration_ms: int = Field(ge=0)
    message: str = Field(max_length=200)


class VideoStreamInfo(BaseModel):
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    average_frame_rate: str | None = None


class StreamProbeResult(BaseModel):
    version: str = "v1"
    camera_id: int
    online: bool
    checked_at: datetime
    diagnostic_id: str
    error_code: str | None = None
    error_message: str | None = None
    stages: list[ProbeStageResult]
    stream: VideoStreamInfo | None = None
