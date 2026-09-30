import asyncio
import importlib.util
import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import AlgorithmPackageStore
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.task.contracts import TaskInferenceParameters

FOLDER = Path(__file__).parents[1] / "algorithm_packages/people-counting"
MANIFEST = json.loads((FOLDER / "algorithm.json").read_text())
SPEC = importlib.util.spec_from_file_location("people_counting", FOLDER / "processor.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def person(x=0.2, y=0.2, confidence=0.9, kind="person"):
    return {
        "class": kind,
        "confidence": confidence,
        "bbox": {"x": x, "y": y, "width": 0.1, "height": 0.4},
    }


def observe(objects, **parameters):
    return MODULE.Algorithm().process(
        {
            "objects": objects,
            "timestampMillis": 1000,
            "parameters": {**MANIFEST["defaultParameters"], **parameters},
        },
        None,
    )["objects"]


def test_counts_current_people_and_explicit_zero_without_alarm_or_identity():
    result = observe([person(), person(0.4), person(0.6, confidence=0.1), person(kind="car")])
    assert result[0]["attributes"]["observedCount"] == 2
    assert result[0]["attributes"]["displayLabel"] == "当前人数：2 人"
    assert result[0]["attributes"]["displayConfidence"] is None
    assert all(obj["attributes"]["eventCandidate"] is False for obj in result)
    assert len(result) == 3
    assert observe([])[0]["attributes"]["observedCount"] == 0
    assert not MANIFEST.get("resources") and not MANIFEST.get("defaultRule")
    assert [model["slot"] for model in MANIFEST["models"]] == ["person"]


def test_region_center_foot_boundary_and_hidden_boxes_do_not_change_count():
    roi = {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4}
    objects = [person(), person(0.7)]
    center = observe(objects, roi=roi, showPersonBoxes=False)
    assert center[0]["attributes"]["observedCount"] == 1
    assert center[0]["bbox"] == roi
    assert center[0]["attributes"]["visibleByDefault"] is True
    assert center[1]["attributes"]["visibleByDefault"] is False
    assert observe(objects, roi=roi, useFootPoint=True)[0]["attributes"]["observedCount"] == 0
    edge = observe([person(0.45, 0.3)], roi=roi)
    assert edge[0]["attributes"]["observedCount"] == 1


def test_overlapping_people_are_not_merged_and_120_people_fit_contract():
    result = observe([person() for _ in range(120)])
    assert result[0]["attributes"]["observedCount"] == 120
    assert len(result) == 121
    for obj in result:
        DetectionObject.model_validate(obj)


def test_package_worker_does_not_accumulate_counts_across_frames(tmp_path):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        for name in ("algorithm.json", "processor.py"):
            archive.writestr(name, (FOLDER / name).read_bytes())
    descriptor = AlgorithmPackageStore(tmp_path).install(content.getvalue())

    async def run():
        runner = PackageRunner(
            tmp_path, descriptor, MANIFEST["defaultParameters"], {"person": 1}, None
        )
        await runner.start()
        try:
            for timestamp, count in [(1000, 3), (1500, 3), (2000, 1), (2500, 0)]:
                result = await runner.run(
                    [DetectionObject.model_validate(person()) for _ in range(count)],
                    Image.new("RGB", (64, 64)),
                    timestamp,
                    TaskInferenceParameters(schemaVersion="1.0"),
                )
                assert result[0].attributes["observedCount"] == count
                assert result[0].attributes["observedAtMillis"] == timestamp
                assert all(obj.attributes["eventCandidate"] is False for obj in result)
        finally:
            await runner.close()

    asyncio.run(run())
