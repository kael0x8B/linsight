"""Package → worker → tracker → rule contract checks; not field accuracy claims."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image
from test_fall_and_parking_packages import START, bundle, detection, evaluator

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import AlgorithmPackageStore
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.task.contracts import TaskInferenceParameters

NAMES = [
    "person-dwell",
    "crowd-limit",
    "vehicle-intrusion",
    "nonmotor-intrusion",
    "animal-intrusion",
    "fire-lane",
    "phone-presence",
    "bag-stationary",
    "fighting",
]
ROOT = Path(__file__).parents[1] / "algorithm_packages"


@pytest.mark.parametrize("name", NAMES)
def test_packages_validate_and_execute_in_real_worker(tmp_path, name):
    manifest, content = bundle(name)
    installed = AlgorithmPackageStore(tmp_path).install(content)

    async def run():
        runner = PackageRunner(
            tmp_path,
            installed,
            manifest["defaultParameters"],
            {m["slot"]: i + 1 for i, m in enumerate(manifest["models"])},
            None,
        )
        await runner.start()
        try:
            label = manifest["models"][0]["labels"][0]
            result = await runner.run(
                [DetectionObject.model_validate(detection(label))],
                Image.new("RGB", (640, 480)),
                START,
                TaskInferenceParameters(schemaVersion="1.0"),
            )
            assert len(result) == (0 if name == "fighting" else 1)
        finally:
            await runner.close()

    asyncio.run(run())


@pytest.mark.parametrize("name", NAMES[:-1])
def test_no_single_frame_alarm_wrong_class_or_low_confidence(name):
    evaluate = evaluator(name)
    label = json.loads((ROOT / name / "algorithm.json").read_text())["models"][0]["labels"][0]
    for t in range(5):
        assert evaluate([detection("toothbrush"), detection(label, confidence=0.1)], t) == []
    assert not any(x.state == "ALARM" for x in evaluate([detection(label)], 6))


def test_dwell_interruption_resets_timer_and_single_alarm_closes():
    evaluate = evaluator("person-dwell")
    transitions = []
    for t in range(270):
        transitions += evaluate([] if t == 100 else [detection("person")], t)
        if t < 221:
            assert not any(x.state == "ALARM" for x in transitions)
    assert len([x for x in transitions if x.state == "ALARM"]) == 1
    assert [x.state for x in evaluate([], 280)] == ["RECOVERED", "CLOSED"]


def test_fire_lane_moving_target_and_unrecognized_obstacle_do_not_alarm():
    evaluate = evaluator("fire-lane")
    transitions = []
    for t in range(100):
        transitions += evaluate([detection("truck", x=0.05 + t * 0.005), detection("cardboard")], t)
    assert not any(x.state == "ALARM" for x in transitions)
    for t in range(100, 150):
        transitions += evaluate([detection("chair")], t)
    assert len([x for x in transitions if x.state == "ALARM"]) == 1


def test_count_uses_simultaneous_people_not_accumulated_tracks():
    evaluate = evaluator("crowd-limit")
    transitions = []
    for t in range(20):
        transitions += evaluate([detection("person", x=i * 0.15) for i in range(4)], t)
    assert not any(x.state == "ALARM" for x in transitions)
    for t in range(20, 40):
        transitions += evaluate([detection("person", x=i * 0.15) for i in range(5)], t)
    assert len([x for x in transitions if x.state == "ALARM"]) == 1


def test_fight_requires_model_evidence_and_bounded_pair_inference():
    spec = importlib.util.spec_from_file_location("fight", ROOT / "fighting/processor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    algorithm = module.Algorithm()
    params = json.loads((ROOT / "fighting/algorithm.json").read_text())["defaultParameters"]

    class SDK:
        calls = 0
        label = "hugging"

        def infer(self, slot, region):
            assert slot == "action"
            assert region["x"] + region["width"] <= 1
            self.calls += 1
            return {"objects": [detection(self.label)]}

    sdk = SDK()
    frame = {
        "objects": [detection("person", x=0.3 + i * 0.01) for i in range(10)],
        "parameters": params,
    }
    assert algorithm.process(frame, sdk)["objects"] == []
    assert sdk.calls == params["maxPairs"]
    sdk.label = "fighting"
    assert algorithm.process(frame, sdk)["objects"][0]["attributes"]["requiresReview"]
    sdk.calls = 0
    frame["objects"] = [detection("person", x=0.3 + i * 0.01) for i in range(3)]
    assert len(algorithm.process(frame, sdk)["objects"]) == 1
    assert sdk.calls == 1
    frame["objects"] = [detection("person")]
    assert algorithm.process(frame, sdk)["objects"] == []
