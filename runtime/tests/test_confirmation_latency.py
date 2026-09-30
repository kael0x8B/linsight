from datetime import datetime
from zoneinfo import ZoneInfo

from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.confirmation_latency import (
    conflicts_with_visibility_target,
    minimum_confirmation_seconds,
)
from ai_runtime.app.rule.contracts import RuleAst
from ai_runtime.app.rule.engine import RuleEngine
from ai_runtime.app.task.contracts import TaskInferenceParameters


def rule(duration: float) -> dict:
    return {
        "condition": {
            "type": "AND",
            "children": [
                {"type": "N_OF_M", "n": 3, "m": 5},
                {"type": "DURATION", "seconds": duration},
            ],
        }
    }


def test_low_sampling_rate_exposes_fifteen_second_lower_bound() -> None:
    assert minimum_confirmation_seconds(rule(2), 0.2) == 15
    assert conflicts_with_visibility_target(rule(2), 0.2)


def test_rule_only_phone_configuration_can_leave_delivery_budget() -> None:
    assert minimum_confirmation_seconds(rule(0), 2) == 1
    assert not conflicts_with_visibility_target(rule(0), 2)


def test_behavior_candidate_is_confirmed_exactly_once_by_rule_layer() -> None:
    ast = RuleAst.model_validate(
        {
            "schemaVersion": "1.0",
            "eventType": "PHONE_CALL",
            "severity": "MAJOR",
            "regions": [
                {
                    "id": "main",
                    "name": "检测区域",
                    "type": "POLYGON",
                    "sourceWidth": 1920,
                    "sourceHeight": 1080,
                    "pointMode": "CENTROID",
                    "overlapThreshold": 0,
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
                "type": "AND",
                "children": [
                    {
                        "type": "ROI_ENTER",
                        "regionId": "main",
                        "objectClasses": ["phone_call"],
                    },
                    {"type": "N_OF_M", "n": 3, "m": 5},
                    {"type": "DURATION", "seconds": 0},
                ],
            },
            "cooldownSeconds": 60,
            "recoverySeconds": 5,
            "dedup": {"scope": "TRACK", "windowSeconds": 60},
        }
    )
    processor = CapabilityPostprocessor(
        {
            "schemaVersion": "1.0",
            "nodes": [
                {
                    "id": "behavior",
                    "type": "CLASSIFIER",
                    "capabilityKey": "behavior.phone-call",
                }
            ],
            "edges": [],
        },
        TaskInferenceParameters.model_validate(
            {
                "schemaVersion": "1.0",
                "temporalN": 30,
                "temporalM": 60,
                "durationSeconds": 300,
            }
        ),
    )
    engine = RuleEngine(32, 2, ast)
    candidate = DetectionObject.model_validate(
        {
            "class": "phone_call",
            "confidence": 0.9,
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.4},
            "trackId": "track-1",
        }
    )
    started = round(
        datetime(2026, 9, 11, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000
    )
    transitions = []
    for offset in (0, 500, 1_000):
        processed = processor.after_tracking([candidate], started + offset)
        transitions.extend(engine.evaluate(processed, started + offset))

    alarms = [item for item in transitions if item.state == "ALARM"]
    assert len(alarms) == 1
    assert alarms[0].occurred_at_millis == started + 1_000
