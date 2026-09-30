import pytest

from ai_runtime.app.capability.postprocess import CapabilityPostprocessor, is_supported_chinese_plate
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.task.contracts import TaskInferenceParameters


@pytest.mark.parametrize("text", [
    "浙H05516", "川AD0992", "皖AD12345",
    "川J3636挂", "川F8000挂", "皖J6879挂", "鲁HA123挂", "苏B12AB挂",
])
def test_standard_and_trailer_plate_formats(text):
    assert is_supported_chinese_plate(text)


@pytest.mark.parametrize("text", [
    "川J363挂", "川J36366挂", "川JABCD挂", "川JABC1挂",
    "川JI123挂", "川JO123挂", "川J36挂6", "挂J3636川", "京A12345学",
])
def test_trailer_support_does_not_admit_invalid_serials_or_other_suffixes(text):
    assert not is_supported_chinese_plate(text)


def detection(text="川J3636挂", minimum=.96):
    return DetectionObject.model_validate({
        "class": "license_plate", "confidence": .9, "trackId": "trailer-1",
        "bbox": {"x": .3, "y": .4, "width": .15, "height": .08},
        "attributes": {"plateText": text, "ocrConfidence": .98, "ocrMinCharConfidence": minimum},
    })


def processor():
    return CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0", ocrMinVotes=3, ocrVoteFrames=5, ocrMinConfidence=.75),
    )


def test_correct_trailer_plate_requires_three_agreeing_frames_before_confirmation():
    pipeline = processor()
    for frame in range(3):
        result = pipeline.after_tracking([detection()], frame * 200)
        if frame < 2:
            assert result[0].attributes["ocrStatus"] == "PENDING"
            assert not pipeline.event_candidates(result)
    assert result[0].attributes["plateNumber"] == "川J3636挂"
    assert result[0].attributes["ocrStatus"] == "CONFIRMED"
    assert result[0].attributes["visibleByDefault"] is True
    assert len(pipeline.event_candidates(result)) == 1


@pytest.mark.parametrize("text,minimum,status", [
    ("川J3636挂", .69, "LOW_CHAR_CONFIDENCE"),
    ("川JABC1挂", .96, "UNSUPPORTED_FORMAT"),
])
def test_trailer_suffix_cannot_bypass_confidence_or_format_checks(text, minimum, status):
    pipeline = processor()
    for frame in range(5):
        result = pipeline.after_tracking([detection(text, minimum)], frame * 200)
        assert result[0].attributes["ocrStatus"] == status
        assert "plateNumber" not in result[0].attributes
        assert not pipeline.event_candidates(result)
