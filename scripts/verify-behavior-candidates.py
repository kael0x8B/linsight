#!/usr/bin/env python3
"""Replay local real-image candidates; static repetition is not field accuracy validation."""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.task.contracts import TaskInferenceParameters
from ai_runtime.app.task.manager import TaskRunner

ROOT = Path(__file__).resolve().parents[1]
root = ROOT / "artifacts/behavior-catalog-20260908"
inv = json.loads((root / "inventory-before.json").read_text())


async def main():
    pool = ModelPool()
    out = {}
    models = [
        (
            901,
            root / "models/person-reference.onnx",
            json.loads(
                next(v for v in inv["versions"] if v["id"] == 18)["runtimeManifest"]
            ),
        ),
        (
            902,
            root / "models/smoking.onnx",
            json.loads((root / "models/smoking.manifest.json").read_text()),
        ),
        (
            903,
            ROOT / "var/model-assets/v1/human-action-vit-int8.onnx",
            json.loads((root / "models/phone-call.manifest.json").read_text()),
        ),
    ]
    for mid, path, m in models:
        await pool.deploy(
            DeployModelRequest.model_validate(
                {
                    "modelVersionId": mid,
                    "artifactPath": path,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "runtimeManifest": m,
                }
            )
        )
    for name, mid in [("smoking", 902), ("phone-call", 903)]:
        dag = {
            "schemaVersion": "1.0",
            "nodes": [
                {
                    "id": "person",
                    "type": "DETECTOR",
                    "capabilityKey": "detector.person",
                },
                {
                    "id": "behavior",
                    "type": "CLASSIFIER",
                    "capabilityKey": "behavior." + name,
                    **({"inputMode": "PERSON_CROPS"} if name == "phone-call" else {}),
                },
                {"id": "tracker", "type": "TRACKER", "capabilityKey": "tracker.iou"},
            ],
            "edges": [
                {"from": "person", "to": "behavior"},
                {"from": "behavior", "to": "tracker"},
            ],
        }
        params = TaskInferenceParameters.model_validate(
            {
                "schemaVersion": "1.0",
                "confidence": 0.5,
                "personConfidence": 0.35,
                "temporalN": 3,
                "temporalM": 30,
                "durationSeconds": 2,
                "sampleFps": 5,
            }
        )
        runner = object.__new__(TaskRunner)
        runner.request = SimpleNamespace(
            parameters=params,
            pipeline=dag,
            model_bindings={"person": 901, "behavior": mid},
        )
        runner.model_pool = pool
        files = sorted((root / "samples").glob("*.jpg"))
        for file in files:
            if name == "phone-call" and "-train-" not in file.name:
                continue
            if name == "smoking" and not file.name.startswith(
                ("smoking", "not_smoking")
            ):
                continue
            runner.frame_path = file
            with Image.open(file).convert("RGB") as image:
                results, objects = await runner._infer_frame(image)
            processor = CapabilityPostprocessor(dag, params)
            tracker = IoUTracker()
            events = []
            for stamp in range(0, 3200, 200):
                confirmed = processor.after_tracking(
                    tracker.update(processor.before_tracking(objects)), stamp
                )
                if confirmed:
                    events.append(stamp)
            record = {
                "objects": [o.model_dump(by_alias=True) for o in objects],
                "modelTimings": [
                    {"backend": r.backend, "inferenceMillis": r.inference_millis}
                    for r in results
                ],
                "functionalStaticReplayFirstConfirmationMs": events[0]
                if events
                else None,
                "limitation": "static image replay only; not real temporal behavior validation",
            }
            out[name + "/" + file.name] = record
            print(
                name,
                file.name,
                [(o.class_name, round(o.confidence, 3)) for o in objects],
                record["functionalStaticReplayFirstConfirmationMs"],
                flush=True,
            )
    (root / "pipeline-reference.json").write_text(json.dumps(out, indent=2))


asyncio.run(main())
