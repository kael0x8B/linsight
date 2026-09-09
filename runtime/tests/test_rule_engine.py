from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import RuleAst
from ai_runtime.app.rule.engine import RuleEngine


def rule_ast() -> RuleAst:
    return RuleAst.model_validate(
        {
            "schemaVersion": "1.0",
            "eventType": "AREA_INTRUSION",
            "severity": "MAJOR",
            "regions": [
                {
                    "id": "main",
                    "name": "主区域",
                    "type": "POLYGON",
                    "sourceWidth": 1920,
                    "sourceHeight": 1080,
                    "pointMode": "FOOT",
                    "overlapThreshold": 0,
                    "points": [
                        {"x": 0.1, "y": 0.1},
                        {"x": 0.9, "y": 0.1},
                        {"x": 0.9, "y": 0.9},
                        {"x": 0.1, "y": 0.9},
                    ],
                }
            ],
            "schedule": {
                "timezone": "Asia/Shanghai",
                "weekly": [{"days": [1, 2, 3, 4, 5, 6, 7], "start": "00:00", "end": "23:59"}],
            },
            "condition": {
                "type": "AND",
                "children": [
                    {"type": "ROI_ENTER", "regionId": "main", "objectClasses": ["person"]},
                    {"type": "N_OF_M", "n": 3, "m": 5},
                    {"type": "DURATION", "seconds": 2},
                ],
            },
            "cooldownSeconds": 30,
            "recoverySeconds": 0.3,
            "dedup": {"scope": "TRACK", "windowSeconds": 30},
        }
    )


def person(x: float = 0.4) -> DetectionObject:
    return DetectionObject.model_validate(
        {
            "class": "person",
            "confidence": 0.92,
            "bbox": {"x": x, "y": 0.3, "width": 0.1, "height": 0.2},
            "trackId": "track-1",
        }
    )


def test_rule_engine_confirms_once_then_closes_and_allows_a_new_activity() -> None:
    engine = RuleEngine(task_id=8, camera_id=9, ast=rule_ast())
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )

    transitions = []
    for offset in (0, 100, 200, 2_200, 2_400):
        transitions.extend(engine.evaluate([person()], started + offset))

    alarms = [value for value in transitions if value.state == "ALARM"]
    assert len(alarms) == 1
    first = alarms[0]
    assert first.dedup_key.endswith(":track-1")
    assert first.source_event_id == first.activity_id

    closing = engine.evaluate([], started + 2_800)
    assert [value.state for value in closing] == ["RECOVERED", "CLOSED"]
    assert all(value.source_event_id == first.source_event_id for value in closing)

    next_transitions = []
    for offset in (3_000, 3_100, 3_200, 5_200):
        next_transitions.extend(engine.evaluate([person()], started + offset))
    next_alarm = next(value for value in next_transitions if value.state == "ALARM")
    assert next_alarm.dedup_key == first.dedup_key
    assert next_alarm.source_event_id != first.source_event_id


def test_tracker_keeps_identity_for_overlapping_person() -> None:
    tracker = IoUTracker()
    first = tracker.update([person(0.4)])[0]
    second = tracker.update([person(0.41)])[0]
    assert first.track_id == second.track_id


def test_missing_candidates_count_as_negative_frames_and_break_confirmation() -> None:
    ast = rule_ast().model_copy(update={"recovery_seconds": 30})
    engine = RuleEngine(task_id=8, camera_id=9, ast=ast)
    started = round(
        datetime(2026, 9, 6, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )
    transitions = []
    for offset in (0, 100, 200):
        transitions.extend(engine.evaluate([person()], started + offset))
    # No explicit violation while the person's PPE is normal or unknown.
    for offset in (300, 400, 500, 600, 700):
        transitions.extend(engine.evaluate([], started + offset))
    transitions.extend(engine.evaluate([person()], started + 2_500))
    assert not any(value.state == "ALARM" for value in transitions)
    for offset in (2_600, 2_700, 4_700):
        transitions.extend(engine.evaluate([person()], started + offset))
    assert sum(value.state == "ALARM" for value in transitions) == 1


def test_rule_engine_does_not_close_a_candidate_that_never_alarmed() -> None:
    engine = RuleEngine(task_id=8, camera_id=9, ast=rule_ast())
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )

    detected = engine.evaluate([person()], started)
    closing = engine.evaluate([], started + 400)

    assert [value.state for value in detected] == ["DETECTED"]
    assert closing == []


def test_rule_ast_rejects_self_intersecting_polygon() -> None:
    value = rule_ast().model_dump(by_alias=True)
    value["regions"][0]["points"] = [
        {"x": 0.1, "y": 0.1},
        {"x": 0.9, "y": 0.9},
        {"x": 0.1, "y": 0.9},
        {"x": 0.9, "y": 0.1},
    ]
    with pytest.raises(ValidationError, match="self-intersects"):
        RuleAst.model_validate(value)


def test_person_absence_uses_scene_count_and_recovers_when_person_returns() -> None:
    value = rule_ast().model_dump(by_alias=True)
    value["eventType"] = "PERSON_ABSENCE"
    value["condition"] = {
        "type": "AND",
        "children": [
            {
                "type": "COUNT_BELOW",
                "regionId": "main",
                "objectClasses": ["person"],
                "min": 1,
            },
            {"type": "N_OF_M", "n": 2, "m": 3},
            {"type": "DURATION", "seconds": 1},
        ],
    }
    value["dedup"] = {"scope": "CAMERA_TASK_TYPE", "windowSeconds": 30}
    value["recoverySeconds"] = 0
    engine = RuleEngine(task_id=8, camera_id=9, ast=RuleAst.model_validate(value))
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )

    transitions = []
    for offset in (0, 100, 1_100):
        transitions.extend(engine.evaluate([], started + offset))
    alarm = next(item for item in transitions if item.state == "ALARM")
    assert alarm.object_snapshot["attributes"] == {
        "comparison": "BELOW",
        "minimumCount": 1,
        "observedCount": 0,
        "thresholdCount": 1,
    }
    assert [item.state for item in engine.evaluate([person()], started + 1_200)] == [
        "RECOVERED",
        "CLOSED",
    ]


def test_people_gathering_uses_at_least_count_and_recovers_below_threshold() -> None:
    value = rule_ast().model_dump(by_alias=True)
    value["eventType"] = "PEOPLE_GATHERING"
    value["condition"] = {
        "type": "AND",
        "children": [
            {
                "type": "ROI_ENTER",
                "regionId": "main",
                "objectClasses": ["person"],
            },
            {"type": "COUNT", "min": 2},
            {"type": "N_OF_M", "n": 1, "m": 1},
        ],
    }
    value["dedup"] = {"scope": "CAMERA_TASK_TYPE", "windowSeconds": 30}
    value["recoverySeconds"] = 0
    engine = RuleEngine(task_id=8, camera_id=9, ast=RuleAst.model_validate(value))
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )
    second = person(0.55).model_copy(update={"track_id": "track-2"})

    transitions = engine.evaluate([person(), second], started)

    alarm = next(item for item in transitions if item.state == "ALARM")
    assert alarm.object_snapshot["attributes"]["comparison"] == "AT_LEAST"
    assert alarm.object_snapshot["attributes"]["observedCount"] == 2
    assert [item.state for item in engine.evaluate([person()], started + 100)] == [
        "RECOVERED",
        "CLOSED",
    ]


def test_scene_count_does_not_close_a_candidate_that_never_alarmed() -> None:
    value = rule_ast().model_dump(by_alias=True)
    value["eventType"] = "PERSON_ABSENCE"
    value["condition"] = {
        "type": "AND",
        "children": [
            {
                "type": "COUNT_BELOW",
                "regionId": "main",
                "objectClasses": ["person"],
                "min": 1,
            },
            {"type": "N_OF_M", "n": 2, "m": 3},
            {"type": "DURATION", "seconds": 1},
        ],
    }
    value["dedup"] = {"scope": "CAMERA_TASK_TYPE", "windowSeconds": 30}
    value["recoverySeconds"] = 0
    engine = RuleEngine(task_id=8, camera_id=9, ast=RuleAst.model_validate(value))
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )

    detected = engine.evaluate([], started)
    closing = engine.evaluate([person()], started + 100)

    assert [item.state for item in detected] == ["DETECTED"]
    assert closing == []


def test_stationary_rule_confirms_when_track_stays_within_movement_threshold() -> None:
    value = rule_ast().model_dump(by_alias=True)
    value["eventType"] = "VEHICLE_STATIONARY"
    value["condition"] = {
        "type": "AND",
        "children": [
            {"type": "ROI_ENTER", "regionId": "main", "objectClasses": ["person"]},
            {"type": "STATIONARY", "maxMovement": 0.02},
            {"type": "N_OF_M", "n": 1, "m": 1},
            {"type": "DURATION", "seconds": 1},
        ],
    }
    engine = RuleEngine(task_id=8, camera_id=9, ast=RuleAst.model_validate(value))
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )

    transitions = engine.evaluate([person(0.4)], started)
    transitions.extend(engine.evaluate([person(0.405)], started + 1_000))

    assert any(item.state == "ALARM" for item in transitions)


def test_loitering_rule_waits_for_time_and_accumulated_path() -> None:
    value = rule_ast().model_dump(by_alias=True)
    value["eventType"] = "PERSON_LOITERING"
    value["condition"] = {
        "type": "AND",
        "children": [
            {"type": "ROI_ENTER", "regionId": "main", "objectClasses": ["person"]},
            {"type": "LOITERING", "minPathLength": 0.08, "seconds": 1},
            {"type": "N_OF_M", "n": 1, "m": 1},
        ],
    }
    engine = RuleEngine(task_id=8, camera_id=9, ast=RuleAst.model_validate(value))
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )

    assert engine.evaluate([person(0.4)], started) == []
    assert engine.evaluate([person(0.44)], started + 500) == []
    transitions = engine.evaluate([person(0.49)], started + 1_000)

    assert any(item.state == "ALARM" for item in transitions)


def test_brief_missing_detection_does_not_repeat_same_activity_after_cooldown() -> None:
    ast = rule_ast().model_copy(update={"recovery_seconds": 5})
    engine = RuleEngine(task_id=8, camera_id=9, ast=ast)
    started = round(
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )
    transitions = []
    for offset in range(0, 80_000, 100):
        # A brief occlusion resets confirmation timing but does not close this event.
        observed = [] if offset in {31_000, 62_000} else [person()]
        transitions.extend(engine.evaluate(observed, started + offset))
    alarms = [value for value in transitions if value.state == "ALARM"]
    assert len(alarms) == 1
    closed = engine.evaluate([], started + 90_000)
    assert [value.state for value in closed] == ["RECOVERED", "CLOSED"]
    assert all(value.source_event_id == alarms[0].source_event_id for value in closed)


def smoke_scene_ast() -> RuleAst:
    value = rule_ast().model_dump(by_alias=True)
    value['eventType'] = 'SMOKE'
    value['condition'] = {'type': 'AND', 'children': [
        {'type': 'ROI_ENTER', 'regionId': 'main', 'objectClasses': ['smoke']},
        {'type': 'N_OF_M', 'n': 2, 'm': 3},
        {'type': 'DURATION', 'seconds': 0},
    ]}
    value['dedup'] = {'scope': 'CAMERA_TASK_TYPE', 'windowSeconds': 30}
    return RuleAst.model_validate(value)


def test_scene_presence_counts_frames_not_boxes_and_retains_real_evidence() -> None:
    engine = RuleEngine(task_id=8, camera_id=9, ast=smoke_scene_ast())
    started = 1788346800000
    smoke = person().model_copy(update={'class_name': 'smoke', 'confidence': 0.8})
    second = person(0.55).model_copy(update={
        'class_name': 'smoke', 'confidence': 0.9, 'track_id': 'track-2',
    })
    irrelevant = person().model_copy(update={'class_name': 'flame', 'confidence': 0.99})
    first = engine.evaluate([smoke, second, irrelevant], started)
    assert [item.state for item in first] == ['DETECTED']
    transitions = engine.evaluate([smoke, second, irrelevant], started + 100)
    alarms = [item for item in transitions if item.state == 'ALARM']
    assert len(alarms) == 1
    assert alarms[0].track_id is None
    assert alarms[0].object_snapshot['class'] == 'smoke'
    assert alarms[0].object_snapshot['confidence'] == 0.9
    assert alarms[0].object_snapshot['bbox'] == second.bbox.model_dump()
    closed = engine.evaluate([], started + 500)
    assert [item.state for item in closed] == ['RECOVERED', 'CLOSED']
    assert all(item.source_event_id == alarms[0].source_event_id for item in closed)
    assert all(item.object_snapshot['class'] == 'smoke' for item in closed)


def test_scene_presence_survives_track_changes_and_dedup_window_boundary() -> None:
    ast = smoke_scene_ast()
    ast.condition['children'][2]['seconds'] = 1
    engine = RuleEngine(task_id=8, camera_id=9, ast=ast)
    started = 1788346829900
    transitions = []
    for index, offset in enumerate((0, 100, 1100, 31000, 61000)):
        detected = person().model_copy(update={
            'class_name': 'smoke', 'track_id': f'changing-track-{index}',
        })
        transitions.extend(engine.evaluate([detected], started + offset))
    assert sum(item.state == 'ALARM' for item in transitions) == 1


def test_scene_presence_ignores_other_classes_and_outside_roi() -> None:
    engine = RuleEngine(task_id=8, camera_id=9, ast=smoke_scene_ast())
    outside = person(0.95).model_copy(update={'class_name': 'smoke'})
    for offset in (0, 100, 1000, 2000):
        assert engine.evaluate([person(), outside], 1788346800000 + offset) == []
