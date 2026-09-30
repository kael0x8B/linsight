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


class DetectionAdapter:
    """ONNX adapter for normalized rows and common YOLO detector export layouts."""

    def __init__(
        self,
        session: ort.InferenceSession,
        device: str,
        adapter_name: str,
        class_labels: tuple[str, ...],
    ) -> None:
        self._session = session
        self._device = device
        self._adapter_name = adapter_name
        self._class_labels = class_labels
        self._input = session.get_inputs()[0]

    def infer(self, image_path: str, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            source_width, source_height = image.size
            started = perf_counter()
            input_height, input_width = self._input_size(parameters)
            resized = image.resize((input_width, input_height), Image.Resampling.BILINEAR)
            tensor = np.asarray(resized, dtype=np.float32) / 255.0
            tensor = np.transpose(tensor, (2, 0, 1))[None, ...]
            preprocess_ms = _elapsed_ms(started)

        started = perf_counter()
        raw = self._session.run(None, {self._input.name: tensor})
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        rows = decode_detection_rows(
            raw,
            input_width,
            input_height,
            len(self._class_labels),
            parameters.confidence,
        )
        candidates = [row for row in rows if float(row[4]) >= parameters.confidence]
        objects = [
            _to_object(row, self._class_labels)
            for row in _nms(candidates, parameters.nms_threshold)
        ]
        return ModelTestResult(
            sourceWidth=source_width,
            sourceHeight=source_height,
            objects=objects,
            backend="ONNX_RUNTIME",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )

    def _input_size(self, parameters: ModelTestParameters) -> tuple[int, int]:
        shape = self._input.shape
        height = (
            shape[2] if len(shape) == 4 and isinstance(shape[2], int) else parameters.input_height
        )
        width = (
            shape[3] if len(shape) == 4 and isinstance(shape[3], int) else parameters.input_width
        )
        return height, width


class PersonDetectionAdapter(DetectionAdapter):
    def __init__(self, session: ort.InferenceSession, device: str) -> None:
        super().__init__(session, device, "person_detection_v1", ("person",))


def _to_object(row: np.ndarray, class_labels: tuple[str, ...]) -> DetectionObject:
    x, y, width, height, score, class_id = [float(value) for value in row]
    x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
    width, height = min(max(width, 0.0), 1.0 - x), min(max(height, 0.0), 1.0 - y)
    class_number = int(class_id)
    return DetectionObject(
        **{
            "class": (
                class_labels[class_number]
                if 0 <= class_number < len(class_labels)
                else f"class_{class_number}"
            ),
            "confidence": min(max(score, 0.0), 1.0),
            "bbox": BoundingBox(x=x, y=y, width=width, height=height),
            "attributes": {"classId": class_number},
        }
    )


def decode_detection_rows(
    outputs: object,
    input_width: int,
    input_height: int,
    class_count: int,
    min_confidence: float = 0.001,
) -> np.ndarray:
    """Normalize common detector tensors to `[x, y, width, height, score, classId]`."""
    arrays = _collect_arrays(outputs)
    for array in arrays:
        rows = np.asarray(array, dtype=np.float32)
        if rows.ndim == 3 and rows.shape[0] == 1:
            rows = rows[0]
        if rows.ndim == 2 and rows.shape[1] == 6:
            return rows
    yolo_rows = _decode_flat_yolo(arrays, input_width, input_height)
    if yolo_rows is not None:
        return yolo_rows
    head_rows = _decode_rknn_yolo_heads(
        arrays, input_width, input_height, class_count, min_confidence
    )
    if head_rows is not None:
        return head_rows
    raise ValueError(
        "model output layout is not supported by the selected detection adapter; "
        f"received {[tuple(value.shape) for value in arrays]}"
    )


def _collect_arrays(value: object) -> list[np.ndarray]:
    if isinstance(value, np.ndarray):
        return [value]
    if hasattr(value, "detach") and hasattr(value, "cpu"):
        return [value.detach().cpu().numpy()]
    if isinstance(value, dict):
        return [array for item in value.values() for array in _collect_arrays(item)]
    if isinstance(value, (list, tuple)):
        return [array for item in value for array in _collect_arrays(item)]
    return []


def _decode_flat_yolo(
    arrays: list[np.ndarray], input_width: int, input_height: int
) -> np.ndarray | None:
    for array in arrays:
        values = np.asarray(array, dtype=np.float32)
        if values.ndim != 3 or values.shape[0] != 1:
            continue
        values = values[0]
        if 5 <= values.shape[0] <= 512 and values.shape[1] > values.shape[0]:
            values = values.T
        if values.ndim != 2 or values.shape[1] < 5:
            continue
        coordinates = values[:, :4]
        scores = values[:, 4:]
        class_ids = np.argmax(scores, axis=1)
        confidence = scores[np.arange(scores.shape[0]), class_ids]
        if (
            float(np.nanmax(confidence, initial=0.0)) > 1.0
            or float(np.nanmin(confidence, initial=0.0)) < 0.0
        ):
            confidence = _sigmoid(confidence)
        x_center, y_center, width, height = coordinates.T
        rows = np.column_stack(
            (
                (x_center - width / 2) / input_width,
                (y_center - height / 2) / input_height,
                width / input_width,
                height / input_height,
                confidence,
                class_ids,
            )
        )
        return rows.astype(np.float32)
    return None


def _decode_rknn_yolo_heads(
    arrays: list[np.ndarray],
    input_width: int,
    input_height: int,
    class_count: int,
    min_confidence: float,
) -> np.ndarray | None:
    tensors = [np.asarray(value, dtype=np.float32) for value in arrays if value.ndim == 4]
    rows: list[list[float]] = []
    recognized = False
    for boxes in tensors:
        if boxes.shape[0] != 1 or boxes.shape[1] < 16 or boxes.shape[1] % 4:
            continue
        # A class tensor can also be divisible by four (COCO has 80 classes).
        # Never reinterpret the declared class channel count as DFL box bins.
        if class_count > 0 and boxes.shape[1] == class_count:
            continue
        height, width = boxes.shape[2:]
        class_candidates = [
            value
            for value in tensors
            if value.shape[0] == 1
            and value.shape[2:] == (height, width)
            and value is not boxes
            and value.shape[1] != 1
            and (class_count == 0 or value.shape[1] == class_count)
        ]
        if not class_candidates:
            continue
        recognized = True
        classes = min(class_candidates, key=lambda value: value.shape[1])
        class_scores = classes[0]
        if (
            float(np.nanmax(class_scores, initial=0.0)) > 1.0
            or float(np.nanmin(class_scores, initial=0.0)) < 0.0
        ):
            class_scores = _sigmoid(class_scores)
        best_scores = class_scores.max(axis=0)
        row_indices, column_indices = np.where(best_scores >= min_confidence)
        if not row_indices.size:
            continue
        best_classes = class_scores[:, row_indices, column_indices].argmax(axis=0)
        # DFL is independent at each spatial cell. Decode only cells that pass
        # the unchanged class threshold, avoiding thousands of unused softmaxes.
        reg_max = boxes.shape[1] // 4
        distribution = boxes[0].reshape(4, reg_max, height, width)[
            :, :, row_indices, column_indices
        ]
        distribution -= distribution.max(axis=1, keepdims=True)
        probability = np.exp(distribution)
        probability /= probability.sum(axis=1, keepdims=True)
        distance = (probability * np.arange(reg_max, dtype=np.float32)[None, :, None]).sum(axis=1)
        stride_x, stride_y = input_width / width, input_height / height
        for index, (row_index, column_index) in enumerate(
            zip(row_indices, column_indices, strict=True)
        ):
            left, top, right, bottom = distance[:, index]
            center_x, center_y = column_index + 0.5, row_index + 0.5
            x1 = (center_x - left) * stride_x
            y1 = (center_y - top) * stride_y
            x2 = (center_x + right) * stride_x
            y2 = (center_y + bottom) * stride_y
            rows.append(
                [
                    x1 / input_width,
                    y1 / input_height,
                    (x2 - x1) / input_width,
                    (y2 - y1) / input_height,
                    float(best_scores[row_index, column_index]),
                    float(best_classes[index]),
                ]
            )
    if not recognized:
        return None
    return np.asarray(rows, dtype=np.float32).reshape((-1, 6))


def _sigmoid(value: np.ndarray) -> np.ndarray:
    clipped = np.clip(value, -80.0, 80.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _nms(rows: list[np.ndarray], threshold: float) -> list[np.ndarray]:
    ordered = sorted(rows, key=lambda row: float(row[4]), reverse=True)
    kept: list[np.ndarray] = []
    while ordered:
        current = ordered.pop(0)
        kept.append(current)
        ordered = [
            row
            for row in ordered
            if int(row[5]) != int(current[5]) or _iou(current, row) <= threshold
        ]
    return kept


def _iou(left: np.ndarray, right: np.ndarray) -> float:
    lx1, ly1, lw, lh = [float(value) for value in left[:4]]
    rx1, ry1, rw, rh = [float(value) for value in right[:4]]
    intersection = max(0.0, min(lx1 + lw, rx1 + rw) - max(lx1, rx1)) * max(
        0.0, min(ly1 + lh, ry1 + rh) - max(ly1, ry1)
    )
    union = lw * lh + rw * rh - intersection
    return 0.0 if union <= 0 else intersection / union


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
