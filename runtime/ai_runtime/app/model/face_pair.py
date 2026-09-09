"""Opt-in YuNet/SFace extraction and comparison with ONNX and RKNN backends.

The embeddings stay inside this adapter; ordinary model results contain only
face locations. A comparison is not liveness proof or a physical entry event.
"""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
import onnxruntime as ort
from PIL import Image

from ai_runtime.app.model.contracts import (
    BoundingBox,
    DetectionObject,
    ModelTestParameters,
    ModelTestResult,
)

ALIGNMENT_POINTS = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float64,
)


class FaceQualityError(ValueError):
    """A bounded reason code, without an image, identity or biometric template."""

    backend = "UNAVAILABLE"
    device = "UNAVAILABLE"


@dataclass(frozen=True)
class FaceLocation:
    box: np.ndarray
    landmarks: np.ndarray
    score: float


def align_face(image: Image.Image, landmarks: np.ndarray) -> Image.Image:
    source = np.asarray(landmarks, dtype=np.float64)
    if source.shape != (5, 2) or not np.isfinite(source).all():
        raise FaceQualityError("INVALID_LANDMARKS")
    centered = source - source.mean(axis=0)
    target = ALIGNMENT_POINTS - ALIGNMENT_POINTS.mean(axis=0)
    variance = float(np.sum(centered**2))
    if variance < 1:
        raise FaceQualityError("INVALID_LANDMARKS")
    left, singular, right = np.linalg.svd(centered.T @ target)
    correction = np.diag([1.0, np.linalg.det(left @ right)])
    rotation = left @ correction @ right
    scale = float(np.sum(singular * np.diag(correction)) / variance)
    if not np.isfinite(scale) or scale <= 0:
        raise FaceQualityError("INVALID_LANDMARKS")
    matrix = np.eye(3)
    matrix[:2, :2] = scale * rotation.T
    matrix[:2, 2] = ALIGNMENT_POINTS.mean(axis=0) - matrix[:2, :2] @ source.mean(axis=0)
    inverse = np.linalg.inv(matrix)
    return image.convert("RGB").transform(
        (112, 112),
        Image.Transform.AFFINE,
        inverse[:2].reshape(-1),
        resample=Image.Resampling.BILINEAR,
    )


class FacePairAdapter:
    backend = "ONNX_RUNTIME_FACE_PAIR_SFACE"
    device = "CPU"

    def __init__(self, directory: Path, threads: int = 2) -> None:
        options = ort.SessionOptions()
        options.log_severity_level = 3
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        options.add_session_config_entry("session.inter_op.allow_spinning", "0")
        self.detector = ort.InferenceSession(
            str(directory / "detector.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.recognizer = ort.InferenceSession(
            str(directory / "recognizer.onnx"), options, providers=["CPUExecutionProvider"]
        )
        if self.detector.get_inputs()[0].shape != [1, 3, 640, 640]:
            raise ValueError("FACE_PAIR requires fixed 640x640 YuNet")
        if self.recognizer.get_inputs()[0].shape != [1, 3, 112, 112]:
            raise ValueError("FACE_PAIR requires 112x112 SFace")

    def locate(self, image: Image.Image, confidence: float = 0.9) -> list[FaceLocation]:
        width, height = image.size
        rgb = np.asarray(image.convert("RGB").resize((640, 640)), dtype=np.float32)
        tensor = np.transpose(rgb[:, :, ::-1], (2, 0, 1))[None].copy()
        names = [v.name for v in self.detector.get_outputs()]
        outputs = dict(
            zip(
                names,
                self.detector.run(
                    None,
                    {
                        self.detector.get_inputs()[0].name: tensor,
                    },
                ),
                strict=True,
            )
        )
        candidates = []
        for stride in (8, 16, 32):
            cls = outputs[f"cls_{stride}"].reshape(-1)
            obj = outputs[f"obj_{stride}"].reshape(-1)
            scores = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
            indices = np.flatnonzero(scores >= confidence)
            boxes = outputs[f"bbox_{stride}"].reshape(-1, 4)
            points = outputs[f"kps_{stride}"].reshape(-1, 5, 2)
            for index in indices:
                grid = np.array([index % (640 // stride), index // (640 // stride)])
                center = (grid + boxes[index, :2]) * stride
                size = np.exp(np.clip(boxes[index, 2:], -20, 20)) * stride
                factor = np.array([width / 640, height / 640])
                corners = np.concatenate(
                    ((center - size / 2) * factor, (center + size / 2) * factor)
                )
                landmarks = (points[index] + grid) * stride * factor
                if np.isfinite(corners).all() and np.isfinite(landmarks).all():
                    candidates.append(FaceLocation(corners, landmarks, float(scores[index])))
        selected: list[FaceLocation] = []
        for candidate in sorted(candidates, key=lambda row: row.score, reverse=True)[:500]:
            if all(_iou(candidate.box, previous.box) < 0.3 for previous in selected):
                selected.append(candidate)
        return selected

    def extract(self, image: Image.Image) -> tuple[np.ndarray, FaceLocation]:
        faces = self.locate(image)
        if len(faces) != 1:
            raise FaceQualityError("NO_FACE" if not faces else "MULTIPLE_FACES")
        face = faces[0]
        width, height = image.size
        x1, y1, x2, y2 = face.box
        if min(x2 - x1, y2 - y1) < 64:
            raise FaceQualityError("FACE_TOO_SMALL")
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            raise FaceQualityError("FACE_CLIPPED")
        aligned = align_face(image, face.landmarks)
        pixels = np.asarray(aligned, dtype=np.float32)
        gray = pixels.mean(axis=2)
        contrast = float(gray.std())
        brightness = float(gray.mean())
        if contrast < 12 or brightness < 30 or brightness > 225:
            raise FaceQualityError("INSUFFICIENT_IMAGE_QUALITY")
        tensor = pixels.transpose(2, 0, 1)[None].copy()
        feature = np.asarray(
            self.recognizer.run(
                None,
                {
                    self.recognizer.get_inputs()[0].name: tensor,
                },
            )[0],
            dtype=np.float64,
        ).reshape(-1)
        norm = float(np.linalg.norm(feature))
        if feature.size != 128 or not np.isfinite(feature).all() or norm < 1e-8:
            raise ValueError("INVALID_FACE_FEATURE")
        return feature / norm, face

    def compare(self, reference: Image.Image, candidate: Image.Image) -> dict:
        reference_feature, _ = self.extract(reference)
        candidate_feature, location = self.extract(candidate)
        similarity = float(np.clip(reference_feature @ candidate_feature, -1, 1))
        return {
            "similarity": similarity,
            "bbox": _box(location, *candidate.size).model_dump(),
            "backend": self.backend,
            "device": self.device,
            "liveness": "NOT_VERIFIED",
        }

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as source:
            return self.infer_image(source, parameters)

    def infer_image(self, image: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        started = perf_counter()
        faces = self.locate(image, max(0.8, parameters.confidence))
        return ModelTestResult(
            sourceWidth=image.width,
            sourceHeight=image.height,
            objects=[
                DetectionObject(
                    **{
                        "class": "face",
                        "confidence": face.score,
                        "bbox": _box(face, *image.size),
                        "attributes": {"liveness": "NOT_VERIFIED", "identityCompared": False},
                    }
                )
                for face in faces
            ],
            backend=self.backend,
            device=self.device,
            preprocessMillis=0,
            inferenceMillis=round((perf_counter() - started) * 1000),
            postprocessMillis=0,
        )


def _box(face: FaceLocation, width: int, height: int) -> BoundingBox:
    x1, y1, x2, y2 = np.clip(face.box / [width, height, width, height], 0, 1)
    return BoundingBox(x=float(x1), y=float(y1), width=float(x2 - x1), height=float(y2 - y1))


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    overlap = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2]))
    intersection = float(np.prod(overlap))
    union = float(
        np.prod(np.maximum(0, a[2:] - a[:2])) + np.prod(np.maximum(0, b[2:] - b[:2])) - intersection
    )
    return intersection / max(union, 1e-9)


class RknnFacePairAdapter(FacePairAdapter):
    """Fixed YuNet/SFace RKNN pair; preprocessing matches the ONNX reference."""

    backend = "RKNN_FACE_PAIR_SFACE"
    device = "RKNPU"

    def __init__(self, directory: Path, threads: int = 2) -> None:
        import json

        metadata = json.loads((directory / "rknn-pair.json").read_text())
        if metadata.get("target") != "rk3566" or metadata.get("toolkitVersion") != "2.3.2":
            raise ValueError("face RKNN pair target or SDK mismatch")
        self.detector = _FaceRknnSession(directory, "detector", metadata["models"]["detector"], 640)
        try:
            self.recognizer = _FaceRknnSession(
                directory, "recognizer", metadata["models"]["recognizer"], 112
            )
        except BaseException:
            self.detector.close()
            raise

    def close(self) -> None:
        self.detector.close()
        self.recognizer.close()


class _FaceRknnSession:
    def __init__(self, directory: Path, name: str, metadata: dict, size: int) -> None:
        import hashlib
        import threading
        from types import SimpleNamespace

        from ai_runtime.app.model.rknn import require_rknn_sdk

        path = directory / (name + ".rknn")
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError("face RKNN member SHA256 mismatch")
        self._input = SimpleNamespace(name="input", shape=[1, 3, size, size])
        self._outputs = [SimpleNamespace(name=value) for value in metadata["outputs"]]
        self._lock = threading.Lock()
        self._closed = False
        self._runtime = require_rknn_sdk()(verbose=False)
        try:
            if self._runtime.load_rknn(str(path)) != 0 or self._runtime.init_runtime() != 0:
                raise ValueError("face RKNN initialization failed")
        except BaseException:
            self.close()
            raise

    def get_inputs(self):
        return [self._input]

    def get_outputs(self):
        return self._outputs

    def run(self, names, inputs):
        tensor = next(iter(inputs.values()))
        array = np.ascontiguousarray(tensor.transpose(0, 2, 3, 1), dtype=np.uint8)
        with self._lock:
            if self._closed:
                raise ValueError("face RKNN model released")
            outputs = self._runtime.inference(inputs=[array], data_format=["nhwc"])
            if outputs is None or len(outputs) != len(self._outputs):
                raise ValueError("face RKNN output mismatch")
            return [np.array(value, copy=True) for value in outputs]

    def close(self):
        with self._lock:
            if not self._closed:
                self._runtime.release()
                self._closed = True
