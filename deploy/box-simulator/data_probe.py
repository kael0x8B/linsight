"""Seed/check synthetic persistent state across upgrades. Container only."""

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

if not Path("/.dockerenv").exists() or os.environ.get("LINSIGHT_SIMULATOR") != "1":
    raise SystemExit("Only run in the disposable simulator")
sys.path.insert(0, "/opt/linsight/runtime")
from ai_runtime.app.event.store import OfflineEventStore, PendingEvent
from ai_runtime.app.gateway.store import GatewayStore
from ai_runtime.app.task.contracts import TaskStartRequest

root = Path("/var/lib/linsight/runtime-data")
store = GatewayStore(root / "gateway")
if sys.argv[1] == "seed":
    config = TaskStartRequest.model_validate(
        {
            "taskId": 901,
            "runId": str(uuid4()),
            "configVersion": 1,
            "cameraId": 901,
            "sourceUrl": "rtsp://127.0.0.1:9/simulator",
            "algorithmId": 901,
            "pipelineVersionId": 1,
            "modelVersionId": 901,
            "pipeline": {
                "schemaVersion": "1.0",
                "nodes": [
                    {
                        "id": "detector",
                        "type": "DETECTOR",
                        "capabilityKey": "detector.person",
                    }
                ],
                "edges": [],
            },
            "parameters": {"schemaVersion": "1.0", "sampleFps": 1.0},
        }
    ).model_dump(mode="json", by_alias=True)
    config["sourceUrl"] = "rtsp://127.0.0.1:9/simulator"
    store.save(
        {"config": config, "revision": 7, "enabled": False, "platformManaged": True},
        str(uuid4()),
        "simulator-fixture",
    )
    events = OfflineEventStore(root / "events/delivery.sqlite3", retain_history=True)
    events.upsert_event(
        PendingEvent(
            sourceEventId="simulator-unsent-event",
            payload={
                "taskId": 901,
                "sourceEventId": "simulator-unsent-event",
                "eventType": "TEST",
            },
            snapshotPath=root / "events/simulator.jpg",
            finalized=False,
        )
    )
    events.close()

paths = [
    Path("/etc/linsight/runtime.env"),
    Path("/etc/linsight/agent.env"),
    Path("/var/lib/linsight/edge-agent-credential.json"),
    root / "gateway/configuration.key",
    root / "gateway/local-password",
]
with sqlite3.connect(root / "events/delivery.sqlite3") as connection:
    event = connection.execute(
        "SELECT payload, finalized FROM pending_event WHERE source_event_id=?",
        ("simulator-unsent-event",),
    ).fetchone()
evidence = {
    "files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    "task": store.get(901),
    "event": list(event) if event else None,
}
baseline = Path("/simulation/data-baseline.json")
if sys.argv[1] == "seed":
    baseline.write_text(json.dumps(evidence))
else:
    assert evidence == json.loads(baseline.read_text()), "Persistent state changed!"
print(
    json.dumps(
        {
            "persistentDataUnchanged": sys.argv[1] != "seed",
            "stoppedTask": 901,
            "unsentEventPresent": event is not None,
        }
    )
)
