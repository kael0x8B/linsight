import numpy as np
import pytest

from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.plate import combine_yolo26_pose_outputs, decode_yolo26_plate_pose


def test_raw_pose_restores_four_corners_and_deduplicates_classes():
    # 1280x720 source: 0.5 resize and 140px vertical pad in a 640 canvas.
    raw = np.zeros((1, 8400, 14), dtype=np.float32)
    raw[0, 30] = [220, 295, 420, 345, .9, .1, 220, 295, 420, 295, 420, 345, 220, 345]
    raw[0, 31] = [220, 295, 420, 345, .2, .8, 220, 295, 420, 295, 420, 345, 220, 345]
    result = decode_yolo26_plate_pose(raw, 1280, 720, .5, 0, 140, .5, .5)
    assert len(result) == 1
    plate = result[0]
    assert plate.confidence == pytest.approx(.9)
    assert plate.bbox.x == pytest.approx(440 / 1280)
    assert plate.bbox.y == pytest.approx(310 / 720)
    assert plate.attributes["corner1X"] == pytest.approx(440 / 1280)
    assert plate.attributes["corner1Y"] == pytest.approx(310 / 720)
    assert plate.attributes["plateLayout"] == "SINGLE"


def test_raw_pose_rejects_unexpected_shape_and_nonfinite_predictions():
    with pytest.raises(ValueError, match="8400"):
        decode_yolo26_plate_pose(np.zeros((1, 300, 14)), 640, 640, 1, 0, 0, .5, .5)
    raw = np.zeros((1, 8400, 14), dtype=np.float32)
    raw[0, 0, 4] = np.nan
    assert decode_yolo26_plate_pose(raw, 640, 640, 1, 0, 0, .5, .5) == []


def test_split_pose_output_reassembles_without_mixing_quantization_scales():
    parts = [np.zeros((1, 8400, width), dtype=np.float32) for width in (4, 2, 8)]
    parts[1][0, 20, 0] = .8
    combined = combine_yolo26_pose_outputs(parts)
    assert combined.shape == (1, 8400, 14)
    assert combined[0, 20, 4] == pytest.approx(.8)
    with pytest.raises(ValueError, match="three split"):
        combine_yolo26_pose_outputs(parts[:2])


def test_raw_pose_manifest_fixes_cpu_and_npu_preprocessing():
    common = {
        "schemaVersion": "1.0", "taskType": "OBJECT_DETECTION",
        "preprocess": {
            "inputWidth": 640, "inputHeight": 640, "color": "RGB",
            "layout": "NCHW", "dtype": "FLOAT32", "scale": 1 / 255,
            "resize": "LETTERBOX",
        },
        "decoder": {"type": "YOLO26_PLATE_POSE"},
    }
    RuntimeManifest.model_validate(common)
    npu = {**common, "preprocess": {**common["preprocess"],
                                    "layout": "NHWC", "dtype": "UINT8", "scale": 1.0}}
    RuntimeManifest.model_validate(npu)
    bad = {**common, "preprocess": {**common["preprocess"], "resize": "STRETCH"}}
    with pytest.raises(ValueError, match="fixed export contract"):
        RuntimeManifest.model_validate(bad)
