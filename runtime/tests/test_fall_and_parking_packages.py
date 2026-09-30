"""SDK package output → shared tracker → real RuleEngine; these are contract tests."""

import asyncio
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import AlgorithmPackageStore, inspect_package
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import RuleAst
from ai_runtime.app.rule.engine import RuleEngine
from ai_runtime.app.task.contracts import TaskInferenceParameters

ROOT = Path(__file__).parents[1] / "algorithm_packages"
START = 1788926400000


def bundle(name, mutate=None):
    folder = ROOT / name
    manifest = json.loads((folder / "algorithm.json").read_text())
    if mutate:
        mutate(manifest)
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("algorithm.json", json.dumps(manifest))
        archive.write(folder / "processor.py", "processor.py")
    return manifest, content.getvalue()


def detection(name="car", x=0.3, confidence=0.9):
    return {
        "class": name,
        "confidence": confidence,
        "bbox": {"x": x, "y": 0.3, "width": 0.1, "height": 0.2},
    }


def evaluator(name):
    manifest, _ = bundle(name)
    spec = importlib.util.spec_from_file_location(name, ROOT / name / "processor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    processor = module.Algorithm()
    tracker = IoUTracker()
    engine = RuleEngine(1, 2, RuleAst.model_validate(manifest["defaultRule"]))

    def evaluate(objects, second):
        result = processor.process(
            {"objects": objects, "parameters": manifest["defaultParameters"]}, None
        )
        candidates = tracker.update([DetectionObject.model_validate(o) for o in result["objects"]])
        return engine.evaluate(
            [o for o in candidates if o.attributes["eventCandidate"]], START + second * 1000
        )

    return evaluate


def test_fall_ignores_standing_low_confidence_and_requires_continuous_confirmation():
    evaluate = evaluator("fall")
    for second in range(10):
        assert evaluate([detection("person"), detection("fall", confidence=0.2)], second) == []
    assert not any(t.state == "ALARM" for t in evaluate([detection("fall")], 10))
    evaluate([], 11)
    transitions = []
    for second in range(12, 20):
        transitions += evaluate([detection("fall")], second)
    alarms = [t for t in transitions if t.state == "ALARM"]
    assert len(alarms) == 1
    assert alarms[0].event_type == "FALL"


def test_parking_confirms_once_after_two_minutes_and_closes_on_departure():
    evaluate = evaluator("vehicle-parking")
    transitions = []
    for second in range(150):
        current = evaluate([detection()], second)
        if second < 122:
            assert not any(t.state == "ALARM" for t in current)
        transitions += current
    assert len([t for t in transitions if t.state == "ALARM"]) == 1
    closing = evaluate([], 155)
    assert [t.state for t in closing] == ["RECOVERED", "CLOSED"]


def test_slow_moving_vehicle_never_accumulates_parking_time():
    evaluate = evaluator("vehicle-parking")
    transitions = []
    for second in range(150):
        transitions += evaluate([detection(x=0.05 + second * 0.004)], second)
    assert not any(t.state == "ALARM" for t in transitions)


def test_short_stop_and_observation_break_do_not_form_one_long_stop():
    evaluate = evaluator("vehicle-parking")
    transitions = []
    for second in range(250):
        objects = [] if second in {60, 120, 180, 240} else [detection()]
        transitions += evaluate(objects, second)
    assert not any(t.state == "ALARM" for t in transitions)


def test_tracker_cannot_transfer_vehicle_timer_to_an_overlapping_person():
    tracker = IoUTracker()
    car = tracker.update([DetectionObject.model_validate(detection())])[0]
    person = tracker.update([DetectionObject.model_validate(detection("person"))])[0]
    assert car.track_id != person.track_id


@pytest.mark.parametrize("name", ["fall", "vehicle-parking"])
def test_real_worker_loads_downloadable_package_without_registry_edits(tmp_path, name):
    manifest, content = bundle(name)
    descriptor = AlgorithmPackageStore(tmp_path).install(content)

    async def run():
        runner = PackageRunner(
            tmp_path, descriptor, manifest["defaultParameters"], {"primary": 1}, None
        )
        await runner.start()
        try:
            objects = [
                DetectionObject.model_validate(detection("fall" if name == "fall" else "car"))
            ]
            result = await runner.run(
                objects,
                Image.new("RGB", (640, 480)),
                START,
                TaskInferenceParameters(schemaVersion="1.0"),
            )
            assert len(result) == 1
            assert result[0].attributes["eventCandidate"] is True
        finally:
            await runner.close()

    asyncio.run(run())


def test_default_rule_must_match_event_and_validate_temporal_contract():
    _, content = bundle("fall", lambda m: m["defaultRule"].update(eventType="WRONG"))
    with pytest.raises(ValueError, match="事件类型"):
        inspect_package(content)

    def invalid(m):
        m["defaultRule"]["condition"]["children"][1]["n"] = 99

    _, content = bundle("fall", invalid)
    with pytest.raises(ValueError, match="N_OF_M"):
        inspect_package(content)
