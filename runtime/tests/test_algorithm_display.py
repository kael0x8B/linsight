"""Provider output -> worker/overlay/track/rule contracts; no provider in the renderer registry."""

import asyncio
import importlib.util
import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import AlgorithmPackageStore, inspect_package
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import RuleAst
from ai_runtime.app.rule.engine import RuleEngine
from ai_runtime.app.stream.overlay import OverlayObject
from ai_runtime.app.task.contracts import TaskInferenceParameters

ROOT = Path(__file__).parents[1] / "algorithm_packages"
FIXTURE = json.loads((Path(__file__).parent / "fixtures/algorithm-display.json").read_text())


def load(name):
    folder = ROOT / name
    manifest = json.loads((folder / "algorithm.json").read_text())
    spec = importlib.util.spec_from_file_location("provider_" + name, folder / "processor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return manifest, module.Algorithm()


@pytest.mark.parametrize(
    "name,positive,negative", [("helmet", "helmet", "no_helmet"), ("vest", "vest", "no_vest")]
)
def test_evidence_score_box_and_visibility_are_owned_by_package(name, positive, negative):
    manifest, algorithm = load(name)
    original = deepcopy(FIXTURE["input"])
    for label, state in [(negative, "alert"), (positive, "normal"), ("person", "unknown")]:
        objects = deepcopy(original)
        objects[1]["class"] = label
        if state == "unknown":
            objects = objects[:1]
        result = algorithm.process(
            {"objects": objects, "parameters": manifest["defaultParameters"]}, None
        )["objects"][0]
        assert result["bbox"] == original[0]["bbox"]
        assert result["confidence"] == 0.66
        display = result["attributes"]
        assert display["displayState"] == state
        assert display["visibleByDefault"] == (state == "alert")
        assert display["eventCandidate"] == (state == "alert")
        assert display["displayConfidence"] == (None if state == "unknown" else 0.93)
        assert display["displayBoxHeight"] == (0.8 if state == "unknown" else 0.15)
        assert OverlayObject.model_validate(result).attributes == display
        assert objects[0] == original[0]


def test_real_worker_matches_shared_frontend_fixture_and_roi_uses_person_box(tmp_path):
    manifest, algorithm = load("helmet")
    assert algorithm.process(
        {"objects": deepcopy(FIXTURE["input"]), "parameters": manifest["defaultParameters"]}, None
    )["objects"] == [FIXTURE["expected"]]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("algorithm.json", json.dumps(manifest))
        file.write(ROOT / "helmet/processor.py", "processor.py")
    inspect_package(archive.getvalue())
    descriptor = AlgorithmPackageStore(tmp_path).install(archive.getvalue())

    async def run():
        runner = PackageRunner(
            tmp_path, descriptor, manifest["defaultParameters"], {"person": 1, "ppe": 2}, None
        )
        await runner.start()
        try:
            result = await runner.run(
                [DetectionObject.model_validate(o) for o in FIXTURE["input"]],
                Image.new("RGB", (640, 480)),
                1789012800000,
                TaskInferenceParameters(schemaVersion="1.0"),
            )
            assert result[0].model_dump(mode="json", by_alias=True) == FIXTURE["expected"]
            tracked = IoUTracker().update(result)
            ast = json.loads((ROOT / "fall/algorithm.json").read_text())["defaultRule"]
            ast["eventType"] = "SAFETY_HELMET"
            ast["regions"][0]["pointMode"] = "FOOT"
            ast["regions"][0]["points"] = [
                {"x": 0, "y": 0.7},
                {"x": 1, "y": 0.7},
                {"x": 1, "y": 1},
                {"x": 0, "y": 1},
            ]
            ast["condition"]["children"][0]["objectClasses"] = ["person"]
            engine = RuleEngine(1, 2, RuleAst.model_validate(ast))
            transitions = [
                t for i in range(10) for t in engine.evaluate(tracked, 1789012800000 + i * 1000)
            ]
            assert any(t.state == "ALARM" for t in transitions), (
                "ROI must use person foot, not the head display box"
            )
        finally:
            await runner.close()

    asyncio.run(run())


@pytest.mark.parametrize("name", ["helmet", "vest"])
def test_display_choice_changes_neither_detection_nor_rule_candidate(name):
    manifest, algorithm = load(name)
    objects = deepcopy(FIXTURE["input"])
    objects[1]["class"] = "no_helmet" if name == "helmet" else "no_vest"
    default = algorithm.process(
        {"objects": objects, "parameters": manifest["defaultParameters"]}, None
    )["objects"][0]
    full = algorithm.process(
        {
            "objects": objects,
            "parameters": {**manifest["defaultParameters"], "showPersonBox": True},
        },
        None,
    )["objects"][0]
    assert full["attributes"]["displayBoxHeight"] == 0.8
    assert default["attributes"]["displayBoxHeight"] == 0.15
    for key in ["bbox", "confidence", "trackId", "class"]:
        assert full[key] == default[key]
    assert full["attributes"]["eventCandidate"] == default["attributes"]["eventCandidate"]
    assert full["attributes"]["displayConfidence"] == default["attributes"]["displayConfidence"]


def test_overlapping_people_do_not_share_or_trade_heads_when_scores_change():
    manifest, algorithm = load("helmet")
    people = [
        {
            "class": "person",
            "confidence": 0.8,
            "trackId": "near",
            "attributes": {},
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.8},
        },
        {
            "class": "person",
            "confidence": 0.7,
            "trackId": "far",
            "attributes": {},
            "bbox": {"x": 0.3, "y": 0.2, "width": 0.15, "height": 0.4},
        },
    ]
    heads = [
        {
            "class": "no_helmet",
            "confidence": 0.6,
            "attributes": {},
            "bbox": {"x": 0.24, "y": 0.09, "width": 0.12, "height": 0.13},
        },
        {
            "class": "no_helmet",
            "confidence": 0.95,
            "attributes": {},
            "bbox": {"x": 0.34, "y": 0.19, "width": 0.07, "height": 0.08},
        },
    ]
    for scores in [(0.6, 0.95), (0.95, 0.6)]:
        heads[0]["confidence"], heads[1]["confidence"] = scores
        for objects in [people + heads, list(reversed(people + heads))]:
            results = algorithm.process(
                {"objects": objects, "parameters": manifest["defaultParameters"]}, None
            )["objects"]
            boxes = {o["trackId"]: o["attributes"]["displayBoxX"] for o in results}
            assert boxes == {"near": 0.24, "far": 0.34}
            assert len(set(boxes.values())) == 2
    # When the near head is occluded, do not steal the far person's head.
    results = algorithm.process(
        {"objects": people + heads[1:], "parameters": manifest["defaultParameters"]}, None
    )["objects"]
    assert results[0]["attributes"]["displayState"] == "unknown"
    assert results[1]["attributes"]["displayBoxX"] == 0.34


def test_head_inside_another_person_lower_body_is_not_associated():
    manifest, algorithm = load("helmet")
    objects = deepcopy(FIXTURE["input"])
    objects[1]["bbox"]["y"] = 0.65
    result = algorithm.process(
        {"objects": objects, "parameters": manifest["defaultParameters"]}, None
    )["objects"][0]
    assert result["attributes"]["displayState"] == "unknown"
    assert result["attributes"]["eventCandidate"] is False
