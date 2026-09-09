import pytest

from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.model.contracts import BoundingBox, DetectionObject
from ai_runtime.app.task.contracts import TaskInferenceParameters


def detected(
    class_name: str,
    bbox: BoundingBox,
    *,
    confidence: float = 0.9,
    track_id: str | None = None,
    attributes: dict | None = None,
) -> DetectionObject:
    return DetectionObject.model_validate(
        {
            "class": class_name,
            "confidence": confidence,
            "bbox": bbox.model_dump(),
            "trackId": track_id,
            "attributes": attributes or {},
        }
    )


def parameters(**values) -> TaskInferenceParameters:
    return TaskInferenceParameters.model_validate({"schemaVersion": "1.0", **values})


def pipeline(capability: str) -> dict:
    return {
        "schemaVersion": "1.0",
        "nodes": [{"id": "capability", "type": "CLASSIFIER", "capabilityKey": capability}],
        "edges": [],
    }


def test_coco_class_filter_reuses_one_detector_for_many_algorithms() -> None:
    processor = CapabilityPostprocessor(
        pipeline("detector.coco"),
        TaskInferenceParameters.model_validate(
            {"schemaVersion": "1.0", "classFilter": ["person", "truck"]}
        ),
    )
    objects = [
        DetectionObject.model_validate(
            {
                "class": name,
                "confidence": 0.9,
                "bbox": {"x": 0, "y": 0, "width": 0.2, "height": 0.2},
            }
        )
        for name in ("person", "car", "truck")
    ]

    assert [value.class_name for value in processor.before_tracking(objects)] == [
        "person",
        "truck",
    ]


def test_ppe_requires_person_and_unknown_does_not_become_violation() -> None:
    processor = CapabilityPostprocessor(pipeline("ppe.helmet"), parameters())
    person = detected("person", BoundingBox(x=0.1, y=0.1, width=0.5, height=0.8))
    unknown = detected("unknown", BoundingBox(x=0.2, y=0.15, width=0.15, height=0.1))

    result = processor.before_tracking([person, unknown])

    assert len(result) == 1
    assert result[0].class_name == "person"
    assert result[0].attributes["helmet"] == "unknown"
    assert result[0].attributes["ppeConfirmedPerson"] is True
    assert processor.before_tracking([unknown]) == []


def test_helmet_region_survives_person_association_without_changing_tracking_or_roi_box() -> None:
    from ai_runtime.app.capability.tracker import IoUTracker

    processor = CapabilityPostprocessor(pipeline("ppe.helmet"), parameters())
    tracker = IoUTracker()
    body = BoundingBox(x=0.1, y=0.1, width=0.5, height=0.8)
    person = detected("person", body)
    for head in [
        BoundingBox(x=0.2, y=0.15, width=0.15, height=0.1),
        BoundingBox(x=0.4, y=0.15, width=0.1, height=0.1),
    ]:
        result = tracker.update(
            processor.before_tracking([person, detected("no_helmet", head, confidence=0.8)])
        )
        assert result[0].bbox == body
        assert result[0].track_id == "track-1"
        assert result[0].attributes["ppeBoxX"] == head.x
        assert result[0].attributes["ppeBoxY"] == head.y
        assert result[0].attributes["ppeBoxWidth"] == head.width
        assert result[0].attributes["ppeBoxHeight"] == head.height
        assert processor.event_candidates(result)[0].bbox == body

    unknown = processor.before_tracking([person])[0]
    assert unknown.attributes["helmet"] == "unknown"
    assert not any(key.startswith("ppeBox") for key in unknown.attributes)


def test_ppe_associates_highest_confidence_candidate_inside_person() -> None:
    processor = CapabilityPostprocessor(pipeline("ppe.reflective-vest"), parameters())
    person = detected("person", BoundingBox(x=0.1, y=0.1, width=0.5, height=0.8))
    vest = detected(
        "vest",
        BoundingBox(x=0.2, y=0.3, width=0.2, height=0.3),
        confidence=0.7,
    )
    absent = detected(
        "no_vest",
        BoundingBox(x=0.25, y=0.35, width=0.2, height=0.3),
        confidence=0.95,
    )

    result = processor.before_tracking([person, vest, absent])

    assert result[0].attributes["vest"] == "absent"
    assert result[0].attributes["ppeSourceClass"] == "no_vest"


def test_ppe_applies_separate_person_and_equipment_thresholds() -> None:
    processor = CapabilityPostprocessor(
        pipeline("ppe.helmet"),
        parameters(personConfidence=0.8, ppeConfidence=0.75),
    )
    weak_person = detected(
        "person", BoundingBox(x=0.0, y=0.0, width=0.4, height=0.8), confidence=0.7
    )
    person = detected("person", BoundingBox(x=0.5, y=0.0, width=0.4, height=0.8), confidence=0.9)
    weak_absent = detected(
        "no_helmet",
        BoundingBox(x=0.6, y=0.1, width=0.1, height=0.1),
        confidence=0.7,
    )

    result = processor.before_tracking([weak_person, person, weak_absent])

    assert len(result) == 1
    assert result[0].attributes["helmet"] == "unknown"


@pytest.mark.parametrize(
    "capability,attribute,present,absent",
    [
        ("ppe.helmet", "helmet", "helmet", "no_helmet"),
        ("ppe.reflective-vest", "vest", "vest", "no_vest"),
    ],
)
def test_ppe_event_candidates_keep_compliant_and_unknown_people_out_of_roi_alarms(
    capability,
    attribute,
    present,
    absent,
) -> None:
    processor = CapabilityPostprocessor(pipeline(capability), parameters())
    person = detected("person", BoundingBox(x=0.1, y=0.1, width=0.5, height=0.8))
    for label, expected in [(present, False), (absent, True), ("unknown", False)]:
        equipment = detected(label, BoundingBox(x=0.2, y=0.2, width=0.2, height=0.2))
        overlay = processor.before_tracking([person, equipment])
        assert len(overlay) == 1  # Normal and unknown states remain visible.
        candidates = processor.event_candidates(overlay)
        assert bool(candidates) is expected
        if candidates:
            assert candidates[0].attributes[attribute] == "absent"
    assert processor.event_candidates([person]) == []
    assert processor.event_candidates(processor.before_tracking([equipment])) == []


def test_non_ppe_event_candidates_preserve_normal_rule_inputs() -> None:
    processor = CapabilityPostprocessor(pipeline("detector.person"), parameters())
    objects = [detected("person", BoundingBox(x=0.1, y=0.1, width=0.5, height=0.8))]
    assert processor.event_candidates(objects) is objects


def test_behavior_requires_temporal_confirmation() -> None:
    processor = CapabilityPostprocessor(
        pipeline("behavior.smoking"),
        parameters(temporalN=2, temporalM=3, durationSeconds=1),
    )
    behavior = detected(
        "smoking",
        BoundingBox(x=0.1, y=0.1, width=0.2, height=0.4),
        track_id="track-1",
    )

    assert processor.after_tracking([behavior], 0) == []
    assert processor.after_tracking([behavior], 500) == []
    confirmed = processor.after_tracking([behavior], 1_000)
    assert confirmed[0].attributes["temporalConfirmed"] is True
    assert confirmed[0].attributes["temporalFrames"] == 3


def test_license_plate_requires_multi_frame_vote() -> None:
    processor = CapabilityPostprocessor(
        pipeline("ocr.license-plate"),
        parameters(ocrVoteFrames=5, ocrMinVotes=3),
    )
    plate = detected(
        "license_plate",
        BoundingBox(x=0.2, y=0.4, width=0.2, height=0.1),
        track_id="vehicle-1",
        attributes={"plateText": "皖A12345", "ocrConfidence": 0.92},
    )

    assert processor.after_tracking([plate], 0)[0].attributes["ocrStatus"] == "PENDING"
    assert processor.after_tracking([plate], 100)[0].attributes["ocrStatus"] == "PENDING"
    confirmed = processor.after_tracking([plate], 200)[0]
    assert confirmed.attributes["ocrStatus"] == "CONFIRMED"
    assert confirmed.attributes["plateNumber"] == "皖A12345"
    assert confirmed.attributes["plateConfidence"] == 0.92
    assert confirmed.attributes["ocrVoteAgreement"] == 1.0


def test_license_plate_rejects_english_only_or_missing_confidence() -> None:
    processor = CapabilityPostprocessor(
        pipeline("ocr.license-plate"),
        parameters(ocrVoteFrames=5, ocrMinVotes=3),
    )
    english_only = detected(
        "license_plate",
        BoundingBox(x=0.2, y=0.4, width=0.2, height=0.1),
        track_id="plate-1",
        attributes={"plateText": "ABC1234", "ocrConfidence": 0.99},
    )
    no_confidence = detected(
        "license_plate",
        BoundingBox(x=0.2, y=0.4, width=0.2, height=0.1),
        track_id="plate-2",
        attributes={"plateText": "皖A12345"},
    )

    result = processor.after_tracking([english_only, no_confidence], 0)

    assert result[0].attributes["ocrStatus"] == "UNSUPPORTED_FORMAT"
    assert result[1].attributes["ocrStatus"] == "MISSING_CONFIDENCE"
    assert all("plateNumber" not in value.attributes for value in result)


def test_license_plate_binds_vehicle_and_preserves_plate_metadata() -> None:
    processor = CapabilityPostprocessor(
        pipeline("ocr.license-plate"),
        parameters(ocrVoteFrames=4, ocrMinVotes=2),
    )
    vehicle = detected(
        "heavy_truck",
        BoundingBox(x=0.1, y=0.1, width=0.8, height=0.8),
        track_id="vehicle-7",
    )
    plate = detected(
        "license_plate",
        BoundingBox(x=0.3, y=0.6, width=0.2, height=0.1),
        track_id="plate-3",
        attributes={
            "plateText": "皖A12345",
            "ocrConfidence": 0.88,
            "plateColor": "yellow",
            "plateType": "large-vehicle",
        },
    )

    first = processor.after_tracking([vehicle, plate], 0)[0]
    second = processor.after_tracking([vehicle, plate], 100)[0]

    assert first.attributes["vehicleTrackId"] == "vehicle-7"
    assert second.attributes["ocrStatus"] == "CONFIRMED"
    assert second.attributes["plateNumber"] == "皖A12345"
    assert second.attributes["plateColor"] == "YELLOW"
    assert second.attributes["plateType"] == "LARGE-VEHICLE"


def test_license_plate_cannot_enable_single_frame_final_result() -> None:
    try:
        parameters(ocrVoteFrames=1, ocrMinVotes=1)
    except ValueError as error:
        assert "greater than or equal to 2" in str(error)
    else:
        raise AssertionError("single-frame plate finalization was accepted")


@pytest.mark.parametrize('capability,label', [('behavior.fall','fall'),
    ('behavior.smoking','smoking'), ('behavior.phone-call','phone_call')])
def test_behavior_requires_elapsed_duration_and_isolates_tracks(capability, label):
    processor = CapabilityPostprocessor(pipeline(capability),
        parameters(temporalN=3, temporalM=30, durationSeconds=2))
    first = detected(label, BoundingBox(x=0, y=0, width=0.3, height=0.8), track_id='a')
    other = detected(label, BoundingBox(x=0.6, y=0, width=0.3, height=0.8), track_id='b')
    for time in range(0, 2000, 200):
        assert processor.after_tracking([first], time) == []
    result = processor.after_tracking([first, other], 2000)
    assert [obj.track_id for obj in result] == ['a']
    for time in range(2200, 9000, 200):
        assert processor.after_tracking([], time) == []
    assert processor._behavior_history == {}
    assert processor.after_tracking([first], 9000) == []


def test_smoking_requires_person_upper_body_association_before_temporal_confirmation():
    processor = CapabilityPostprocessor(pipeline('behavior.smoking'), parameters())
    person = detected('person', BoundingBox(x=0.1, y=0.1, width=0.4, height=0.8))
    near_head = detected('smoking', BoundingBox(x=0.2, y=0.2, width=0.03, height=0.03))
    held_low = detected('smoking', BoundingBox(x=0.2, y=0.7, width=0.03, height=0.03))
    outside = detected('smoking', BoundingBox(x=0.8, y=0.2, width=0.03, height=0.03))
    assert processor.before_tracking([near_head]) == []
    assert processor.before_tracking([person, held_low, outside]) == []
    result = processor.before_tracking([person, near_head])
    assert len(result) == 1
    assert result[0].class_name == 'smoking'
    assert result[0].bbox == person.bbox
    assert result[0].attributes['behaviorPersonAssociated'] is True


def test_one_cigarette_cannot_confirm_two_overlapping_people():
    processor = CapabilityPostprocessor(pipeline('behavior.smoking'), parameters())
    large = detected('person', BoundingBox(x=0, y=0, width=0.8, height=1))
    small = detected('person', BoundingBox(x=0.1, y=0.1, width=0.3, height=0.7))
    cigarette = detected('smoking', BoundingBox(x=0.2, y=0.2, width=0.03, height=0.03))
    result = processor.before_tracking([large, small, cigarette])
    assert len(result) == 1
    assert result[0].bbox == small.bbox
