from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import RuleAst
from ai_runtime.app.rule.engine import RuleEngine
from ai_runtime.app.task.contracts import TaskInferenceParameters


def engine():
    ast = RuleAst.model_validate(
        {
            "schemaVersion": "1.0",
            "eventType": "VEHICLE_PLATE_RECOGNIZED",
            "severity": "INFO",
            "regions": [
                {
                    "id": "yard",
                    "name": "厂区",
                    "type": "POLYGON",
                    "sourceWidth": 640,
                    "sourceHeight": 480,
                    "pointMode": "CENTROID",
                    "points": [
                        {"x": 0, "y": 0},
                        {"x": 1, "y": 0},
                        {"x": 1, "y": 1},
                        {"x": 0, "y": 1},
                    ],
                }
            ],
            "schedule": {
                "timezone": "Asia/Shanghai",
                "weekly": [{"days": [1, 2, 3, 4, 5, 6, 7], "start": "00:00", "end": "23:59"}],
            },
            "condition": {
                "type": "ROI_ENTER",
                "regionId": "yard",
                "objectClasses": ["license_plate"],
            },
            "cooldownSeconds": 0,
            "recoverySeconds": 5,
            "dedup": {"scope": "TRACK", "windowSeconds": 60},
        }
    )
    return RuleEngine(33, 2, ast, identity_deduplication=True)


def plate(track="physical-1", text="吉WD0011", confidence=0.98):
    return DetectionObject.model_validate(
        {
            "class": "license_plate",
            "confidence": 0.9,
            "trackId": track,
            "bbox": {"x": 0.3, "y": 0.5, "width": 0.2, "height": 0.1},
            "attributes": {
                "plateText": text,
                "ocrConfidence": 0.98,
                "ocrMinCharConfidence": confidence,
            },
        }
    )


def processor():
    return CapabilityPostprocessor(
        {"nodes": [{"capabilityKey": "ocr.license-plate"}]},
        TaskInferenceParameters(schemaVersion="1.0"),
    )


def test_visible_plate_with_bad_ocr_does_not_close_and_reopen_visit():
    p, rule = processor(), engine()
    transitions = []
    for timestamp in range(0, 15000, 350):
        # Both initial and final observations pass; the same plate stays
        # physically visible with poor OCR for more than the 5-second recovery.
        frame = plate(confidence=0.98 if timestamp < 1050 or timestamp >= 12000 else 0.5)
        processed = p.after_tracking([frame], timestamp)
        observed = p.rule_observations(processed, timestamp)
        if 1050 <= timestamp < 12000:
            assert observed[0].attributes["eventCandidate"] is False
            assert "plateNumber" not in observed[0].attributes
            assert not p.event_candidates(processed)
        transitions.extend(rule.evaluate(observed, timestamp))
    assert [t.state for t in transitions].count("ALARM") == 1
    assert not any(t.state in {"RECOVERED", "CLOSED"} for t in transitions)
    assert (
        next(t for t in transitions if t.state == "ALARM").object_snapshot["attributes"][
            "plateNumber"
        ]
        == "吉WD0011"
    )


def test_same_plate_reentry_obeys_sliding_dedup_window_but_other_plates_do_not():
    p, rule = processor(), engine()

    def observe(timestamp, frames):
        return rule.evaluate(
            p.rule_observations(p.after_tracking(frames, timestamp), timestamp), timestamp
        )

    alarms = []
    for timestamp in (0, 350, 700):
        alarms.extend(t for t in observe(timestamp, [plate()]) if t.state == "ALARM")
    assert len(alarms) == 1
    assert any(t.state == "CLOSED" for t in observe(6000, []))
    # A new detector track after a short dropout is still the same plate.
    for timestamp in (7000, 7350, 7700):
        assert not any(t.state == "ALARM" for t in observe(timestamp, [plate(track="new")]))
    for timestamp in (8000, 8350, 8700):
        alarms.extend(
            t
            for t in observe(timestamp, [plate(track="other", text="皖A12345")])
            if t.state == "ALARM"
        )
    assert len(alarms) == 2
    observe(14000, [])
    # Same identity is eligible again only after the configured absence window.
    for timestamp in (68000, 68350, 68700):
        alarms.extend(t for t in observe(timestamp, [plate(track="third")]) if t.state == "ALARM")
    assert len(alarms) == 3
    assert alarms[0].source_event_id != alarms[2].source_event_id


def test_presence_alone_cannot_start_an_event_or_cross_physical_tracks():
    p, rule = processor(), engine()
    unconfirmed = plate().model_copy(update={"attributes": {"eventCandidate": False}})
    assert rule.evaluate([unconfirmed], 0) == []
    for timestamp in (0, 350, 700):
        objects = p.after_tracking([plate()], timestamp)
        rule.evaluate(p.rule_observations(objects, timestamp), timestamp)
    for timestamp in range(1050, 7000, 350):
        objects = p.after_tracking([plate(track="unrelated", confidence=0.5)], timestamp)
        observed = p.rule_observations(objects, timestamp)
        assert observed == []
        rule.evaluate(observed, timestamp)
    assert not rule._states
