from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, model_validator

from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import RuleAst


class TaskInferenceParameters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    validation_only: StrictBool = Field(default=False, alias="validationOnly")
    confidence: Annotated[float, Field(ge=0.01, le=1.0)] = 0.5
    nms_threshold: Annotated[float, Field(alias="nmsThreshold", ge=0.01, le=1.0)] = 0.5
    input_width: Annotated[int, Field(alias="inputWidth", ge=32, le=2048)] = 640
    input_height: Annotated[int, Field(alias="inputHeight", ge=32, le=2048)] = 640
    sample_fps: Annotated[float, Field(alias="sampleFps", ge=0.1, le=10.0)] = 1.0
    person_confidence: Annotated[float, Field(alias="personConfidence", ge=0.01, le=1.0)] = 0.5
    ppe_confidence: Annotated[float, Field(alias="ppeConfidence", ge=0.01, le=1.0)] = 0.5
    unknown_policy: Literal["NO_ALARM"] = Field(default="NO_ALARM", alias="unknownPolicy")
    temporal_n: Annotated[int, Field(alias="temporalN", ge=1, le=30)] = 2
    temporal_m: Annotated[int, Field(alias="temporalM", ge=1, le=60)] = 3
    duration_seconds: Annotated[float, Field(alias="durationSeconds", ge=0, le=300)] = 1.0
    ocr_vote_frames: Annotated[int, Field(alias="ocrVoteFrames", ge=2, le=30)] = 5
    ocr_min_votes: Annotated[int, Field(alias="ocrMinVotes", ge=2, le=30)] = 3
    class_filter: list[str] = Field(default_factory=list, alias="classFilter", max_length=80)

    @model_validator(mode="after")
    def validate_windows(self) -> "TaskInferenceParameters":
        if self.temporal_n > self.temporal_m:
            raise ValueError("temporalN cannot exceed temporalM")
        if self.ocr_min_votes > self.ocr_vote_frames:
            raise ValueError("ocrMinVotes cannot exceed ocrVoteFrames")
        return self


class TaskStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(alias="taskId", gt=0)
    run_id: str = Field(alias="runId", min_length=36, max_length=36)
    config_version: int = Field(alias="configVersion", gt=0)
    camera_id: int = Field(alias="cameraId", gt=0)
    source_url: SecretStr = Field(alias="sourceUrl")
    algorithm_id: int = Field(alias="algorithmId", gt=0)
    pipeline_version_id: int = Field(alias="pipelineVersionId", gt=0)
    pipeline: dict
    model_version_id: int = Field(alias="modelVersionId", gt=0)
    model_bindings: dict[str, Annotated[int, Field(gt=0)]] = Field(
        default_factory=dict, alias="modelBindings", max_length=20
    )
    rule_id: int | None = Field(default=None, alias="ruleId", gt=0)
    rule_version_id: int | None = Field(default=None, alias="ruleVersionId", gt=0)
    rule: RuleAst | None = None
    parameters: TaskInferenceParameters

    @model_validator(mode="after")
    def validate_rule_binding(self) -> "TaskStartRequest":
        if not self.model_bindings:
            self.model_bindings = {"primary": self.model_version_id}
        elif self.model_version_id not in self.model_bindings.values():
            self.model_bindings["primary"] = self.model_version_id
        values = (self.rule_id, self.rule_version_id, self.rule)
        if any(value is not None for value in values) and any(value is None for value in values):
            raise ValueError("ruleId, ruleVersionId and rule must be provided together")
        return self


class TaskStatus(BaseModel):
    task_id: int = Field(alias="taskId")
    run_id: str = Field(alias="runId")
    config_version: int = Field(alias="configVersion")
    status: Literal["RUNNING", "FAILED", "OFFLINE", "STOPPED"]
    diagnostic_id: str = Field(alias="diagnosticId")
    metrics: dict
    error_code: str | None = Field(default=None, alias="errorCode")
    error_message: str | None = Field(default=None, alias="errorMessage")


class TaskOverlayFrame(BaseModel):
    """Latest lossy detection frame exposed to the Edge Agent for live preview."""

    task_id: int = Field(alias="taskId", gt=0)
    run_id: str = Field(alias="runId", min_length=36, max_length=36)
    camera_id: int = Field(alias="cameraId", gt=0)
    frame_id: str = Field(alias="frameId", min_length=1, max_length=128)
    timestamp: datetime
    source_width: int = Field(alias="sourceWidth", gt=0)
    source_height: int = Field(alias="sourceHeight", gt=0)
    objects: list[DetectionObject] = Field(max_length=512)
    image_base64: str | None = Field(default=None, alias="imageBase64", max_length=349_528)
    stream_id: str | None = Field(
        default=None, alias="streamId", pattern=r"^[0-9a-f-]{36}$"
    )
    source_pts: int | None = Field(default=None, alias="sourcePts", ge=0, le=2**53 - 1)
    frame_key: str | None = Field(default=None, alias="frameKey", pattern=r"^[0-9a-f]{32}$")


class TaskGlobalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    record_before_seconds: float = Field(alias="recordBeforeSeconds", ge=0, le=120)
    record_after_seconds: float = Field(alias="recordAfterSeconds", ge=0, le=120)
    default_confidence: float = Field(alias="defaultConfidence", ge=0.01, le=1.0)
    default_fps: float = Field(alias="defaultFps", ge=0.1, le=10.0)
    evidence_storage_mode: Literal["OBJECT_STORAGE"] = Field(alias="evidenceStorageMode")
    evidence_retention_days: int = Field(alias="evidenceRetentionDays", ge=1, le=3650)
    notifications_enabled: bool = Field(alias="notificationsEnabled")
    node_offline_threshold_seconds: int = Field(alias="nodeOfflineThresholdSeconds", ge=10, le=3600)


class TaskSettingsApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(alias="taskId", gt=0)
    global_settings_version: int = Field(alias="globalSettingsVersion", gt=0)
    settings: TaskGlobalSettings
