import importlib.util
import json
from pathlib import Path

import pytest

from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import RuleAst
from ai_runtime.app.rule.engine import RuleEngine

FOLDER = Path(__file__).parents[1] / "algorithm_packages/person-absence"
MANIFEST = json.loads((FOLDER / "algorithm.json").read_text())
spec = importlib.util.spec_from_file_location("assigned_absence", FOLDER / "processor.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
START = 1789012800000


class SDK:
    def __init__(self, features=None):
        self.features = features or {}

    def reference_embedding(self, resource, entry):
        assert resource == "people" and entry == 8
        return {"embedding": [1.0, 0.0]}

    def extract_embedding(self, slot, region):
        assert slot == "face"
        return {"embedding": self.features.get(round(region["x"], 2))}


def person(x=0.2, confidence=0.9):
    return {
        "class": "person",
        "confidence": confidence,
        "bbox": {"x": x, "y": 0.1, "width": 0.2, "height": 0.6},
    }


def frame(offset, objects=None, **parameters):
    return {
        "timestampMillis": START + offset,
        "sourceWidth": 640,
        "sourceHeight": 480,
        "objects": objects or [],
        "runtimeCapabilities": ["observation-validity-v1"],
        "parameters": {
            **MANIFEST["defaultParameters"],
            "libraryId": 73004,
            "personIds": [8],
            "confirmFrames": 2,
            "windowFrames": 3,
            "identityHoldSeconds": 1,
            **parameters,
        },
        "resources": {"people": [{"id": 8, "name": "指定人员", "validUntil": START + 1000000}]},
    }


def state(result):
    return result["objects"][0]["attributes"]["presenceState"]


def test_only_assigned_person_confirms_presence_and_a_substitute_does_not():
    algorithm = module.Algorithm()
    other = SDK({0.2: [0.0, 1.0]})
    assert state(algorithm.process(frame(0, [person()]), other)) == "unknown"
    result = algorithm.process(frame(500, [person()]), other)
    assert state(result) == "absent" and result["observationValid"]
    target = SDK({0.2: [1.0, 0.0]})
    assert state(algorithm.process(frame(1000, [person()]), target)) == "unknown"
    assert state(algorithm.process(frame(1500, [person()]), target)) == "present"
    # A different person replaces the target in the identical image position.
    assert state(algorithm.process(frame(2000, [person()]), other)) == "unknown"
    assert state(algorithm.process(frame(2500, [person()]), other)) == "absent"


def test_back_facing_lease_expires_and_missing_body_cannot_keep_identity():
    algorithm = module.Algorithm()
    target = SDK({0.2: [1.0, 0.0]})
    for offset in (0, 500):
        algorithm.process(frame(offset, [person()]), target)
    assert state(algorithm.process(frame(1000, [person()]), SDK())) == "present"
    unknown = algorithm.process(frame(2000, [person()]), SDK())
    assert state(unknown) == "unknown" and unknown["observationValid"] is False
    assert state(algorithm.process(frame(2500), SDK())) == "absent"
    assert state(algorithm.process(frame(3000, [person()]), SDK())) == "unknown"


def test_crossing_or_source_gap_drops_identity_instead_of_transferring_it():
    for crossed in (True, False):
        algorithm = module.Algorithm()
        for offset in (0, 500):
            algorithm.process(frame(offset, [person()]), SDK({0.2: [1.0, 0.0]}))
        objects = [person(0.18), person(0.22)] if crossed else [person()]
        result = algorithm.process(frame(1000 if crossed else 10000, objects), SDK())
        assert state(result) == "unknown"


def test_low_confidence_and_expired_reference_are_unknown_not_absent():
    algorithm = module.Algorithm()
    assert state(algorithm.process(frame(0, [person(confidence=0.2)]), SDK())) == "unknown"
    expired = frame(500)
    expired["resources"]["people"][0]["validUntil"] = START
    assert not algorithm.process(expired, SDK())["observationValid"]


def test_outside_person_is_not_on_post():
    algorithm = module.Algorithm()
    result = algorithm.process(
        frame(0, [person(0.7)], roi={"x": 0, "y": 0, "width": 0.5, "height": 1}),
        SDK({0.7: [1.0, 0.0]}),
    )
    assert state(result) == "absent"


@pytest.mark.parametrize(
    "change",
    [
        {"personIds": []},
        {"personIds": [8, 9]},
        {"confirmFrames": 4, "windowFrames": 3},
        {"rejectSimilarity": 0.8, "similarity": 0.6},
    ],
)
def test_invalid_identity_selection_fails_closed(change):
    with pytest.raises(ValueError):
        module.Algorithm().process(frame(0, **change), SDK())


def test_old_gateway_cannot_silently_treat_unknown_as_recovery():
    old = frame(0)
    old.pop("runtimeCapabilities")
    with pytest.raises(ValueError, match="Upgrade gateway"):
        module.Algorithm().process(old, SDK())


def test_unknown_pauses_confirmation_and_does_not_close_existing_alarm():
    rule = json.loads(json.dumps(MANIFEST["defaultRule"]))
    rule["condition"]["children"][1].update(n=2, m=3)
    rule["condition"]["children"][2]["seconds"] = 1
    rule["recoverySeconds"] = 1
    engine = RuleEngine(1, 2, RuleAst.model_validate(rule), max_observation_gap_millis=5000)
    algorithm = module.Algorithm()

    def evaluate(offset, objects=None, sdk=None):
        result = algorithm.process(frame(offset, objects), sdk or SDK())
        if not result["observationValid"]:
            engine.interrupt_observation()
            return []
        return engine.evaluate(
            [
                DetectionObject.model_validate(o)
                for o in result["objects"]
                if o["attributes"]["eventCandidate"]
            ],
            START + offset,
        )

    all_events = []
    for offset in (0, 500, 1500):
        all_events += evaluate(offset)
    alarm = next(e for e in all_events if e.state == "ALARM")
    assert not evaluate(2000, [person()])
    assert not evaluate(5000, [person()])  # unresolved face cannot close it
    assert not evaluate(5500)
    assert not evaluate(6000)
    target = SDK({0.2: [1.0, 0.0]})
    assert not evaluate(6500, [person()], target)
    assert not evaluate(7000, [person()], target)
    recovered = evaluate(8000, [person()], target)
    assert [e.state for e in recovered] == ["RECOVERED", "CLOSED"]
    assert all(e.source_event_id == alarm.source_event_id for e in recovered)
