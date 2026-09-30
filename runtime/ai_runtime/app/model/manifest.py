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
    resize: Literal["STRETCH", "LETTERBOX", "OCR_RIGHT_PAD"] = "STRETCH"

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
        "YOLO_PLATE",
        "YOLO26_PLATE_POSE",
        "CHINESE_PLATE_CTC",
        "PLATE_OCR_ROUTED",
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
            "OBJECT_DETECTION": {"AUTO_DETECTION", "LPD_YUNET", "YOLO_PLATE", "YOLO26_PLATE_POSE"},
            "CLASSIFICATION": {"CLASSIFICATION"},
            "OCR": {"CTC_GREEDY", "LPRNET", "CHINESE_PLATE_CTC", "PLATE_OCR_ROUTED"},
            "FACE_VERIFICATION": {"FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN"},
        }
        if self.decoder.type not in valid[self.task_type]:
            raise ValueError(
                f"decoder {self.decoder.type} is incompatible with task {self.task_type}"
            )
        if (
            self.preprocess.resize == "LETTERBOX"
            and self.decoder.type not in {"YOLO_PLATE", "YOLO26_PLATE_POSE"}
        ):
            raise ValueError("LETTERBOX is currently implemented for plate pose detectors only")
        if self.preprocess.resize == "OCR_RIGHT_PAD" and self.decoder.type != "PLATE_OCR_ROUTED":
            raise ValueError("OCR_RIGHT_PAD requires PLATE_OCR_ROUTED")
        if self.decoder.type == "PLATE_OCR_ROUTED":
            expected = PreprocessManifest(
                inputWidth=320, inputHeight=48, color="BGR", resize="OCR_RIGHT_PAD",
                mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5),
            )
            if self.preprocess != expected:
                raise ValueError("routed OCR preprocessing must match its fixed two-model contract")
        if self.decoder.type in {"YOLO_PLATE", "YOLO26_PLATE_POSE", "CHINESE_PLATE_CTC"}:
            detector = self.decoder.type in {"YOLO_PLATE", "YOLO26_PLATE_POSE"}
            expected = PreprocessManifest(
                inputWidth=640 if detector else 168,
                inputHeight=640 if detector else 48,
                color="RGB" if detector else "BGR",
                resize="LETTERBOX" if detector else "STRETCH",
                mean=(0, 0, 0) if detector else (0.588, 0.588, 0.588),
                std=(1, 1, 1) if detector else (0.193, 0.193, 0.193),
            )
            embedded = expected.model_copy(
                update={
                    "layout": "NHWC",
                    "dtype": "UINT8",
                    "scale": 1.0,
                    "mean": (0, 0, 0),
                    "std": (1, 1, 1),
                }
            )
            if self.preprocess not in (expected, embedded):
                raise ValueError("plate model preprocessing must match its fixed export contract")
        return self
