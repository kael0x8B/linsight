import importlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Protocol

import numpy as np
from PIL import Image

from ai_runtime.app.model.contracts import ModelTestParameters, ModelTestResult
from ai_runtime.app.model.person import _elapsed_ms, _nms, _to_object, decode_detection_rows
from ai_runtime.app.model.registry import AdapterDefinition

LPRNET_CHARACTERS = tuple(
    "京沪津渝冀晋蒙辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新"
    "0123456789ABCDEFGHJKLMNPQRSTUVWXYZIO-"
)


class ExecutableAdapter(Protocol):
    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult: ...


class LprNetAdapter:
    """RKNN Model Zoo LPRNet adapter for mainland Chinese licence plates."""

    def __init__(self, session, device: str) -> None:
        self._session = session
        self._device = device
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if len(inputs) != 1 or len(outputs) < 1:
            raise ValueError("LPRNet ONNX must expose exactly one input and at least one output")
        shape = inputs[0].shape
        if len(shape) != 4 or shape[1:] != [3, 24, 94]:
            raise ValueError(f"unsupported LPRNet input shape: {shape}")
        self._input_name = inputs[0].name

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        del parameters  # The pinned production model has a fixed 94x24 input contract.
        started = perf_counter()
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            source_width, source_height = image.size
            resized = image.resize((94, 24), Image.Resampling.BILINEAR)
            # The official RKNN Model Zoo reference uses OpenCV BGR input.
            array = np.asarray(resized, dtype=np.float32)[..., ::-1].copy()
            tensor = np.transpose((array - 127.5) / 127.5, (2, 0, 1))[None, ...]
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        outputs = self._session.run(None, {self._input_name: tensor})
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        text, confidence = decode_lprnet_output(np.asarray(outputs[0]))
        objects = []
        if text:
            objects.append(
                _to_license_plate_object(text, confidence)
            )
        return ModelTestResult(
            sourceWidth=source_width,
            sourceHeight=source_height,
            objects=objects,
            backend="ONNX_RUNTIME_LPRNET",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )


class LicensePlateYuNetAdapter:
    """OpenCV Zoo YuNet plate detector with quadrilateral output for rectification."""

    _MIN_SIZES = ((10, 16, 24), (32, 48), (64, 96), (128, 192, 256))
    _STEPS = (8, 16, 32, 64)

    def __init__(self, session, device: str) -> None:
        self._session = session
        self._device = device
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 3, 240, 320]:
            shape = inputs[0].shape if inputs else None
            raise ValueError(f"unsupported license-plate YuNet input shape: {shape}")
        output_names = {value.name for value in session.get_outputs()}
        if not {"loc", "conf", "iou"}.issubset(output_names):
            raise ValueError("license-plate YuNet must expose loc, conf and iou outputs")
        self._input_name = inputs[0].name
        self._priors = _license_plate_priors(320, 240, self._MIN_SIZES, self._STEPS)

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        started = perf_counter()
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            source_width, source_height = image.size
            resized = image.resize((320, 240), Image.Resampling.BILINEAR)
            bgr = np.asarray(resized, dtype=np.float32)[..., ::-1].copy()
            tensor = np.transpose(bgr, (2, 0, 1))[None, ...]
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        loc, conf, iou = self._session.run(
            ["loc", "conf", "iou"], {self._input_name: tensor}
        )
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        objects = decode_license_plate_yunet(
            np.asarray(loc),
            np.asarray(conf),
            np.asarray(iou),
            self._priors,
            parameters.confidence,
            parameters.nms_threshold,
        )
        return ModelTestResult(
            sourceWidth=source_width,
            sourceHeight=source_height,
            objects=objects,
            backend="ONNX_RUNTIME_LPD_YUNET",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )


def _license_plate_priors(width, height, min_sizes, steps) -> np.ndarray:
    feature_map = [int(int((height + 1) / 2) / 2), int(int((width + 1) / 2) / 2)]
    feature_maps = []
    for _ in range(4):
        feature_map = [int(feature_map[0] / 2), int(feature_map[1] / 2)]
        feature_maps.append(feature_map)
    priors = []
    for level, (feature_height, feature_width) in enumerate(feature_maps):
        for row in range(feature_height):
            for column in range(feature_width):
                for min_size in min_sizes[level]:
                    priors.append(
                        [
                            (column + 0.5) * steps[level] / width,
                            (row + 0.5) * steps[level] / height,
                            min_size / width,
                            min_size / height,
                        ]
                    )
    return np.asarray(priors, dtype=np.float32)


def decode_license_plate_yunet(
    loc: np.ndarray,
    conf: np.ndarray,
    iou: np.ndarray,
    priors: np.ndarray,
    confidence_threshold: float,
    nms_threshold: float,
):
    from ai_runtime.app.model.contracts import BoundingBox, DetectionObject

    if loc.shape != (len(priors), 14) or conf.shape != (len(priors), 2):
        raise ValueError(
            f"unsupported license-plate YuNet output shapes: {loc.shape}, {conf.shape}"
        )
    if iou.shape != (len(priors), 1):
        raise ValueError(f"unsupported license-plate YuNet iou shape: {iou.shape}")
    scores = np.sqrt(np.maximum(conf[:, 1], 0) * np.clip(iou[:, 0], 0, 1))
    corner_offsets = (loc[:, 4:8], loc[:, 10:14])
    corners = np.concatenate(corner_offsets, axis=1).reshape(-1, 4, 2)
    corners = priors[:, None, :2] + corners * 0.1 * priors[:, None, 2:4]
    corners = np.clip(corners, 0, 1)
    candidate_indices = np.flatnonzero(scores >= confidence_threshold)
    candidate_indices = candidate_indices[
        np.argsort(scores[candidate_indices])[::-1]
    ][:5000]
    boxes = np.column_stack(
        (
            corners[:, :, 0].min(axis=1),
            corners[:, :, 1].min(axis=1),
            corners[:, :, 0].max(axis=1),
            corners[:, :, 1].max(axis=1),
        )
    )
    kept = _box_nms(candidate_indices, boxes, scores, nms_threshold)[:750]
    objects = []
    for index in kept:
        left, top, right, bottom = boxes[index]
        attributes = {
            f"corner{point + 1}{axis.upper()}": round(float(corners[index, point, offset]), 6)
            for point in range(4)
            for offset, axis in enumerate(("x", "y"))
        }
        attributes["rectificationSource"] = "YUNET_QUADRILATERAL"
        objects.append(
            DetectionObject(
                **{
                    "class": "license_plate",
                    "confidence": round(float(scores[index]), 6),
                    "bbox": BoundingBox(
                        x=float(left),
                        y=float(top),
                        width=float(max(0, right - left)),
                        height=float(max(0, bottom - top)),
                    ),
                    "attributes": attributes,
                }
            )
        )
    return objects


def _box_nms(indices, boxes, scores, threshold: float) -> list[int]:
    remaining = list(map(int, indices))
    kept = []
    while remaining:
        current = remaining.pop(0)
        kept.append(current)
        left = np.maximum(boxes[current, 0], boxes[remaining, 0])
        top = np.maximum(boxes[current, 1], boxes[remaining, 1])
        right = np.minimum(boxes[current, 2], boxes[remaining, 2])
        bottom = np.minimum(boxes[current, 3], boxes[remaining, 3])
        intersection = np.maximum(0, right - left) * np.maximum(0, bottom - top)
        current_area = max(0, boxes[current, 2] - boxes[current, 0]) * max(
            0, boxes[current, 3] - boxes[current, 1]
        )
        other_area = np.maximum(0, boxes[remaining, 2] - boxes[remaining, 0]) * np.maximum(
            0, boxes[remaining, 3] - boxes[remaining, 1]
        )
        union = current_area + other_area - intersection
        overlap = np.divide(
            intersection, union, out=np.zeros_like(intersection), where=union > 0
        )
        remaining = [
            value
            for value, iou_value in zip(remaining, overlap, strict=True)
            if iou_value < threshold
        ]
    return kept


def decode_lprnet_output(output: np.ndarray) -> tuple[str, float]:
    if output.ndim != 3 or output.shape[0] != 1 or output.shape[1] != len(LPRNET_CHARACTERS):
        raise ValueError(f"unsupported LPRNet output shape: {list(output.shape)}")
    logits = output[0].astype(np.float64, copy=False)
    logits -= logits.max(axis=0, keepdims=True)
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum(axis=0, keepdims=True)
    indices = np.argmax(probabilities, axis=0)
    blank = len(LPRNET_CHARACTERS) - 1
    decoded: list[str] = []
    selected_probabilities: list[float] = []
    previous = -1
    for timestep, index_value in enumerate(indices):
        index = int(index_value)
        if index != previous and index != blank:
            decoded.append(LPRNET_CHARACTERS[index])
            selected_probabilities.append(float(probabilities[index, timestep]))
        previous = index
    confidence = (
        sum(selected_probabilities) / len(selected_probabilities)
        if selected_probabilities
        else 0.0
    )
    return "".join(decoded), round(confidence, 6)


def _to_license_plate_object(text: str, confidence: float):
    from ai_runtime.app.model.contracts import BoundingBox, DetectionObject

    return DetectionObject(
        **{
            "class": "license_plate",
            "confidence": confidence,
            "bbox": BoundingBox(x=0.0, y=0.0, width=1.0, height=1.0),
            "attributes": {
                "plateText": text,
                "ocrConfidence": confidence,
                "ocrCharset": "CHINESE_MAINLAND",
            },
        }
    )


class TorchScriptAdapter:
    def __init__(self, path: Path, device: str, definition: AdapterDefinition) -> None:
        try:
            self._torch = importlib.import_module("torch")
        except ModuleNotFoundError as error:
            raise ValueError(
                "TorchScript support is not installed; install linsight-runtime[pytorch]"
            ) from error
        try:
            self._model = self._torch.jit.load(str(path), map_location="cpu").eval()
        except Exception as error:
            raise ValueError(f"invalid TorchScript artifact: {type(error).__name__}") from error
        self._device = device
        self._definition = definition

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            source_width, source_height = image.size
            started = perf_counter()
            resized = image.resize(
                (parameters.input_width, parameters.input_height), Image.Resampling.BILINEAR
            )
            array = np.asarray(resized, dtype=np.float32) / 255.0
            tensor = self._torch.from_numpy(np.transpose(array, (2, 0, 1))[None, ...])
            preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        with self._torch.inference_mode():
            output = self._model(tensor)
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        rows = decode_detection_rows(
            output,
            parameters.input_width,
            parameters.input_height,
            len(self._definition.class_labels),
            parameters.confidence,
        )
        candidates = [row for row in rows if float(row[4]) >= parameters.confidence]
        objects = [
            _to_object(row, self._definition.class_labels)
            for row in _nms(candidates, parameters.nms_threshold)
        ]
        return ModelTestResult(
            sourceWidth=source_width,
            sourceHeight=source_height,
            objects=objects,
            backend="TORCHSCRIPT_CPU",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )


class UltralyticsCheckpointAdapter:
    def __init__(self, path: Path, device: str, definition: AdapterDefinition) -> None:
        try:
            ultralytics = importlib.import_module("ultralytics")
        except ModuleNotFoundError as error:
            raise ValueError(
                "Ultralytics checkpoint support is not installed; "
                "install linsight-runtime[pytorch]"
            ) from error
        try:
            self._model = ultralytics.YOLO(str(path))
        except Exception as error:
            raise ValueError(
                f"invalid or incompatible Ultralytics checkpoint: {type(error).__name__}"
            ) from error
        self._device = device
        self._definition = definition

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        started = perf_counter()
        with Image.open(image_path) as source:
            source_width, source_height = source.size
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        results = self._model.predict(
            source=image_path,
            imgsz=(parameters.input_height, parameters.input_width),
            conf=parameters.confidence,
            iou=parameters.nms_threshold,
            device="cpu",
            verbose=False,
        )
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        objects = []
        for result in results:
            if result.boxes is None:
                continue
            names = result.names if isinstance(result.names, dict) else {}
            boxes = result.boxes.xyxy.detach().cpu().numpy()
            confidences = result.boxes.conf.detach().cpu().numpy()
            class_ids = result.boxes.cls.detach().cpu().numpy().astype(int)
            for box, confidence, class_id in zip(boxes, confidences, class_ids, strict=True):
                x1, y1, x2, y2 = [float(value) for value in box]
                row = np.asarray(
                    [
                        x1 / source_width,
                        y1 / source_height,
                        (x2 - x1) / source_width,
                        (y2 - y1) / source_height,
                        float(confidence),
                        float(class_id),
                    ],
                    dtype=np.float32,
                )
                labels = self._definition.class_labels
                if class_id in names:
                    expanded = list(labels)
                    if class_id >= len(expanded):
                        expanded.extend(
                            f"class_{index}" for index in range(len(expanded), class_id + 1)
                        )
                    expanded[class_id] = str(names[class_id])
                    labels = tuple(expanded)
                objects.append(_to_object(row, labels))
        return ModelTestResult(
            sourceWidth=source_width,
            sourceHeight=source_height,
            objects=objects,
            backend="ULTRALYTICS_PYTORCH_CPU",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )


class MergedAdapter:
    def __init__(self, adapters: list[ExecutableAdapter], backend: str) -> None:
        self._adapters = adapters
        self._backend = backend

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        results = [adapter.infer(image_path, parameters) for adapter in self._adapters]
        first = results[0]
        return ModelTestResult(
            sourceWidth=first.source_width,
            sourceHeight=first.source_height,
            objects=[item for result in results for item in result.objects],
            backend=self._backend,
            device=first.device,
            preprocessMillis=sum(result.preprocess_millis for result in results),
            inferenceMillis=sum(result.inference_millis for result in results),
            postprocessMillis=sum(result.postprocess_millis for result in results),
        )


def load_pytorch_checkpoint(
    path: Path, device: str, definition: AdapterDefinition, trusted_artifact: bool
) -> tuple[ExecutableAdapter, str]:
    if not trusted_artifact:
        raise ValueError(
            "PyTorch checkpoints use pickle and are accepted only for SHA-verified PRESET assets"
        )
    family = _checkpoint_family(path)
    if family == "ultralytics":
        return (
            UltralyticsCheckpointAdapter(path, device, definition),
            "ULTRALYTICS_PYTORCH_CPU",
        )
    raise ValueError(
        "this PyTorch checkpoint stores a state_dict without its executable model definition; "
        "convert it to ONNX/TorchScript or install a model-family adapter"
    )


def extract_archive(path: Path, digest: str) -> tuple[Path, list[Path]]:
    target = path.parent / f".{path.stem}-{digest[:12]}"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 256 or sum(item.file_size for item in members) > 4 * 1024**3:
            raise ValueError("model archive exceeds extraction limits")
        normalized_names = [str(PurePosixPath(item.filename)) for item in members]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("model archive contains duplicate member paths")
        for member in members:
            relative = PurePosixPath(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("model archive contains an unsafe path")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("model archive may not contain symbolic links")
            destination = target.joinpath(*relative.parts)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
    _verify_manifest(target)
    executable = sorted(
        item
        for item in target.rglob("*")
        if item.is_file()
        and item.suffix.lower() in {".onnx", ".pt", ".pth", ".jit", ".torchscript"}
    )
    return target, executable


def _verify_manifest(root: Path) -> None:
    manifest_path = root / "bundle-manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = [path for path in root.rglob("*") if path.is_file()]
    by_name = {path.name: path for path in files}
    if len(by_name) != len(files):
        raise ValueError("model archive contains ambiguous duplicate file names")
    for member in manifest.get("members", []):
        file_name, expected = member.get("fileName"), member.get("sha256")
        candidate = by_name.get(file_name)
        if candidate is None or expected is None:
            raise ValueError("model archive manifest references a missing member")
        import hashlib

        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"model archive member SHA256 mismatch: {file_name}")


def _checkpoint_family(path: Path) -> str:
    if not zipfile.is_zipfile(path):
        return "unknown"
    with zipfile.ZipFile(path) as archive:
        pickle_members = [name for name in archive.namelist() if name.endswith("data.pkl")]
        if not pickle_members:
            return "unknown"
        marker = archive.read(pickle_members[0])[: 8 * 1024 * 1024]
    return "ultralytics" if b"ultralytics" in marker else "state_dict"
