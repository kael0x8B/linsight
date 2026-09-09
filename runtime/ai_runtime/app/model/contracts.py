from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.registry import ModelAdapterName


class DeployModelRequest(BaseModel):
    model_version_id: int = Field(alias="modelVersionId", gt=0)
    artifact_path: Path = Field(alias="artifactPath")
    artifact_format: Literal["ONNX", "TORCHSCRIPT", "PYTORCH", "ARCHIVE", "RKNN"] = Field(
        default="ONNX", alias="artifactFormat"
    )
    trusted_artifact: bool = Field(default=False, alias="trustedArtifact")
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    adapter: ModelAdapterName | None = None
    runtime_manifest: RuntimeManifest | None = Field(default=None, alias="runtimeManifest")
    device: Literal["CPU", "RKNPU"] = "CPU"

    @model_validator(mode="after")
    def require_execution_contract(self):
        if self.runtime_manifest is None and self.adapter is None:
            raise ValueError("runtimeManifest or legacy adapter is required")
        npu_pair = (
            self.artifact_format == "ARCHIVE"
            and self.runtime_manifest is not None
            and self.runtime_manifest.decoder.type == "FACE_PAIR_SFACE_RKNN"
        )
        if (self.artifact_format == "RKNN" or npu_pair) != (self.device == "RKNPU"):
            raise ValueError("RKNN artifacts require RKNPU; other formats require CPU")
        if self.artifact_format == "RKNN" and self.runtime_manifest is None:
            raise ValueError("RKNN execution requires runtimeManifest")
        return self


class DeployModelResponse(BaseModel):
    model_version_id: int = Field(alias="modelVersionId")
    backend: str
    device: str
    reused: bool


class ModelTestParameters(BaseModel):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    confidence: Annotated[float, Field(ge=0.01, le=1.0)]
    nms_threshold: Annotated[float, Field(alias="nmsThreshold", ge=0.01, le=1.0)]
    input_width: Annotated[int, Field(alias="inputWidth", ge=32, le=2048)]
    input_height: Annotated[int, Field(alias="inputHeight", ge=32, le=2048)]
    output_coordinates: Literal["NORMALIZED_XYWH"] = Field(alias="outputCoordinates")


class ModelTestRequest(BaseModel):
    model_version_id: int = Field(alias="modelVersionId", gt=0)
    image_path: Path = Field(alias="imagePath")
    parameters: ModelTestParameters
    device: Literal["CPU", "RKNPU"] | None = None


class BoundingBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


class DetectionObject(BaseModel):
    class_name: str = Field(alias="class")
    confidence: float = Field(ge=0, le=1)
    bbox: BoundingBox
    track_id: str | None = Field(default=None, alias="trackId")
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ModelTestResult(BaseModel):
    schema_version: Literal["1.0"] = Field(default="1.0", alias="schemaVersion")
    source_width: int = Field(alias="sourceWidth", gt=0)
    source_height: int = Field(alias="sourceHeight", gt=0)
    objects: list[DetectionObject]
    backend: str
    device: str
    preprocess_millis: int = Field(alias="preprocessMillis", ge=0)
    inference_millis: int = Field(alias="inferenceMillis", ge=0)
    postprocess_millis: int = Field(alias="postprocessMillis", ge=0)
