import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/capture-runtime-observability.py"
SPEC = importlib.util.spec_from_file_location("runtime_observability_capture", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def snapshot(
    *,
    running: int,
    analysis_fps: float,
    active_streams: int,
    pending_events: int,
) -> dict:
    return {
        "schemaVersion": "1.0",
        "process": {
            "cpuPercent": 50,
            "residentMemoryBytes": 1024,
        },
        "system": {
            "cpuPercent": 70,
            "memoryPercent": 60,
            "diskPercent": 50,
            "temperatureCelsius": 55,
            "loadAverage1m": 1.5,
            "networkBytesSent": 100,
            "networkBytesReceived": 200,
        },
        "tasks": {
            "running": running,
            "analysisFps": analysis_fps,
            "inferenceP95Millis": 45,
            "preprocessP95Millis": 5,
            "inferenceP50Millis": 35,
            "inferenceP99Millis": 50,
            "postprocessP95Millis": 3,
            "totalLatencyP50Millis": 45,
            "totalLatencyP95Millis": 55,
            "totalLatencyP99Millis": 60,
        },
        "streams": {
            "active": active_streams,
            "inputFps": 20,
            "droppedFrames": 2,
            "reconnects": 1,
        },
        "delivery": {
            "pendingEvents": pending_events,
            "pendingTransitions": pending_events,
            "deadLetterTransitions": 2,
            "evidenceBacklogBytes": pending_events * 100,
            "missingMediaFiles": 0,
        },
    }


def test_capture_summary_preserves_outage_and_recovery_signals() -> None:
    samples = [
        {
            "controlPlaneReachable": False,
            "snapshot": snapshot(running=2, analysis_fps=15, active_streams=2, pending_events=5),
        },
        {
            "controlPlaneReachable": True,
            "snapshot": snapshot(running=2, analysis_fps=14, active_streams=2, pending_events=0),
        },
    ]

    value = MODULE.summarize(samples, 1800.5)

    assert value["successfulRuntimeSamples"] == 2
    assert value["observedSeconds"] == 1800.5
    assert value["controlPlaneReachableSamples"] == 1
    assert value["runningTasksMin"] == 2
    assert value["analysisFpsMin"] == 14
    assert value["activeStreamsMax"] == 2
    assert value["pendingEventsMax"] == 5
    assert value["pendingEventsFirst"] == 5
    assert value["pendingEventsFinal"] == 0
    assert value["deadLetterTransitionsFirst"] == 2
    assert value["deadLetterTransitionsMax"] == 2
    assert value["deadLetterTransitionsFinal"] == 2
    assert value["missingMediaFilesMax"] == 0
    assert value["inferenceP95MillisMax"] == 45
    assert value["systemCpuPeakPercent"] == 70
    assert value["totalLatencyP99MillisMax"] == 60


def test_capture_rejects_credentials_in_url() -> None:
    try:
        MODULE.safe_base_url("https://user:secret@runtime.example.invalid")
    except ValueError as error:
        assert "credentials" in str(error)
    else:
        raise AssertionError("credential-bearing URL was accepted")
