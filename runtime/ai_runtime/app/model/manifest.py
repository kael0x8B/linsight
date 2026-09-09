from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PreprocessManifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input_width: Annotated[int | None, Field(default=None, alias="inputWidth", ge=16, le=4096)]
    input_height: Annotated[int | None, Field(default=None, alias="inputHeight", ge=16, le=4096)]
    color: Literal["RGB", "BGR"] = "RGB"
    layout: Literal["NCHW", "NHWC"] = "NCHW"
    dtype: Literal["FLOAT32", "UINT8"] = "FLOAT32"
    scale: float = Field(default=1.0 / 255.0, gt=0, le=1)
    mean: tuple[float, float, float] = (0.0, 0.0, 0.0)
    std: tuple[float, float, float] = (1.0, 1.0, 1.0)
    resize: Literal["STRETCH"] = "STRETCH"

    @model_validator(mode="after")
    def validate_numeric_contract(self):
        if self.dtype == "UINT8" and (
            self.scale != 1.0 or self.mean != (0.0, 0.0, 0.0) or self.std != (1.0, 1.0, 1.0)
        ):
            raise ValueError("UINT8 preprocessing cannot apply float normalization")
        if any(value == 0 for value in self.std):
            raise ValueError("preprocess std cannot contain zero")
        return self


class DecoderManifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal[
        "AUTO_DETECTION",
        "CLASSIFICATION",
        "CTC_GREEDY",
        "LPD_YUNET",
        "FACE_PAIR_SFACE",
        "FACE_PAIR_SFACE_RKNN",
        "LPRNET",
    ]
    labels: tuple[str, ...] = ()
    charset: tuple[str, ...] = ()
    blank_index: int | None = Field(default=None, alias="blankIndex", ge=0)

    @model_validator(mode="after")
    def validate_decoder_contract(self):
        if self.type in {"AUTO_DETECTION", "CLASSIFICATION"} and not self.labels:
            raise ValueError(f"decoder {self.type} requires labels")
        if self.type == "CTC_GREEDY" and not self.charset:
            raise ValueError("CTC_GREEDY decoder requires charset")
        if self.blank_index is not None and self.charset and self.blank_index >= len(self.charset):
            raise ValueError("blankIndex is outside charset")
        return self


class RuntimeManifest(BaseModel):
    """Versioned, data-driven execution contract for one model artifact."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    task_type: Literal["OBJECT_DETECTION", "CLASSIFICATION", "OCR", "FACE_VERIFICATION"] = Field(
        alias="taskType"
    )
    preprocess: PreprocessManifest
    decoder: DecoderManifest

    @model_validator(mode="after")
    def validate_task_decoder_pair(self):
        valid = {
            "OBJECT_DETECTION": {"AUTO_DETECTION", "LPD_YUNET"},
            "CLASSIFICATION": {"CLASSIFICATION"},
            "OCR": {"CTC_GREEDY", "LPRNET"},
            "FACE_VERIFICATION": {"FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN"},
        }
        if self.decoder.type not in valid[self.task_type]:
            raise ValueError(
                f"decoder {self.decoder.type} is incompatible with task {self.task_type}"
            )
        return self
