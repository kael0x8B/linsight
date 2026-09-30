"""Chinese plate-specific ONNX contracts and original-image rectification.

The pinned YOLO plate model emits four landmarks and single/double-line classes.
Its paired CNN emits CTC character logits and a separate plate-colour head.
"""

import math
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image

from ai_runtime.app.model.backends import _box_nms, _to_license_plate_object
from ai_runtime.app.model.contracts import (
    BoundingBox,
    DetectionObject,
    ModelTestParameters,
    ModelTestResult,
)
from ai_runtime.app.model.person import _elapsed_ms

PLATE_CHARACTERS = tuple(
    "#京沪津渝冀晋蒙辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新"
    "学警港澳挂使领民航危0123456789ABCDEFGHJKLMNPQRSTUVWXYZ险品"
)
PLATE_COLORS = ("BLACK", "BLUE", "GREEN", "WHITE", "YELLOW")


def plate_letterbox(source: Image.Image) -> tuple[Image.Image, float, int, int]:
    """One pixel-identical input geometry for CPU and NPU plate detectors."""
    ratio = min(640 / source.width, 640 / source.height)
    size = (max(1, int(source.width * ratio)), max(1, int(source.height * ratio)))
    left, top = (640 - size[0]) // 2, (640 - size[1]) // 2
    canvas = Image.new("RGB", (640, 640), (114, 114, 114))
    canvas.paste(source.convert("RGB").resize(size, Image.Resampling.BILINEAR), (left, top))
    return canvas, ratio, left, top


class YoloPlateAdapter:
    def __init__(self, session, device: str) -> None:
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 3, 640, 640]:
            raise ValueError("YOLO_PLATE requires fixed [1,3,640,640] input")
        self._session, self._device = session, device
        self._input_name = inputs[0].name

    def infer(self, image_path: str | Path, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as image:
            return self.infer_image(image, parameters)

    def infer_image(self, source: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        started = perf_counter()
        width, height = source.size
        canvas, ratio, left, top = plate_letterbox(source)
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        outputs = self._session.run(None, {self._input_name: tensor})
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        objects = decode_yolo_plate(
            outputs[0],
            width,
            height,
            ratio,
            left,
            top,
            parameters.confidence,
            parameters.nms_threshold,
        )
        return ModelTestResult(
            sourceWidth=width,
            sourceHeight=height,
            objects=objects,
            backend="ONNX_RUNTIME_YOLO_PLATE",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )


class Yolo26PlateAdapter:
    """Four-corner YOLO26 pose head exported before device-incompatible TopK."""

    def __init__(self, session, device: str) -> None:
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 3, 640, 640]:
            raise ValueError("YOLO26_PLATE_POSE requires fixed [1,3,640,640] input")
        self._session, self._device = session, device
        self._input_name = inputs[0].name

    def infer(self, image_path: str | Path, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as image:
            return self.infer_image(image, parameters)

    def infer_image(self, source: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        started = perf_counter()
        width, height = source.size
        canvas, ratio, left, top = plate_letterbox(source)
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        outputs = self._session.run(None, {self._input_name: tensor})
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        objects = decode_yolo26_plate_pose(
            combine_yolo26_pose_outputs(outputs), width, height, ratio, left, top,
            parameters.confidence, parameters.nms_threshold,
        )
        return ModelTestResult(
            sourceWidth=width, sourceHeight=height, objects=objects,
            backend="ONNX_RUNTIME_YOLO26_PLATE_POSE", device=self._device,
            preprocessMillis=preprocess_ms, inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )


def combine_yolo26_pose_outputs(outputs: list[np.ndarray]) -> np.ndarray:
    """Accept the FP16 single output or separately quantized INT8 output heads."""
    if len(outputs) == 1:
        return np.asarray(outputs[0])
    expected = ((1, 8400, 4), (1, 8400, 2), (1, 8400, 8))
    if len(outputs) != 3 or tuple(np.asarray(x).shape for x in outputs) != expected:
        raise ValueError("YOLO26_PLATE_POSE requires one raw or three split outputs")
    return np.concatenate(outputs, axis=2)


def decode_yolo26_plate_pose(
    output: np.ndarray,
    width: int,
    height: int,
    ratio: float,
    pad_x: int,
    pad_y: int,
    confidence: float,
    nms: float,
) -> list[DetectionObject]:
    """Decode [xyxy, two class scores, TL/TR/BR/BL corners] in letterbox pixels."""
    rows = np.asarray(output, dtype=np.float32)
    if rows.shape != (1, 8400, 14):
        raise ValueError(f"YOLO26_PLATE_POSE output must be [1,8400,14], got {rows.shape}")
    rows = rows[0]
    scores = rows[:, 4:6].max(axis=1)
    classes = rows[:, 4:6].argmax(axis=1)
    valid = np.flatnonzero(np.isfinite(rows).all(axis=1) & (scores >= confidence))
    valid = valid[np.argsort(scores[valid])[::-1]][:3000]
    boxes = rows[:, :4].copy()
    boxes[:, [0, 2]] = np.clip((boxes[:, [0, 2]] - pad_x) / ratio / width, 0, 1)
    boxes[:, [1, 3]] = np.clip((boxes[:, [1, 3]] - pad_y) / ratio / height, 0, 1)
    objects = []
    for index in _box_nms(valid, boxes, scores, nms)[:100]:
        x1, y1, x2, y2 = map(float, boxes[index])
        if x2 <= x1 or y2 <= y1:
            continue
        points = rows[index, 6:14].reshape(4, 2).copy()
        points[:, 0] = np.clip((points[:, 0] - pad_x) / ratio / width, 0, 1)
        points[:, 1] = np.clip((points[:, 1] - pad_y) / ratio / height, 0, 1)
        attributes = {
            "plateLayout": "DOUBLE" if classes[index] == 1 else "SINGLE",
            "rectificationSource": "YOLO_PLATE_QUADRILATERAL",
        }
        attributes.update({
            f"corner{i + 1}{axis}": float(points[i, j])
            for i in range(4)
            for j, axis in enumerate(("X", "Y"))
        })
        objects.append(DetectionObject(**{
            "class": "license_plate",
            "confidence": float(np.clip(scores[index], 0, 1)),
            "bbox": BoundingBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
            "attributes": attributes,
        }))
    return objects


def decode_yolo_plate(
    output: np.ndarray,
    width: int,
    height: int,
    ratio: float,
    pad_x: int,
    pad_y: int,
    confidence: float,
    nms: float,
) -> list[DetectionObject]:
    rows = np.asarray(output, dtype=np.float32)
    if rows.ndim != 3 or rows.shape[0] != 1 or rows.shape[2] != 15:
        raise ValueError(f"YOLO_PLATE output must be [1,N,15], got {rows.shape}")
    rows = rows[0]
    scores = rows[:, 4] * rows[:, 13:15].max(axis=1)
    valid = np.flatnonzero(np.isfinite(rows).all(axis=1) & (scores >= confidence))
    valid = valid[np.argsort(scores[valid])[::-1]][:3000]
    boxes = np.column_stack((rows[:, :2] - rows[:, 2:4] / 2, rows[:, :2] + rows[:, 2:4] / 2))
    boxes[:, [0, 2]] = np.clip((boxes[:, [0, 2]] - pad_x) / ratio / width, 0, 1)
    boxes[:, [1, 3]] = np.clip((boxes[:, [1, 3]] - pad_y) / ratio / height, 0, 1)
    objects = []
    for index in _box_nms(valid, boxes, scores, nms)[:100]:
        x1, y1, x2, y2 = map(float, boxes[index])
        if x2 <= x1 or y2 <= y1:
            continue
        points = rows[index, 5:13].reshape(4, 2).copy()
        points[:, 0] = (points[:, 0] - pad_x) / ratio / width
        points[:, 1] = (points[:, 1] - pad_y) / ratio / height
        attributes = {
            f"corner{i + 1}{axis}": float(points[i, j])
            for i in range(4)
            for j, axis in enumerate(("X", "Y"))
        }
        attributes.update(
            {
                "plateLayout": "DOUBLE" if rows[index, 14] > rows[index, 13] else "SINGLE",
                "rectificationSource": "YOLO_PLATE_QUADRILATERAL",
            }
        )
        objects.append(
            DetectionObject(
                **{
                    "class": "license_plate",
                    "confidence": float(np.clip(scores[index], 0, 1)),
                    "bbox": BoundingBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1),
                    "attributes": attributes,
                }
            )
        )
    return objects


class ChinesePlateOcrAdapter:
    def __init__(self, session, device: str) -> None:
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 3, 48, 168]:
            raise ValueError("CHINESE_PLATE_CTC requires fixed [1,3,48,168] input")
        if len(session.get_outputs()) != 2:
            raise ValueError("CHINESE_PLATE_CTC requires character and colour outputs")
        self._session, self._device = session, device
        self._input_name = inputs[0].name

    def infer(self, image_path: str | Path, parameters: ModelTestParameters) -> ModelTestResult:
        with Image.open(image_path) as source:
            return self.infer_image(source, parameters)

    def infer_image(self, source: Image.Image, parameters: ModelTestParameters) -> ModelTestResult:
        del parameters
        started = perf_counter()
        number_region, offset = plate_number_region(source)
        image = number_region.resize((168, 48), Image.Resampling.BILINEAR)
        bgr = np.asarray(image, dtype=np.float32)[..., ::-1].copy()
        tensor = ((bgr / 255 - 0.588) / 0.193).transpose(2, 0, 1)[None]
        preprocess_ms = _elapsed_ms(started)
        started = perf_counter()
        outputs = self._session.run(None, {self._input_name: tensor})
        inference_ms = _elapsed_ms(started)
        started = perf_counter()
        objects = decode_chinese_plate_ctc(*outputs)
        for detected in objects:
            detected.attributes.update(
                {
                    "ocrNumberRegionLeft": offset / source.width,
                    "ocrLayout": "YELLOW_SIDEBAR" if offset else "STANDARD",
                }
            )
        return ModelTestResult(
            sourceWidth=source.width,
            sourceHeight=source.height,
            objects=objects,
            backend="ONNX_RUNTIME_CHINESE_PLATE_CTC",
            device=self._device,
            preprocessMillis=preprocess_ms,
            inferenceMillis=inference_ms,
            postprocessMillis=_elapsed_ms(started),
        )


def plate_number_region(source: Image.Image) -> tuple[Image.Image, int]:
    """Exclude a small yellow auxiliary column on a non-yellow plate.

    Some site plates put two small yellow characters beside the white number.
    Feeding that column into CTC merges it with the province glyph. Require
    evidence of the column itself; never trim a fixed fraction of every plate.
    """
    rgb = source.convert("RGB")
    if rgb.width < 40 or rgb.height < 16:
        return rgb, 0
    pixels = np.asarray(rgb, dtype=np.float32)
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    yellow = (r > 1.5 * b) & (g > 1.35 * b) & (r > 0.75 * g) & (np.minimum(r, g) > 65)
    # A yellow background / yellow number is not an auxiliary column.
    if yellow[:, int(rgb.width * 0.2) :].mean() > 0.015:
        return rgb, 0
    stacked_offset = _colored_stacked_auxiliary_offset(pixels)
    if stacked_offset:
        return rgb.crop((stacked_offset, 0, rgb.width, rgb.height)), stacked_offset
    # Low-resolution perspective crops can move the two-line site marker as far
    # as 18% into the padded plate image.  Inspect a slightly wider band, while
    # the yellow-background guard above still protects ordinary yellow plates.
    left = yellow[:, : max(1, int(rgb.width * 0.20))]
    columns = np.flatnonzero(left.sum(axis=0) >= max(2, rgb.height * 0.045))
    # Isolated yellow compression fringes on a white province glyph are not a
    # sidebar. Require a connected horizontal span, not three scattered pixels.
    runs = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
    connected = [run for run in runs if len(run) >= 3]
    columns = np.concatenate(connected) if connected else np.array([], dtype=int)
    if len(columns) >= 3 and columns[-1] >= rgb.width * 0.04:
        rows = np.flatnonzero(left[:, columns].any(axis=1))
        # In an oblique/moving crop one of the two small glyphs may lose its colour
        # through blur. A substantial glyph is enough; a thin reflection is not.
        # Thin strokes survive the 1080p capture as roughly 12% of the crop height.
        # Keep the threshold above a short reflection (covered by the regression
        # test) but do not require the filled synthetic glyph height used originally.
        if len(rows) >= rgb.height * 0.12 and rows[-1] - rows[0] >= rgb.height * 0.10:
            offset = int(columns[-1]) + 1
            if offset <= rgb.width * 0.18:
                return rgb.crop((offset, 0, rgb.width, rgb.height)), offset
    # Vertically separated bright strokes also occur in ordinary province
    # glyphs (吉、晋、鲁、宁、云). Geometry alone cannot authorize deleting
    # them. A dim marker without positive colour evidence remains in the crop.
    return rgb, 0


def _colored_stacked_auxiliary_offset(pixels: np.ndarray) -> int:
    """Recognize two small yellow rows when compression weakens their chroma.

    The relaxed colour threshold is safe only with both compact rows and a
    non-yellow number body. White province radicals alone cannot match it.
    """
    height, width = pixels.shape[:2]
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    colored = (
        (r > 1.08 * b)
        & (g > 1.25 * b)
        & (r > 0.65 * g)
        & (r > 70)
        & (r - b > 8)
    )
    if colored[:, int(width * 0.2) :].mean() > 0.015:
        return 0
    core = colored[
        max(1, round(height * 0.08)) : min(height - 1, round(height * 0.9)),
        : int(width * 0.2),
    ]
    columns = np.flatnonzero(core.sum(axis=0) >= max(2, height * 0.025))
    column_runs = np.split(columns, np.flatnonzero(np.diff(columns) > 1) + 1)
    for columns in column_runs:
        if (
            len(columns) < 3
            or len(columns) > width * 0.13
            or columns[-1] + 1 > width * 0.18
        ):
            continue
        rows = np.flatnonzero(core[:, columns].any(axis=1))
        row_runs = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)
        groups = [run for run in row_runs if max(3, height * 0.07) <= len(run) <= height * 0.32]
        for upper, lower in zip(groups, groups[1:], strict=False):
            if lower[0] - upper[-1] - 1 < max(3, height * 0.07):
                continue
            # Compression can leave only half the lower glyph's coloured
            # strokes. Both rows still need a substantial shared column span.
            coverage = min(
                core[upper][:, columns].any(axis=0).sum(),
                core[lower][:, columns].any(axis=0).sum(),
            )
            if coverage >= len(columns) * 0.5:
                return int(columns[-1]) + 1
    return 0


def _probabilities(logits: np.ndarray) -> np.ndarray:
    values = np.asarray(logits, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("plate model returned non-finite logits")
    values = np.exp(values - values.max(axis=-1, keepdims=True))
    return values / values.sum(axis=-1, keepdims=True)


def decode_chinese_plate_ctc(characters: np.ndarray, color: np.ndarray) -> list[DetectionObject]:
    characters, color = np.asarray(characters), np.asarray(color)
    if (
        characters.ndim != 3
        or characters.shape[0] != 1
        or (characters.shape[2] != len(PLATE_CHARACTERS))
    ):
        raise ValueError("CHINESE_PLATE_CTC output must be [1,time,78]")
    if color.shape != (1, len(PLATE_COLORS)):
        raise ValueError("Chinese plate colour output must be [1,5]")
    probabilities = _probabilities(characters)[0]
    text, confidences, previous = [], [], 0
    for timestep, value in enumerate(probabilities.argmax(axis=1)):
        index = int(value)
        if index and index != previous:
            text.append(PLATE_CHARACTERS[index])
            confidences.append(float(probabilities[timestep, index]))
        previous = index
    if not text:
        return []
    detected = _to_license_plate_object("".join(text), sum(confidences) / len(confidences))
    colors = _probabilities(color)[0]
    color_index = int(colors.argmax())
    detected.attributes.update(
        {
            "ocrMinCharConfidence": min(confidences),
            "plateColor": PLATE_COLORS[color_index],
            "plateColorConfidence": float(colors[color_index]),
        }
    )
    return [detected]


def rectify_plate(
    source: Image.Image, detected: DetectionObject, margin: float = 0.0
) -> tuple[Image.Image, str]:
    """Crop original pixels, optionally adding a fractional border around the plate."""
    if not 0 <= margin <= 0.2:
        raise ValueError("plate crop margin must be between 0 and 0.2")
    width, height = source.size
    attrs, box = detected.attributes, detected.bbox
    double = attrs.get("plateLayout") == "DOUBLE"
    crop, method = None, "BOUNDING_BOX"
    try:
        points = np.array(
            [
                (float(attrs[f"corner{i}X"]) * width, float(attrs[f"corner{i}Y"]) * height)
                for i in range(1, 5)
            ]
        )
        if not np.isfinite(points).all():
            raise ValueError("non-finite corners")
        # Order independently of adapter output order and verify a convex quadrilateral.
        center = points.mean(axis=0)
        points = points[np.argsort(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))]
        points = np.roll(points, -int(points.sum(axis=1).argmin()), axis=0)
        sides = np.roll(points, -1, axis=0) - points
        cross = sides[:, 0] * np.roll(sides[:, 1], -1) - sides[:, 1] * np.roll(sides[:, 0], -1)
        tl, tr, br, bl = points
        w = max(math.dist(tl, tr), math.dist(bl, br))
        h = max(math.dist(tl, bl), math.dist(tr, br))
        valid = (
            np.all(cross > 1)
            and w >= 4
            and h >= 4
            and (1.0 if double else 1.8) <= w / h <= (4 if double else 7)
            and np.all(points >= 0)
            and np.all(points <= [width, height])
            and np.all(
                points >= [(box.x - box.width * 0.2) * width, (box.y - box.height * 0.2) * height]
            )
            and np.all(
                points <= [(box.x + box.width * 1.2) * width, (box.y + box.height * 1.2) * height]
            )
        )
        if valid:
            if margin:
                center = points.mean(axis=0)
                padded = center + (points - center) * (1 + 2 * margin)
                # A plate touching the frame edge cannot gain real context there.
                if np.all(padded >= 0) and np.all(padded <= [width, height]):
                    points = padded
                    tl, tr, br, bl = points
                    w = max(math.dist(tl, tr), math.dist(bl, br))
                    h = max(math.dist(tl, bl), math.dist(tr, br))
            target = (math.ceil(w), math.ceil(h))
            destinations = [
                (0, 0),
                (target[0] - 1, 0),
                (target[0] - 1, target[1] - 1),
                (0, target[1] - 1),
            ]
            matrix, rhs = [], []
            for (x, y), (u, v) in zip(destinations, points, strict=True):
                matrix.extend(
                    [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
                )
                rhs.extend([u, v])
            coefficients = np.linalg.solve(np.asarray(matrix), np.asarray(rhs))
            crop = source.transform(
                target, Image.Transform.PERSPECTIVE, coefficients, resample=Image.Resampling.BICUBIC
            )
            method = "PERSPECTIVE"
    except (KeyError, TypeError, ValueError, np.linalg.LinAlgError):
        pass  # A bad quadrilateral must not turn a horizontal plate into a portrait crop.
    if crop is None:
        border = 0.03 + margin
        left = max(0, math.floor((box.x - box.width * border) * width))
        top = max(0, math.floor((box.y - box.height * border) * height))
        right = min(width, math.ceil((box.x + box.width * (1 + border)) * width))
        bottom = min(height, math.ceil((box.y + box.height * (1 + border)) * height))
        if right - left < 4 or bottom - top < 4:
            raise ValueError("plate crop is too small")
        crop = source.crop((left, top, right, bottom))
    if double:
        w, h = crop.size
        lower = crop.crop((0, h // 3, w, h))
        upper = crop.crop((0, 0, w, int(h * 5 / 12))).resize(lower.size)
        combined = Image.new("RGB", (2 * w, lower.height))
        combined.paste(upper, (0, 0))
        combined.paste(lower, (w, 0))
        crop = combined
        method += "_DOUBLE_LINE"
    return crop, method
