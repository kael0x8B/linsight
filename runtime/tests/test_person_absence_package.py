import asyncio
import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import AlgorithmPackageStore
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import Region, RuleAst
from ai_runtime.app.rule.engine import RuleEngine
from ai_runtime.app.task.contracts import TaskInferenceParameters

FOLDER = Path(__file__).parents[1] / "algorithm_packages/person-absence-count"
MANIFEST = json.loads((FOLDER / "algorithm.json").read_text())
START = 1789012800000  # 2026-09-10 12:00 Asia/Shanghai


def engine(duration=2, recovery=1, minimum=1):
    ast = json.loads(json.dumps(MANIFEST["defaultRule"]))
    ast["condition"]["children"][0]["min"] = minimum
    ast["condition"]["children"][1].update(n=2, m=3)
    ast["condition"]["children"][2]["seconds"] = duration
    ast["recoverySeconds"] = recovery
    ast["regions"][0]["points"] = [
        {"x": 0.1, "y": 0.1},
        {"x": 0.8, "y": 0.1},
        {"x": 0.8, "y": 0.95},
        {"x": 0.1, "y": 0.95},
    ]
    return RuleEngine(1, 2, RuleAst.model_validate(ast), max_observation_gap_millis=5000)


def person(x=0.4, confidence=0.9, kind="person"):
    return DetectionObject.model_validate(
        {
            "class": kind,
            "confidence": confidence,
            "bbox": {"x": x, "y": 0.2, "width": 0.1, "height": 0.5},
            "trackId": str(x),
        }
    )


def test_real_package_process_and_count_rule(tmp_path):
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
            result = await runner.run(
                [person(), person(0.6, 0.1), person(0.5, kind="car")],
                Image.new("RGB", (64, 64)),
                START,
                TaskInferenceParameters(schemaVersion="1.0"),
            )
            assert len(result) == 1
            # eventCandidate means countable observation, not a violation.
            assert result[0].attributes["eventCandidate"] is True
            e = engine()
            assert not e.evaluate(result, START)
            empty = await runner.run(
                [],
                Image.new("RGB", (64, 64)),
                START + 1000,
                TaskInferenceParameters(schemaVersion="1.0"),
            )
            assert empty == []
            transitions = []
            for offset in (1000, 1500, 2500, 3500, 4500, 6500):
                transitions += e.evaluate(empty, START + offset)
            assert sum(t.state == "ALARM" for t in transitions) == 1
            assert not e.evaluate(result, START + 7000)
            recovered = e.evaluate(result, START + 8000)
            assert [t.state for t in recovered] == ["RECOVERED", "CLOSED"]
            assert recovered[0].source_event_id == next(
                t.source_event_id for t in transitions if t.state == "ALARM"
            )
        finally:
            await runner.close()

    asyncio.run(run())


def test_outside_people_do_not_hide_absence_and_short_absence_does_not_alarm():
    e = engine()
    events = []
    for offset, objects in [
        (0, []),
        (500, []),
        (1000, [person()]),
        (1500, [person(0.85)]),
        (2000, [person(0.85)]),
        (3500, [person(0.85)]),
        (4000, [person(0.85)]),
    ]:
        events += e.evaluate(objects, START + offset)
    alarms = [t for t in events if t.state == "ALARM"]
    assert len(alarms) == 1 and alarms[0].occurred_at_millis == START + 3500
    assert alarms[0].object_snapshot["attributes"]["observedCount"] == 0


def test_minimum_count_and_region_reference():
    e = engine(duration=0, minimum=2)
    e.ast.regions.insert(
        0,
        Region.model_validate(
            {
                **e.ast.regions[0].model_dump(by_alias=True),
                "id": "unused",
                "points": [
                    {"x": 0.85, "y": 0},
                    {"x": 1, "y": 0},
                    {"x": 1, "y": 1},
                    {"x": 0.85, "y": 1},
                ],
            }
        ),
    )
    for offset in (0, 500, 1000):
        assert not e.evaluate([person(), person(0.6)], START + offset)
    e.evaluate([person()], START + 1500)
    result = e.evaluate([person()], START + 2000)
    assert (
        next(t for t in result if t.state == "ALARM").object_snapshot["attributes"]["observedCount"]
        == 1
    )


def test_gap_and_non_working_hours_do_not_accumulate_absence():
    e = engine()
    e.evaluate([], START)
    e.evaluate([], START + 500)
    assert not any(t.state == "ALARM" for t in e.evaluate([], START + 60000))
    e.evaluate([], START + 60500)
    assert any(t.state == "ALARM" for t in e.evaluate([], START + 62500))
    # A gap also cannot count as recovery; require observed presence for one second.
    assert not e.evaluate([person()], START + 80000)
    assert [t.state for t in e.evaluate([person()], START + 81000)] == ["RECOVERED", "CLOSED"]
    e = engine()
    e.ast.schedule.weekly[0].start = "12:00"
    e.ast.schedule.weekly[0].end = "12:00"
    e.evaluate([], START)
    e.evaluate([], START + 500)
    assert not e.evaluate([], START + 60000)
    assert not e._states


def test_interrupt_keeps_confirmed_activity_without_duplicate_alarm():
    e = engine(duration=0)
    e.evaluate([], START)
    alarm = next(t for t in e.evaluate([], START + 500) if t.state == "ALARM")
    e.interrupt_observation()
    for offset in (1000, 1500, 2000):
        assert e.evaluate([], START + offset) == []
    e.evaluate([person()], START + 2500)
    closed = e.evaluate([person()], START + 3500)
    assert all(t.source_event_id == alarm.source_event_id for t in closed)
