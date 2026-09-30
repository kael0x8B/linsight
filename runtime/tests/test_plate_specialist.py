import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.model.contracts import DetectionObject, ModelTestParameters, ModelTestResult
from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.plate import (
    PLATE_CHARACTERS,
    decode_chinese_plate_ctc,
    decode_yolo_plate,
    plate_number_region,
    rectify_plate,
)
from ai_runtime.app.task.contracts import TaskInferenceParameters
from ai_runtime.app.task.manager import TaskRunner
from ai_runtime.app.task.plate_pipeline import (
    _deduplicate_plate_detections,
    infer_license_plates,
    plate_color_proposal_windows,
)


def plate(text="粤BF27861", track="one", **attrs):
    return DetectionObject.model_validate(
        {
            "class": "license_plate",
            "confidence": 0.9,
            "trackId": track,
            "bbox": {"x": 0.2, "y": 0.4, "width": 0.6, "height": 0.2},
            "attributes": {"plateText": text, "ocrConfidence": 0.95, **attrs},
        }
    )


def test_normalized_plate_boxes_are_deduplicated_by_iou():
    full_frame = plate()
    full_frame.confidence = 0.76
    full_frame.bbox.x = 0.229
    full_frame.bbox.y = 0.335
    full_frame.bbox.width = 0.068
    full_frame.bbox.height = 0.059
    proposal = full_frame.model_copy(deep=True)
    proposal.confidence = 0.83
    proposal.bbox.x = 0.228
    proposal.bbox.y = 0.336
    proposal.bbox.width = 0.067
    proposal.bbox.height = 0.057

    result = _deduplicate_plate_detections([full_frame, proposal], 0.5)

    assert result == [proposal]


def test_complete_full_frame_plate_wins_over_higher_scoring_partial_zoom():
    full_frame = plate(plateInputRegion="FULL_FRAME")
    full_frame.confidence = 0.82
    full_frame.bbox.x = 0.289
    full_frame.bbox.y = 0.275
    full_frame.bbox.width = 0.076
    full_frame.bbox.height = 0.049
    partial_zoom = full_frame.model_copy(deep=True)
    partial_zoom.confidence = 0.89
    partial_zoom.bbox.x = 0.302
    partial_zoom.bbox.width = 0.064
    partial_zoom.attributes["plateInputRegion"] = "COLOR_PROPOSAL"

    result = _deduplicate_plate_detections([partial_zoom, full_frame], 0.5)

    assert result == [full_frame]


def test_detector_restores_letterbox_landmarks_and_uses_joint_score():
    # 1280x720 source: scale .5 and vertical padding 140.
    row = [320, 320, 200, 50, 0.9, 220, 295, 420, 295, 420, 345, 220, 345, 0.8, 0.1]
    duplicate = row.copy()
    duplicate[4] = 0.8
    rejected = row.copy()
    rejected[13] = 0.4  # Objectness alone must not pass the threshold.
    result = decode_yolo_plate(
        np.array([[row, duplicate, rejected]]), 1280, 720, 0.5, 0, 140, 0.5, 0.5
    )
    assert len(result) == 1
    assert result[0].confidence == pytest.approx(0.72)
    assert result[0].bbox.x == pytest.approx(440 / 1280)
    assert result[0].attributes["corner1Y"] == pytest.approx(310 / 720)
    assert result[0].attributes["plateLayout"] == "SINGLE"


def test_specialist_ctc_repeated_characters_blank_and_colour():
    text = "皖AA1122"
    indices = [0]
    for char in text:
        indices.extend([PLATE_CHARACTERS.index(char)] * 2 + [0])
    logits = np.full((1, len(indices), len(PLATE_CHARACTERS)), -15.0)
    for t, index in enumerate(indices):
        logits[0, t, index] = 15
    result = decode_chinese_plate_ctc(logits, np.array([[0, 0, 0, 0, 10]]))[0]
    assert result.attributes["plateText"] == text
    assert result.attributes["plateColor"] == "YELLOW"
    assert result.attributes["ocrMinCharConfidence"] > 0.99
    with pytest.raises(ValueError, match="non-finite"):
        decode_chinese_plate_ctc(logits * np.nan, np.zeros((1, 5)))


def test_rectification_orders_corners_and_falls_back_for_degenerate_geometry():
    source = Image.new("RGB", (200, 100), (30, 60, 90))
    # Bottom-right, top-left, bottom-left, top-right: valid but shuffled.
    corners = [(0.8, 0.6), (0.2, 0.4), (0.2, 0.6), (0.8, 0.4)]
    attrs = {
        f"corner{i + 1}{axis}": point[j]
        for i, point in enumerate(corners)
        for j, axis in enumerate(("X", "Y"))
    }
    crop, method = rectify_plate(source, plate(**attrs))
    assert method == "PERSPECTIVE"
    assert crop.size == (121, 20) or crop.size == (120, 20)
    assert crop.getpixel((50, 10)) == (30, 60, 90)
    padded, method = rectify_plate(source, plate(**attrs), margin=0.025)
    assert method == "PERSPECTIVE"
    assert padded.width > crop.width and padded.height > crop.height
    with pytest.raises(ValueError, match="margin"):
        rectify_plate(source, plate(**attrs), margin=0.21)
    attrs["corner3X"], attrs["corner3Y"] = corners[0]
    fallback, method = rectify_plate(source, plate(**attrs))
    assert method == "BOUNDING_BOX"
    assert fallback.width > fallback.height


def test_double_line_crop_is_split_and_combined_in_reading_order():
    source = Image.new("RGB", (200, 100), "blue")
    source.paste("red", (0, 0, 200, 48))
    crop, method = rectify_plate(source, plate(plateLayout="DOUBLE"))
    assert method == "BOUNDING_BOX_DOUBLE_LINE"
    assert crop.width > 200
    assert crop.getpixel((20, 1)) == (255, 0, 0)
    assert crop.getpixel((crop.width - 20, crop.height - 2)) == (0, 0, 255)


def test_model_manifests_reject_wrong_preprocessing_and_task_pair():
    catalog = json.loads(
        (Path(__file__).parents[1] / "model_assets/chinese-plate-specialist-v1.json").read_text()
    )
    for model in catalog["models"]:
        manifest = model["runtimeManifest"]
        RuntimeManifest.model_validate(manifest)
        with pytest.raises(ValueError, match="preprocessing"):
            RuntimeManifest.model_validate(
                {
                    **manifest,
                    "preprocess": {
                        **manifest["preprocess"],
                        "color": "BGR" if model == catalog["models"][0] else "RGB",
                    },
                }
            )


def test_auxiliary_column_is_removed_only_when_pixels_support_it():
    # Two yellow rows on the left, white province/number on green background.
    image = Image.new("RGB", (168, 48), (20, 100, 90))
    image.paste((150, 155, 40), (8, 6, 18, 18))
    image.paste((150, 155, 40), (8, 28, 18, 40))
    image.paste("white", (23, 5, 35, 42))
    crop, offset = plate_number_region(image)
    assert offset == 18
    assert crop.getpixel((5, 10)) == (255, 255, 255)  # Province retained.
    for background in ["yellow", "blue", "white", (20, 100, 90)]:
        normal = Image.new("RGB", (168, 48), background)
        assert plate_number_region(normal)[1] == 0
    # A small yellow reflection is insufficient; do not amputate a standard plate.
    standard = Image.new("RGB", (168, 48), "blue")
    standard.paste("yellow", (8, 10, 18, 14))
    assert plate_number_region(standard)[1] == 0


def test_thin_low_resolution_auxiliary_column_is_still_removed():
    image = Image.new("RGB", (149, 45), (20, 100, 90))
    # At the live camera's plate size, only a six-pixel-high fragment of one
    # yellow sidebar glyph survives perspective correction and compression.
    image.paste((150, 155, 40), (12, 18, 16, 24))
    image.paste("white", (20, 5, 32, 40))
    crop, offset = plate_number_region(image)
    assert offset == 16
    assert crop.size == (133, 45)
    assert crop.getpixel((5, 10)) == (255, 255, 255)


def test_dim_stacked_glyphs_do_not_authorize_destructive_trimming():
    image = Image.new("RGB", (149, 45), (0, 25, 0))
    image.paste((70, 95, 70), (5, 8, 16, 18))
    image.paste((70, 95, 70), (5, 24, 16, 35))
    image.paste((85, 105, 80), (21, 7, 33, 37))
    crop, offset = plate_number_region(image)
    assert offset == 0
    assert crop.size == image.size

    # A normal full-height province glyph followed by the city letter is not a
    # stacked auxiliary marker and must remain intact.
    standard = Image.new("RGB", (149, 45), (0, 25, 0))
    standard.paste((70, 95, 70), (5, 7, 17, 37))
    standard.paste((85, 105, 80), (22, 7, 34, 37))
    assert plate_number_region(standard)[1] == 0


@pytest.mark.parametrize("background", [(0, 40, 140), (0, 65, 45)])
@pytest.mark.parametrize(
    "glyph",
    [
        # 吉、晋、鲁 have separated radicals just like a stacked marker.
        "00100 00100 11111 00100 11111 00000 11111 10001 10001 10001 11111".split(),
        "11111 01010 11011 01010 11111 00000 11111 10001 11111 10001 11111".split(),
        "00100 01110 10001 11111 10101 11111 00000 11111 10001 11111 10001 11111".split(),
    ],
    ids=["ji", "jin", "lu"],
)
def test_standard_province_radicals_remain_on_blue_and_green_plates(background, glyph):
    image = Image.new("RGB", (200, 48), background)
    for row, values in enumerate(glyph):
        for column, value in enumerate(values):
            if value == "1":
                left, top = 6 + column * 3, 5 + row * 3
                image.paste("white", (left, top, left + 3, top + 3))
    image.paste("white", (34, 5, 50, 42))
    crop, offset = plate_number_region(image)
    assert offset == 0
    np.testing.assert_array_equal(np.asarray(crop), np.asarray(image))


def test_scattered_yellow_compression_fringes_do_not_remove_province():
    # Observed on a standard 80x30 blue plate: three separated columns of
    # yellow colour bleed were incorrectly counted as an auxiliary marker.
    image = Image.new("RGB", (80, 30), (0, 40, 140))
    image.paste("white", (2, 5, 11, 25))
    for column in (1, 6, 7):
        image.paste((150, 155, 40), (column, 8, column + 1, 17))
    image.paste("white", (16, 5, 24, 25))
    crop, offset = plate_number_region(image)
    assert offset == 0
    np.testing.assert_array_equal(np.asarray(crop), np.asarray(image))


@pytest.mark.parametrize("scale", [0.8, 1, 1.4])
def test_weak_yellow_marker_requires_two_compact_colored_rows(scale):
    image = Image.new("RGB", (149, 45), (0, 65, 45))
    # Chroma loss pushes r/b below the strict yellow threshold; both stacked
    # glyphs still provide positive colour evidence distinct from white text.
    image.paste((126, 173, 102), (5, 8, 16, 18))
    image.paste((126, 173, 102), (5, 25, 16, 35))
    image.paste("white", (22, 5, 34, 40))
    image = image.resize(
        (round(149 * scale), round(45 * scale)), Image.Resampling.BILINEAR
    )
    crop, offset = plate_number_region(image)
    assert 14 * scale <= offset <= 18 * scale
    assert crop.getpixel((round(26 * scale) - offset, round(20 * scale))) == (255, 255, 255)
    assert plate_number_region(crop)[1] == 0


def test_weak_yellow_single_glyph_and_yellow_plate_are_not_sidebars():
    image = Image.new("RGB", (149, 45), (0, 65, 45))
    image.paste((126, 173, 102), (5, 8, 16, 18))
    image.paste("white", (22, 5, 34, 40))
    assert plate_number_region(image)[1] == 0
    yellow_plate = Image.new("RGB", (149, 45), (126, 173, 102))
    assert plate_number_region(yellow_plate)[1] == 0


@pytest.mark.parametrize("lower_width,expected_offset", [(5, 0), (6, 20)])
def test_compressed_marker_requires_at_least_half_width_in_both_rows(
    lower_width, expected_offset
):
    # Real field crop: twelve columns survive in the upper marker glyph, while
    # only six columns survive below it. Five scattered columns are insufficient.
    image = Image.new("RGB", (200, 60), (0, 65, 45))
    image.paste((126, 173, 102), (8, 12, 20, 23))
    image.paste((126, 173, 102), (20 - lower_width, 36, 20, 42))
    image.paste("white", (27, 8, 42, 51))
    crop, offset = plate_number_region(image)
    assert offset == expected_offset
    assert crop.getpixel((30 - offset, 20)) == (255, 255, 255)


def test_plate_votes_survive_vehicle_context_changes_and_candidates_stay_visible():
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0", ocrMinVotes=3),
    )
    for i, vehicle in enumerate(["vehicle-1", None, "vehicle-2"]):
        obj = plate("吉WD0011", vehicleTrackId=vehicle)
        result = processor.after_tracking([obj], i * 250)
        assert result[0].attributes["visibleByDefault"] is True
        assert bool(processor.event_candidates(result)) == (i == 2)
    assert result[0].attributes["plateNumber"] == "吉WD0011"


@pytest.mark.parametrize(
    "text,attrs",
    [
        ("11:07:17", {}),
        ("110717", {}),
        ("2026-09-21", {}),
        ("川GH", {}),
        ("", {}),
        ("吉WD0011", {"ocrConfidence": 0.6}),
        ("贵WD0011", {"ocrMinCharConfidence": 0.58}),
        ("吉WD0011", {"ocrConfidence": None}),
    ],
)
def test_unverified_plate_candidates_do_not_draw_boxes_or_emit_events(text, attrs):
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0"),
    )
    for time in range(0, 2000, 250):
        result = processor.after_tracking([plate(text, **attrs)], time)
        assert len(result) == 1  # Keep raw candidates available for diagnostics.
        assert result[0].attributes["visibleByDefault"] is False
        assert "plateNumber" not in result[0].attributes
        assert not processor.event_candidates(result)


def test_plate_display_bridges_brief_ocr_loss_without_confirming_stale_text():
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0"),
    )
    for time in (0, 250, 500):
        result = processor.after_tracking([plate()], time)
    assert processor.event_candidates(result)
    for time in (750, 1250):
        result = processor.after_tracking([plate("贵WD0011", ocrConfidence=0.5)], time)
        assert result[0].attributes["visibleByDefault"] is True
        assert "plateNumber" not in result[0].attributes
        assert not processor.event_candidates(result)
    # Bad OCR cannot refresh visibility indefinitely, even on the same track.
    result = processor.after_tracking([plate("贵WD0011", ocrConfidence=0.5)], 1501)
    assert result[0].attributes["visibleByDefault"] is False
    # Reacquire immediately when fresh, qualified plate evidence returns.
    result = processor.after_tracking([plate()], 1750)
    assert result[0].attributes["visibleByDefault"] is True
    assert not processor.event_candidates(result)
    # Explicit non-plate text is hidden immediately, not held as a plate.
    result = processor.after_tracking([plate("11:07:17")], 2000)
    assert result[0].attributes["visibleByDefault"] is False


def test_plate_display_history_is_track_local_and_expires_on_clock_rollback():
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0"),
    )
    processor.after_tracking([plate()], 1000)
    assert not processor.after_tracking(
        [plate(track="other", ocrConfidence=0.5)], 1250
    )[0].attributes["visibleByDefault"]
    assert not processor.after_tracking(
        [plate(ocrConfidence=0.5)], 750
    )[0].attributes["visibleByDefault"]


def test_moving_plate_keeps_identity_without_box_overlap_and_expires_after_outage():
    from ai_runtime.app.capability.tracker import IoUTracker

    tracker = IoUTracker(motion_classes=frozenset({"license_plate"}))
    tracks = []
    for i in range(4):
        obj = plate("吉WD0011")
        obj.bbox.x, obj.bbox.width = 0.05 + i * 0.15, 0.1
        tracks.append(tracker.update([obj], i * 250)[0].track_id)
    assert len(set(tracks)) == 1
    assert tracker.update([obj], 2500)[0].track_id != tracks[-1]
    tracker.reset()
    assert not tracker._tracks


def test_motion_tracker_does_not_merge_different_or_ambiguous_plates():
    from ai_runtime.app.capability.tracker import IoUTracker

    tracker = IoUTracker(motion_classes=frozenset({"license_plate"}))
    first = plate("吉WD0011")
    first.bbox.x, first.bbox.width = 0.1, 0.1
    initial = tracker.update([first], 0)[0].track_id
    different = plate("皖A12345")
    different.bbox.x, different.bbox.width = 0.25, 0.1
    assert tracker.update([different], 250)[0].track_id != initial
    tracker.reset()
    initial = tracker.update([first], 500)[0].track_id
    left, right = first.model_copy(deep=True), first.model_copy(deep=True)
    left.bbox.x, right.bbox.x = 0.25, 0.27
    result = tracker.update([left, right], 750)
    assert all(obj.track_id != initial for obj in result)


def test_pipeline_crops_roi_at_source_resolution_without_vehicle_detection(tmp_path):
    source = Image.new("RGB", (1000, 500), (12, 34, 56))
    path = tmp_path / "frame.jpg"
    Image.new("RGB", source.size, "white").save(path)
    calls = []

    class Pool:
        async def test(self, request, **kwargs):
            with kwargs["image"].copy() as crop:
                size = crop.size
                calls.append((request.model_version_id, size))
                if request.model_version_id != 1:
                    assert crop.getpixel((crop.width // 2, crop.height // 2)) == (12, 34, 56)
                    assert not request.image_path.exists()
            objects = [] if request.model_version_id == 1 else [plate()]
            return ModelTestResult(
                sourceWidth=size[0],
                sourceHeight=size[1],
                objects=objects,
                backend="TEST",
                device="CPU",
                preprocessMillis=0,
                inferenceMillis=1,
                postprocessMillis=0,
            )

    params = TaskInferenceParameters(schemaVersion="1.0", plateUseRuleRoi=True)
    runner = SimpleNamespace(
        frame_path=path,
        model_pool=Pool(),
        request=SimpleNamespace(
            parameters=params,
            model_bindings={"vehicle": 1, "plate": 2, "ocr": 3},
            rule=SimpleNamespace(
                regions=[
                    SimpleNamespace(
                        points=[
                            SimpleNamespace(x=0.2, y=0.2),
                            SimpleNamespace(x=0.8, y=0.8),
                        ]
                    )
                ]
            ),
            pipeline={
                "nodes": [
                    {"id": "vehicle", "capabilityKey": "detector.vehicle"},
                    {"id": "plate", "capabilityKey": "detector.license-plate"},
                    {"id": "ocr", "capabilityKey": "ocr.license-plate"},
                ]
            },
        ),
    )
    results, objects = asyncio.run(TaskRunner._infer_frame(runner, source))
    assert (2, (616, 316)) in calls
    assert objects[0].bbox.x == pytest.approx((192 + 0.2 * 616) / 1000)
    assert results[0].source_width == 1000 and results[0].source_height == 500
    assert objects[0].attributes["plateText"] == "粤BF27861"
    assert not list(tmp_path.glob("plate-*.png"))


def test_plate_color_proposal_prioritizes_a_small_plate_over_a_large_yellow_box():
    source = Image.new("RGB", (1104, 620), (96, 96, 96))
    source.paste((28, 132, 88), (335, 155, 394, 177))
    source.paste((212, 150, 18), (730, 370, 860, 420))

    windows = plate_color_proposal_windows(source)

    assert windows
    left, top, right, bottom = windows[0]
    assert left <= 335 and top <= 155 and right >= 394 and bottom >= 177
    assert right - left < source.width / 3
    assert bottom - top < source.height / 3


def test_live_plate_pipeline_reuses_4k_pixels_for_detectors_and_ocr(tmp_path):
    source = Image.new("RGB", (3840, 2160), (96, 96, 96))
    # One-pixel strokes cannot survive a hidden 4K -> 1080p -> 4K round trip.
    for x in range(960, 1152):
        source.putpixel((x, 891), (255, 255, 255) if x % 2 else (0, 0, 0))
    path = tmp_path / "frame.png"
    source.save(path)
    source.close()
    detector_images = []
    ocr_sizes = []

    class Pool:
        async def test(self, request, **kwargs):
            image = kwargs["image"]
            if request.model_version_id in {1, 2}:
                assert image.size == (3840, 2160)
                detector_images.append(image)
                objects = []
                if request.model_version_id == 2:
                    objects = [DetectionObject.model_validate({
                        "class": "license_plate", "confidence": 0.9,
                        "bbox": {"x": 0.25, "y": 0.4, "width": 0.05, "height": 0.025},
                    })]
            else:
                ocr_sizes.append(image.size)
                assert image.width > 192 and image.height > 54
                assert set(np.asarray(image)[30, 12:192, 0]) == {0, 255}
                objects = [plate("吉WD0011", ocrMinCharConfidence=0.99)]
            return ModelTestResult(
                sourceWidth=image.width, sourceHeight=image.height, objects=objects,
                backend="TEST", device="CPU", preprocessMillis=0,
                inferenceMillis=1, postprocessMillis=0,
            )

    runner = SimpleNamespace(
        frame_path=path,
        model_pool=Pool(),
        request=SimpleNamespace(
            parameters=TaskInferenceParameters(schemaVersion="1.0"),
            model_bindings={"vehicle": 1, "plate": 2},
        ),
    )
    model_params = ModelTestParameters(
        schemaVersion="1.0", confidence=0.5, nmsThreshold=0.5,
        inputWidth=640, inputHeight=640, outputCoordinates="NORMALIZED_XYWH",
    )
    results, objects = asyncio.run(infer_license_plates(
        runner, {"vehicle", "plate"},
        {"vehicle": "detector.vehicle", "plate": "detector.license-plate"},
        3, model_params, None,
    ))
    assert detector_images[0] is detector_images[1]
    assert len(ocr_sizes) == 1
    assert results[0].source_width == 3840 and results[0].source_height == 2160
    assert objects[0].bbox.x == pytest.approx(0.25)
    assert objects[0].attributes["plateText"] == "吉WD0011"


@pytest.mark.parametrize("file_backed", [False, True], ids=["in_memory", "file_backed"])
def test_plate_pipeline_retries_a_zoomed_color_proposal_after_full_frame_miss(
    tmp_path, monkeypatch, file_backed
):
    source = Image.new("RGB", (1000, 500), (90, 90, 90))
    source.paste((25, 135, 86), (300, 100, 360, 120))
    source.save(tmp_path / "frame.png")
    # The first plausible colour window misses. The live file-backed path must
    # try the second window just as the uploaded-image path does, on every frame.
    monkeypatch.setattr(
        "ai_runtime.app.task.plate_pipeline.plate_color_proposal_windows",
        lambda _: [(50, 50, 140, 90), (280, 80, 380, 140)],
    )
    monkeypatch.setattr("time.monotonic", lambda: 1.0)
    calls = []

    class Pool:
        async def test(self, request, **kwargs):
            image = kwargs["image"]
            calls.append((request.model_version_id, image.size))
            objects = []
            if request.model_version_id == 1 and image.size == (100, 60):
                objects = [
                    DetectionObject.model_validate(
                        {
                            "class": "license_plate",
                            "confidence": 0.82,
                            "bbox": {"x": 0.35, "y": 0.4, "width": 0.3, "height": 0.2},
                            "attributes": {
                                "corner1X": 0.35,
                                "corner1Y": 0.4,
                                "corner2X": 0.65,
                                "corner2Y": 0.4,
                                "corner3X": 0.65,
                                "corner3Y": 0.6,
                                "corner4X": 0.35,
                                "corner4Y": 0.6,
                            },
                        }
                    )
                ]
            elif request.model_version_id == 2:
                objects = [plate("吉WD0011")]
            return ModelTestResult(
                sourceWidth=image.width,
                sourceHeight=image.height,
                objects=objects,
                backend="TEST",
                device="CPU",
                preprocessMillis=0,
                inferenceMillis=1,
                postprocessMillis=0,
            )

    runner = SimpleNamespace(
        frame_path=tmp_path / "frame.png",
        model_pool=Pool(),
        request=SimpleNamespace(
            parameters=TaskInferenceParameters(schemaVersion="1.0"),
            model_bindings={"plate": 1},
            rule=None,
        ),
    )
    model_params = ModelTestParameters(
        schemaVersion="1.0",
        confidence=0.5,
        nmsThreshold=0.5,
        inputWidth=640,
        inputHeight=640,
        outputCoordinates="NORMALIZED_XYWH",
    )

    results, objects = asyncio.run(
        infer_license_plates(
            runner,
            {"plate"},
            {"plate": "detector.license-plate"},
            2,
            model_params,
            None if file_backed else source,
        )
    )

    assert len(results) == 4
    assert calls[0] == (1, source.size)
    assert calls[1] == (1, (90, 40))
    assert calls[2] == (1, (100, 60))
    assert calls[3][0] == 2
    assert objects[0].attributes["plateInputRegion"] == "COLOR_PROPOSAL"
    assert objects[0].attributes["plateProposalParent"] == "FULL_FRAME"
    assert objects[0].attributes["plateText"] == "吉WD0011"


def test_plate_detector_uses_ocr_guarded_confidence_floor(tmp_path):
    source = Image.new("RGB", (1000, 500), (90, 90, 90))
    confidences = []

    class Pool:
        async def test(self, request, **kwargs):
            confidences.append((request.model_version_id, request.parameters.confidence))
            image = kwargs["image"]
            return ModelTestResult(
                sourceWidth=image.width,
                sourceHeight=image.height,
                objects=[],
                backend="TEST",
                device="CPU",
                preprocessMillis=0,
                inferenceMillis=1,
                postprocessMillis=0,
            )

    runner = SimpleNamespace(
        frame_path=tmp_path / "frame.png",
        model_pool=Pool(),
        request=SimpleNamespace(
            parameters=TaskInferenceParameters(schemaVersion="1.0"),
            model_bindings={"vehicle": 1, "plate": 2},
            rule=None,
        ),
    )
    model_params = ModelTestParameters(
        schemaVersion="1.0",
        confidence=0.5,
        nmsThreshold=0.5,
        inputWidth=640,
        inputHeight=640,
        outputCoordinates="NORMALIZED_XYWH",
    )

    asyncio.run(
        infer_license_plates(
            runner,
            {"vehicle", "plate"},
            {"vehicle": "detector.vehicle", "plate": "detector.license-plate"},
            3,
            model_params,
            source,
        )
    )

    assert confidences[0] == (2, 0.25)
    assert confidences[-1] == (1, 0.5)


@pytest.mark.parametrize(
    "first_text,first_minimum,retry_minimum,expected_text,expected_passes,retry_accepted",
    [
        ("BF27861", 0.95, 0.95, "辽BF27861", 2, True),
        ("NK25662D", 0.45, 0.95, "辽BF27861", 2, True),
        ("闽BF27861", 0.24, 0.95, "辽BF27861", 2, True),
        ("闽BF27861", 0.24, 0.55, "闽BF27861", 2, False),
        ("辽BF27861", 0.95, 0.95, "辽BF27861", 1, False),
        ("11:07:17", 0.24, 0.95, "11:07:17", 1, False),
    ],
)
def test_plate_pipeline_retries_wider_source_crop_for_missing_or_uncertain_province(
    tmp_path, first_text, first_minimum, retry_minimum,
    expected_text, expected_passes, retry_accepted,
):
    source = Image.new("RGB", (200, 100), "green")
    corners = {
        "corner1X": 0.2, "corner1Y": 0.4,
        "corner2X": 0.8, "corner2Y": 0.4,
        "corner3X": 0.8, "corner3Y": 0.6,
        "corner4X": 0.2, "corner4Y": 0.6,
    }
    detected = DetectionObject.model_validate({
        "class": "license_plate", "confidence": 0.9,
        "bbox": {"x": 0.2, "y": 0.4, "width": 0.6, "height": 0.2},
        "attributes": corners,
    })
    ocr_sizes = []

    class Pool:
        async def test(self, request, **kwargs):
            image = kwargs["image"]
            if request.model_version_id == 1:
                objects = [detected]
            else:
                ocr_sizes.append(image.size)
                text = first_text if image.width < 140 else "辽BF27861"
                minimum = first_minimum if image.width < 140 else retry_minimum
                objects = [plate(text, ocrMinCharConfidence=minimum)]
            return ModelTestResult(
                sourceWidth=image.width, sourceHeight=image.height,
                objects=objects, backend="TEST", device="CPU",
                preprocessMillis=0, inferenceMillis=1, postprocessMillis=0,
            )

    params = TaskInferenceParameters(schemaVersion="1.0", plateUseRuleRoi=False)
    runner = SimpleNamespace(
        frame_path=tmp_path / "frame.png", model_pool=Pool(),
        request=SimpleNamespace(
            parameters=params, model_bindings={"plate": 1}, rule=None,
        ),
    )
    model_params = ModelTestParameters(
        schemaVersion="1.0", confidence=0.5, nmsThreshold=0.5,
        inputWidth=640, inputHeight=640, outputCoordinates="NORMALIZED_XYWH",
    )
    results, objects = asyncio.run(infer_license_plates(
        runner, {"plate"}, {"plate": "detector.license-plate"}, 2, model_params, source,
    ))
    assert len(results) == expected_passes + 1  # Detector and measured OCR attempts.
    assert len(ocr_sizes) == expected_passes
    if expected_passes == 2:
        assert ocr_sizes[1][0] > ocr_sizes[0][0]
    assert objects[0].attributes["plateText"] == expected_text
    assert objects[0].attributes.get("plateCropRetried", False) == retry_accepted
    assert objects[0].attributes["plateCropMargin"] == (0.10 if retry_accepted else 0.025)


@pytest.mark.parametrize(
    "family, initial_text, retry_text, initial_min, retry_min, expected, margin",
    [
        ("SPECIALIST", "吉BWD001", "吉WD0011", 0.99, 0.98, "吉WD0011", 0.10),
        ("PPOCR_SITE", "吉WD0010", "吉WD0010", 0.99, 0.98, "吉WD0010", 0.05),
        ("PPOCR_SITE", "吉VD0010", "吉WD0010", 0.99, 0.98, None, None),
        ("PPOCR_SITE", "吉WD0010", "吉WD0010", 0.69, 0.98, None, None),
        ("PPOCR_SITE", "吉WD0010", "吉WD0010", 0.99, 0.69, None, None),
    ],
)
def test_plate_pipeline_uses_context_retry_for_site_plate_sidebar(
    tmp_path, family, initial_text, retry_text, initial_min, retry_min, expected, margin,
):
    source = Image.new("RGB", (200, 100), "green")
    corners = {
        "corner1X": 0.2, "corner1Y": 0.4,
        "corner2X": 0.8, "corner2Y": 0.4,
        "corner3X": 0.8, "corner3Y": 0.6,
        "corner4X": 0.2, "corner4Y": 0.6,
    }
    detected = DetectionObject.model_validate({
        "class": "license_plate", "confidence": 0.9,
        "bbox": {"x": 0.2, "y": 0.4, "width": 0.6, "height": 0.2},
        "attributes": corners,
    })
    ocr_sizes = []

    class Pool:
        async def test(self, request, **kwargs):
            image = kwargs["image"]
            if request.model_version_id == 1:
                objects = [detected]
            else:
                ocr_sizes.append(image.size)
                if len(ocr_sizes) == 1:
                    objects = [plate(
                        initial_text,
                        ocrConfidence=0.99,
                        ocrMinCharConfidence=initial_min,
                        ocrLayout="YELLOW_SIDEBAR",
                        ocrModelFamily=family,
                    )]
                else:
                    objects = [plate(
                        retry_text,
                        ocrConfidence=0.98,
                        ocrMinCharConfidence=retry_min,
                        ocrLayout="YELLOW_SIDEBAR",
                        ocrModelFamily=family,
                    )]
            return ModelTestResult(
                sourceWidth=image.width, sourceHeight=image.height,
                objects=objects, backend="TEST", device="CPU",
                preprocessMillis=0, inferenceMillis=1, postprocessMillis=0,
            )

    runner = SimpleNamespace(
        frame_path=tmp_path / "frame.png", model_pool=Pool(),
        request=SimpleNamespace(
            parameters=TaskInferenceParameters(schemaVersion="1.0", plateUseRuleRoi=False),
            model_bindings={"plate": 1}, rule=None,
        ),
    )
    model_params = ModelTestParameters(
        schemaVersion="1.0", confidence=0.5, nmsThreshold=0.5,
        inputWidth=640, inputHeight=640, outputCoordinates="NORMALIZED_XYWH",
    )
    results, objects = asyncio.run(infer_license_plates(
        runner, {"plate"}, {"plate": "detector.license-plate"}, 2, model_params, source,
    ))
    assert len(results) == 3
    assert len(ocr_sizes) == 2
    assert ocr_sizes[1][0] > ocr_sizes[0][0]
    if expected is None:
        assert "plateText" not in objects[0].attributes
    else:
        assert objects[0].attributes["plateText"] == expected
        assert objects[0].attributes["plateCropRetried"] is True
        assert objects[0].attributes["plateCropMargin"] == margin
        if family == "PPOCR_SITE":
            assert objects[0].attributes["plateCropAgreement"] is True
            assert objects[0].attributes["ocrInitialMinCharConfidence"] == initial_min


def test_vote_window_includes_frames_where_plate_is_missing():
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0", ocrMinVotes=3, ocrVoteFrames=5),
    )
    for time in (0, 100):
        assert not processor.event_candidates(processor.after_tracking([plate()], time))
    for time in (200, 300, 400):
        processor.after_tracking([], time)
    assert not processor.event_candidates(processor.after_tracking([plate()], 500))
    assert not processor.event_candidates(processor.after_tracking([plate()], 600))
    assert processor.event_candidates(processor.after_tracking([plate()], 700))


def test_tied_numbers_never_confirm_and_vehicles_do_not_share_votes():
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0", ocrMinVotes=2, ocrVoteFrames=5),
    )
    for i, text in enumerate(["皖A12345", "皖A54321", "皖A12345", "皖A54321"]):
        result = processor.after_tracking([plate(text)], i * 100)
    assert not processor.event_candidates(result)
    assert not processor.event_candidates(processor.after_tracking([plate(track="two")], 500))


def test_weak_character_cannot_be_hidden_by_high_average_or_repeated_votes():
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0", ocrMinVotes=3, ocrVoteFrames=5),
    )
    # Node 1's nonstandard 场内 test plate: high mean, uncertain province/letter.
    for time in range(5):
        result = processor.after_tracking(
            [plate("贵WD0011", ocrConfidence=0.938, ocrMinCharConfidence=0.583)], time
        )
        assert result[0].attributes["ocrStatus"] == "LOW_CHAR_CONFIDENCE"
        assert not processor.event_candidates(result)
    for time in range(5, 8):
        result = processor.after_tracking([plate(ocrMinCharConfidence=0.99)], time)
        assert bool(processor.event_candidates(result)) == (time == 7)
    for value in (float("nan"), float("inf"), True, None, "0.99"):
        result = processor.after_tracking([plate(ocrMinCharConfidence=value)], 8)
        assert result[0].attributes["ocrStatus"] == "INVALID_CONFIDENCE"
        assert not processor.event_candidates(result)


def test_context_retried_site_plate_keeps_configured_character_floor():
    processor = CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0", ocrMinVotes=3, ocrVoteFrames=5),
    )
    attributes = {
        "ocrConfidence": 0.95,
        "ocrMinCharConfidence": 0.98,
        "ocrLayout": "YELLOW_SIDEBAR",
        "plateCropRetried": True,
    }
    for time in range(3):
        result = processor.after_tracking([plate("吉WD0011", **attributes)], time)
        assert bool(processor.event_candidates(result)) == (time == 2)
    assert result[0].attributes["plateNumber"] == "吉WD0011"

    for attrs in (
        {**attributes, "plateCropRetried": False, "ocrMinCharConfidence": 0.68},
        {**attributes, "ocrLayout": "STANDARD", "ocrMinCharConfidence": 0.68},
        {**attributes, "ocrMinCharConfidence": 0.68},
        {**attributes, "ocrMinCharConfidence": 0.64},
    ):
        isolated = CapabilityPostprocessor(
            {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
            TaskInferenceParameters(schemaVersion="1.0"),
        )
        rejected = isolated.after_tracking([plate("吉WD0011", **attrs)], 0)
        assert rejected[0].attributes["ocrStatus"] == "LOW_CHAR_CONFIDENCE"
        assert not isolated.event_candidates(rejected)
