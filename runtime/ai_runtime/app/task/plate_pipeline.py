"""Plate inference uses original pixels and returns full-frame coordinates."""

import asyncio
import math
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from ai_runtime.app.capability.postprocess import is_supported_chinese_plate
from ai_runtime.app.model.contracts import (
    BoundingBox,
    DetectionObject,
    ModelTestParameters,
    ModelTestRequest,
    ModelTestResult,
)
from ai_runtime.app.model.plate import rectify_plate
from ai_runtime.app.rule.contracts import RuleAst

if TYPE_CHECKING:
    from ai_runtime.app.task.inference import TaskFrameInference


_PLATE_PROPOSAL_MAX_SIZE = (320, 180)
_PLATE_DETECTOR_OCR_FLOOR = 0.25
_PLATE_PROPOSAL_COLOR_RANGES = (
    ("YELLOW", 18, 58, 70, 55),
    ("GREEN", 58, 150, 60, 35),
    ("BLUE", 135, 210, 75, 35),
)


def _colored_components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Return sparse four-connected components without adding a heavy CV dependency."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=np.bool_)
    components = []
    for row_value, column_value in np.argwhere(mask):
        row, column = int(row_value), int(column_value)
        if visited[row, column]:
            continue
        pending = [(row, column)]
        visited[row, column] = True
        left = right = column
        top = bottom = row
        count = 0
        while pending:
            y, x = pending.pop()
            count += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    pending.append((next_y, next_x))
        components.append((left, top, right + 1, bottom + 1, count))
    return components


def _window_iou(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    # Windows are expressed in pixels when proposals are compared, but in
    # normalized 0..1 coordinates when detections are deduplicated.  Clamping
    # the denominator to 1 made every normalized IoU equal to the tiny raw
    # intersection area, so the full-frame and zoom passes could report the
    # same plate twice.
    return intersection / max(1e-9, first_area + second_area - intersection)


def _detection_overlaps_window(
    detected: DetectionObject,
    window: tuple[int, int, int, int],
    source_size: tuple[int, int],
) -> bool:
    source_width, source_height = source_size
    box = detected.bbox
    detected_window = (
        box.x * source_width,
        box.y * source_height,
        (box.x + box.width) * source_width,
        (box.y + box.height) * source_height,
    )
    return _window_iou(detected_window, window) > 0.01


def _deduplicate_plate_detections(
    detections: list[DetectionObject], threshold: float
) -> list[DetectionObject]:
    selected = []
    # A colour proposal may start inside a two-colour site plate and detect only
    # its larger body.  Its zoomed score can exceed the complete full-frame box,
    # but selecting it drops the province/sidebar before OCR.  When boxes overlap,
    # keep the detector's full-frame (or configured ROI) observation as the
    # canonical geometry; proposals remain valuable when the base pass missed.
    def priority(item: DetectionObject) -> tuple[int, float]:
        input_region = item.attributes.get("plateInputRegion")
        canonical = input_region in {"FULL_FRAME", "RULE_ROI"}
        return int(canonical), item.confidence

    for detected in sorted(detections, key=priority, reverse=True):
        box = detected.bbox
        window = (box.x, box.y, box.x + box.width, box.y + box.height)
        if any(
            _window_iou(
                window,
                (
                    existing.bbox.x,
                    existing.bbox.y,
                    existing.bbox.x + existing.bbox.width,
                    existing.bbox.y + existing.bbox.height,
                ),
            )
            >= threshold
            for existing in selected
        ):
            continue
        selected.append(detected)
    return selected


def plate_color_proposal_windows(source: Image.Image) -> list[tuple[int, int, int, int]]:
    """Find small blue, green or yellow plate-shaped regions for a zoomed detector pass.

    The YOLO plate model has a fixed 640 square input. A distant plate can retain
    readable source pixels but shrink below the detector's feature scale when a
    16:9 frame is letterboxed. Colour proposals only select zoom windows; YOLO
    still has to confirm every returned plate, so a coloured sign is not itself a
    detection.
    """
    scale = min(
        1.0,
        _PLATE_PROPOSAL_MAX_SIZE[0] / source.width,
        _PLATE_PROPOSAL_MAX_SIZE[1] / source.height,
    )
    work_size = (
        max(1, round(source.width * scale)),
        max(1, round(source.height * scale)),
    )
    work = source if scale == 1 else source.resize(work_size, Image.Resampling.BILINEAR)
    try:
        hsv = np.asarray(work.convert("HSV"))
    finally:
        if work is not source:
            work.close()
    hue, saturation, value = (hsv[..., index] for index in range(3))
    minimum_pixels = max(12, round(work_size[0] * work_size[1] * 0.000025))
    candidates: list[tuple[float, tuple[int, int, int, int]]] = []
    for color, hue_minimum, hue_maximum, saturation_minimum, value_minimum in (
        _PLATE_PROPOSAL_COLOR_RANGES
    ):
        mask = (
            (hue >= hue_minimum)
            & (hue <= hue_maximum)
            & (saturation >= saturation_minimum)
            & (value >= value_minimum)
        )
        for left, top, right, bottom, count in _colored_components(mask):
            width, height = right - left, bottom - top
            if count < minimum_pixels or width < 8 or height < 4:
                continue
            aspect = width / height
            density = count / (width * height)
            if not 2.25 <= aspect <= 6.5 or density < 0.32:
                continue
            if not 0.012 <= width / work_size[0] <= 0.40:
                continue
            if not 0.006 <= height / work_size[1] <= 0.18:
                continue
            shape_score = 1 - min(0.8, abs(aspect - 3.2) / 3.2)
            size_score = min(1.0, count / (minimum_pixels * 3)) ** 0.1
            # Green and blue backgrounds normally carry bright plate glyphs and
            # are less common than plate-shaped yellow machinery or packaging.
            color_score = 1.15 if color in {"GREEN", "BLUE"} else 1.0
            candidates.append(
                (density * shape_score * size_score * color_score, (left, top, right, bottom))
            )

    windows: list[tuple[int, int, int, int]] = []
    for _, component in sorted(candidates, reverse=True):
        left, top, right, bottom = (round(coordinate / scale) for coordinate in component)
        component_width = right - left
        center_x, center_y = (left + right) / 2, (top + bottom) / 2
        crop_width = min(source.width, max(80, round(component_width * 4.2)))
        crop_height = min(source.height, max(45, round(crop_width * 9 / 16)))
        crop_left = round(center_x - crop_width / 2)
        crop_top = round(center_y - crop_height / 2)
        crop_left = max(0, min(crop_left, source.width - crop_width))
        crop_top = max(0, min(crop_top, source.height - crop_height))
        window = (crop_left, crop_top, crop_left + crop_width, crop_top + crop_height)
        if window == (0, 0, source.width, source.height):
            continue
        if any(_window_iou(window, existing) > 0.55 for existing in windows):
            continue
        windows.append(window)
        if len(windows) == 6:
            break
    return windows


def plate_input_window(
    source: Image.Image,
    rule: RuleAst | None,
    use_roi: bool,
) -> tuple[int, int, int, int]:
    if not use_roi or rule is None:
        return (0, 0, source.width, source.height)
    points = [point for region in rule.regions for point in region.points]
    # The polygon itself remains the event rule. Its envelope supplies detector pixels.
    # A small context border avoids cutting the plate at the configured boundary.
    return (
        max(0, math.floor(min(p.x for p in points) * source.width) - 8),
        max(0, math.floor(min(p.y for p in points) * source.height) - 8),
        min(source.width, math.ceil(max(p.x for p in points) * source.width) + 8),
        min(source.height, math.ceil(max(p.y for p in points) * source.height) + 8),
    )


def restore_plate_coordinates(
    detected: DetectionObject,
    window: tuple[int, int, int, int],
    source_size: tuple[int, int],
) -> DetectionObject:
    left, top, right, bottom = window
    width, height = source_size
    crop_width, crop_height = right - left, bottom - top
    box = detected.bbox
    attributes = dict(detected.attributes)
    for index in range(1, 5):
        for axis, offset, extent, total in (
            ("X", left, crop_width, width),
            ("Y", top, crop_height, height),
        ):
            key = f"corner{index}{axis}"
            if key in attributes:
                attributes[key] = (offset + float(attributes[key]) * extent) / total
    attributes["plateInputRegion"] = "RULE_ROI" if window != (0, 0, width, height) else "FULL_FRAME"
    return detected.model_copy(
        update={
            "bbox": BoundingBox(
                x=(left + box.x * crop_width) / width,
                y=(top + box.y * crop_height) / height,
                width=box.width * crop_width / width,
                height=box.height * crop_height / height,
            ),
            "attributes": attributes,
        }
    )


async def infer_license_plates(
    runner: "TaskFrameInference",
    detector_nodes: set[str],
    capabilities: dict[str, str],
    ocr_model_id: int,
    parameters: ModelTestParameters,
    image: Image.Image | None,
) -> tuple[list[ModelTestResult], list[DetectionObject]]:
    source = image if image is not None else Image.open(runner.frame_path).convert("RGB")
    results, plate_detections, other_objects = [], [], []
    region_path = runner.frame_path.parent / "plate-input-region.png"
    region_image = source
    is_crop = False
    try:
        window = plate_input_window(
            source,
            getattr(runner.request, "rule", None),
            runner.request.parameters.plate_use_rule_roi,
        )
        is_crop = window != (0, 0, source.width, source.height)
        region_image = source.crop(window) if is_crop else source
        for node_id in sorted(detector_nodes):
            model_id = runner.request.model_bindings.get(node_id)
            if model_id is None:
                raise ValueError(f"pipeline node has no model binding: {node_id}")
            plate_detector = capabilities[node_id] == "detector.license-plate"
            path = region_path if plate_detector and is_crop else runner.frame_path
            detector_parameters = (
                parameters.model_copy(
                    update={
                        "confidence": min(
                            parameters.confidence,
                            _PLATE_DETECTOR_OCR_FLOOR,
                        )
                    }
                )
                if plate_detector
                else parameters
            )
            result = await runner.model_pool.test(
                ModelTestRequest(
                    modelVersionId=model_id,
                    imagePath=path,
                    parameters=detector_parameters,
                ),
                **(
                    {"image": region_image}
                    if plate_detector
                    # Reuse the already decoded source for vehicle detection as
                    # well; reopening a 4K JPEG adds a full decode and RGB copy.
                    else {"image": source}
                ),
            )
            if plate_detector:
                detections = [
                    restore_plate_coordinates(obj, window, source.size)
                    for obj in result.objects
                    if obj.class_name == "license_plate"
                ]
                plate_detections.extend(detections)
                result = result.model_copy(
                    update={
                        "source_width": source.width,
                        "source_height": source.height,
                        "objects": detections,
                    }
                )
                results.append(result)
                # Live and uploaded frames must have the same detection recall.
                # Skipping zoom passes by wall-clock parity starves small plates
                # of consecutive observations and breaks temporal confirmation.
                proposal_limit = 4
                proposal_parameters = detector_parameters
                proposal_windows = await asyncio.to_thread(
                    plate_color_proposal_windows, region_image
                )
                proposal_attempts = 0
                for proposal_index, proposal_window in enumerate(proposal_windows):
                    absolute_window = (
                        window[0] + proposal_window[0],
                        window[1] + proposal_window[1],
                        window[0] + proposal_window[2],
                        window[1] + proposal_window[3],
                    )
                    if any(
                        _detection_overlaps_window(detected, absolute_window, source.size)
                        for detected in plate_detections
                    ):
                        continue
                    if proposal_attempts >= proposal_limit:
                        break
                    proposal_attempts += 1
                    proposal = region_image.crop(proposal_window)
                    proposal_path = (
                        runner.frame_path.parent / f"plate-input-proposal-{proposal_index}.png"
                    )
                    try:
                        proposal_result = await runner.model_pool.test(
                            ModelTestRequest(
                                modelVersionId=model_id,
                                imagePath=proposal_path,
                                parameters=proposal_parameters,
                            ),
                            image=proposal,
                        )
                    finally:
                        proposal.close()
                    proposal_detections = []
                    for detected in proposal_result.objects:
                        if detected.class_name != "license_plate":
                            continue
                        restored = restore_plate_coordinates(
                            detected, absolute_window, source.size
                        )
                        attributes = dict(restored.attributes)
                        attributes.update(
                            {
                                "plateInputRegion": "COLOR_PROPOSAL",
                                "plateProposalParent": (
                                    "RULE_ROI" if is_crop else "FULL_FRAME"
                                ),
                                "plateDetectorThreshold": proposal_parameters.confidence,
                            }
                        )
                        proposal_detections.append(
                            restored.model_copy(update={"attributes": attributes})
                        )
                    results.append(
                        proposal_result.model_copy(
                            update={
                                "source_width": source.width,
                                "source_height": source.height,
                                "objects": proposal_detections,
                            }
                        )
                    )
                    plate_detections.extend(proposal_detections)
                    if proposal_detections:
                        break
            else:
                other_objects.extend(result.objects)
                results.append(result)
        enriched = []
        plates = _deduplicate_plate_detections(
            plate_detections, runner.request.parameters.nms_threshold
        )
        for index, plate in enumerate(plates[: runner.request.parameters.plate_max_candidates]):
            crop_path = runner.frame_path.parent / f"plate-crop-{index}.png"
            attrs = dict(plate.attributes)
            try:
                try:
                    crop, method = await asyncio.to_thread(rectify_plate, source, plate, 0.025)
                except ValueError:
                    attrs["plateCropStatus"] = "INVALID"
                    enriched.append(plate.model_copy(update={"attributes": attrs}))
                    continue
                attrs.update(
                    {
                        "plateCropStatus": method,
                        "plateCropWidth": crop.width,
                        "plateCropHeight": crop.height,
                        "plateCropMargin": 0.025,
                    }
                )

                async def recognize(candidate: Image.Image, path=crop_path) -> ModelTestResult:
                    return await runner.model_pool.test(
                        ModelTestRequest(
                            modelVersionId=ocr_model_id,
                            imagePath=path,
                            parameters=parameters,
                        ),
                        image=candidate,
                    )

                ocr = await recognize(crop)
                results.append(ocr)
                best = max(ocr.objects, key=lambda obj: obj.confidence, default=None)
                text = best.attributes.get("plateText") if best is not None else None
                minimum = best.attributes.get("ocrMinCharConfidence") if best is not None else None
                average = best.attributes.get("ocrConfidence") if best is not None else None
                auxiliary_sidebar = (
                    best is not None
                    and best.attributes.get("ocrLayout") == "YELLOW_SIDEBAR"
                )
                routed_site = (
                    auxiliary_sidebar
                    and best.attributes.get("ocrModelFamily") == "PPOCR_SITE"
                )

                def numeric_confidence(value: object) -> bool:
                    return (
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                        and 0 <= value <= 1
                    )

                def weak(value: object) -> bool:
                    return (
                        numeric_confidence(value)
                        and value < runner.request.parameters.ocr_min_confidence
                    )

                def strong(value: object) -> bool:
                    return (
                        numeric_confidence(value)
                        and value >= runner.request.parameters.ocr_min_confidence
                    )

                missing_province = isinstance(text, str) and is_supported_chinese_plate(
                    "京" + text
                )
                plausible_plate_fragment = (
                    isinstance(text, str)
                    and not is_supported_chinese_plate(text)
                    and 6 <= len(text) <= 9
                    and text.isalnum()
                    and any(char.isascii() and char.isalpha() for char in text)
                    and any(char.isdigit() for char in text)
                )
                low_confidence_plate = (
                    isinstance(text, str)
                    and is_supported_chinese_plate(text)
                    and (weak(minimum) or weak(average))
                )
                if auxiliary_sidebar:
                    # Never fall back to the plausible tight-crop result when
                    # the mandatory contextual retry is weak or malformed.
                    best = None
                if (
                    missing_province
                    or plausible_plate_fragment
                    or low_confidence_plate
                    or auxiliary_sidebar
                ):
                    # A complete plate body with no province, or a plate whose
                    # characters do not meet the acceptance threshold, may
                    # benefit from more source pixels around the first glyph.
                    # Site-marker plates always use this second view: their
                    # tight crop can produce a plausible, high-confidence but
                    # shortened plate such as 吉BWD001.
                    # The aspect-preserving text recognizer needs only modest
                    # context. Confirm site text in two source crop
                    # views; a confident conflicting read is not a vote.
                    retry_margin = 0.05 if routed_site else 0.10
                    wider, wider_method = await asyncio.to_thread(
                        rectify_plate, source, plate, retry_margin
                    )
                    if wider.size != crop.size:
                        retry = await recognize(wider)
                        results.append(retry)
                        alternate = max(retry.objects, key=lambda obj: obj.confidence, default=None)
                        alternate_text = (
                            alternate.attributes.get("plateText")
                            if alternate is not None else None
                        )
                        alternate_minimum = (
                            alternate.attributes.get("ocrMinCharConfidence")
                            if alternate is not None else None
                        )
                        alternate_average = (
                            alternate.attributes.get("ocrConfidence")
                            if alternate is not None else None
                        )
                        alternate_accepted = (
                            isinstance(alternate_text, str)
                            and is_supported_chinese_plate(alternate_text)
                            and (
                                not routed_site
                                or (
                                    alternate_text == text
                                    and strong(minimum)
                                    and strong(average)
                                    and strong(alternate_minimum)
                                    and strong(alternate_average)
                                )
                            )
                            and (
                                (
                                    auxiliary_sidebar
                                    and strong(alternate_average)
                                    and strong(alternate_minimum)
                                )
                                or (missing_province and not auxiliary_sidebar)
                                or (
                                    plausible_plate_fragment
                                    and strong(alternate_average)
                                    and (
                                        alternate_minimum is None
                                        or strong(alternate_minimum)
                                    )
                                )
                                or (
                                    not auxiliary_sidebar
                                    and strong(alternate_average)
                                    and (
                                        alternate_minimum is None
                                        or strong(alternate_minimum)
                                    )
                                    and (
                                        (weak(minimum) and strong(alternate_minimum))
                                        or (weak(average) and alternate_average > average)
                                    )
                                )
                            )
                        )
                        if alternate_accepted:
                            best = alternate
                            if routed_site:
                                attrs.update(
                                    {
                                        "plateCropAgreement": True,
                                        "ocrInitialMinCharConfidence": minimum,
                                        "ocrInitialConfidence": average,
                                    }
                                )
                            attrs.update(
                                {
                                    "plateCropStatus": wider_method,
                                    "plateCropWidth": wider.width,
                                    "plateCropHeight": wider.height,
                                    "plateCropMargin": retry_margin,
                                    "plateCropRetried": True,
                                }
                            )
                if best is not None:
                    attrs.update(best.attributes)
                enriched.append(plate.model_copy(update={"attributes": attrs}))
            finally:
                crop_path.unlink(missing_ok=True)
        return results, [*other_objects, *enriched]
    finally:
        region_path.unlink(missing_ok=True)
        if is_crop:
            region_image.close()
        if image is None:
            source.close()
