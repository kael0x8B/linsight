import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/production_evidence.py"
SPEC = importlib.util.spec_from_file_location("production_evidence_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

RELEASE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/release-readiness.py"
RELEASE_SPEC = importlib.util.spec_from_file_location(
    "release_readiness_evidence_test", RELEASE_SCRIPT
)
assert RELEASE_SPEC is not None and RELEASE_SPEC.loader is not None
RELEASE_MODULE = importlib.util.module_from_spec(RELEASE_SPEC)
sys.modules[RELEASE_SPEC.name] = RELEASE_MODULE
RELEASE_SPEC.loader.exec_module(RELEASE_MODULE)

ENVIRONMENT = {
    "name": "acceptance-lab",
    "hardware": "x86 CPU, NVIDIA GPU, 32 GiB RAM, production camera network",
    "softwareVersion": "v1.0.0-test",
}


def collector_artifact(run_id: str, summary: dict, with_snapshot: bool = False) -> dict:
    return {
        "schemaVersion": "1.0",
        "artifactType": "runtimeObservabilitySeries",
        "generatedAt": datetime.now(UTC).isoformat(),
        "runId": run_id,
        "environment": ENVIRONMENT,
        "summary": {"sampleCount": 1, "successfulRuntimeSamples": 1, **summary},
        "samples": [
            {
                "snapshot": {
                    "process": {
                        "cpuPercent": 25,
                        "residentMemoryBytes": 1024,
                        "openFileCount": 12,
                    },
                    "tasks": {
                        "running": 1,
                        "analysisFps": 15,
                        "queueDepth": 0,
                        "inferenceP95Millis": 45,
                    },
                    "streams": {
                        "active": 1,
                        "inputFps": 20,
                        "droppedFrames": 0,
                        "reconnects": 0,
                    },
                    "models": {"loaded": 1, "capacity": 4},
                    "delivery": {
                        "pendingEvents": 0,
                        "pendingTransitions": 0,
                        "deadLetterTransitions": 0,
                        "evidenceBacklogBytes": 0,
                        "missingMediaFiles": 0,
                    },
                }
            }
        ]
        if with_snapshot
        else [],
    }


def valid_report(evidence_type: str, root: Path) -> tuple[dict, Path]:
    raw = root / "raw" / f"{evidence_type}.log"
    report_path = root / "reports" / f"{evidence_type}.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(f"immutable raw evidence for {evidence_type}\n", encoding="utf-8")
    report = MODULE._pending_report(evidence_type, ENVIRONMENT)
    report.update(
        {
            "status": "PASS",
            "generatedAt": datetime.now(UTC).isoformat(),
            "runId": f"field-{evidence_type}-001",
            "rawArtifacts": [
                {
                    "path": f"../raw/{evidence_type}.log",
                    "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                }
            ],
        }
    )
    if evidence_type == "algorithmAcceptance":
        for asset in report["modelAssets"]:
            asset.update(
                {
                    "sourceUrl": "https://models.example.invalid/repository",
                    "sourceRevision": "fixed-commit-123",
                    "artifactSha256": "a" * 64,
                    "licenseSpdx": "Apache-2.0",
                    "singleImageTest": "PASS",
                    "nodeDeployment": "PASS",
                    "standardizedOutput": "PASS",
                }
            )
        for algorithm in report["algorithms"]:
            algorithm.update(
                {
                    "status": "PASS",
                    "datasetVersion": "dataset-v1",
                    "datasetSha256": "b" * 64,
                    "metrics": {
                        "eventPrecision": 0.95,
                        "eventRecall": 0.94,
                        "falsePositivesPerStreamHour": 0.1,
                        "missedEvents": 0,
                        "endToEndP95Ms": 900,
                        "averageFps": 15,
                    },
                    "thresholds": {
                        "minEventPrecision": 0.9,
                        "minEventRecall": 0.9,
                        "maxFalsePositivesPerStreamHour": 0.2,
                        "maxMissedEvents": 0,
                        "maxEndToEndP95Ms": 1500,
                        "minAverageFps": 10,
                    },
                    "cooldownDedupPass": True,
                    "resourceUsage": {
                        "cpuPeakPercent": 60,
                        "memoryPeakMiB": 2048,
                        "acceleratorMemoryPeakMiB": 4096,
                    },
                }
            )
    elif evidence_type == "weakNetwork30Minutes":
        report.update(
            {
                "disconnectedMinutes": 30,
                "continuedAnalysis": True,
                "queueRestartVerified": True,
                "recoveryVerified": True,
                "events": {"generated": 180, "uploaded": 180, "duplicates": 0, "missing": 0},
                "media": {"generated": 360, "uploaded": 360, "duplicates": 0, "missing": 0},
                "pendingAfterRecovery": 0,
                "integrityFailures": 0,
                "recoverySeconds": 35,
            }
        )
    elif evidence_type == "apiLoadP95":
        report.update(
            {
                "adminApi": {
                    "requests": 600,
                    "success": 600,
                    "concurrency": 20,
                    "p95Ms": 120,
                    "endpoints": [f"/admin-api/resource-{index}" for index in range(6)],
                },
                "runtime": {
                    "targetStreamCount": 8,
                    "testedStreamCount": 8,
                    "analysisFps": 15,
                    "inferenceP95Ms": 45,
                    "cpuPeakPercent": 65,
                    "memoryPeakMiB": 4096,
                    "acceleratorMemoryPeakMiB": 6144,
                },
                "eventVisibleP95Ms": 850,
            }
        )
    elif evidence_type == "securityScan":
        for scan in report["scans"]:
            scan.update(
                {
                    "status": "PASS",
                    "scanner": "scanner",
                    "scannerVersion": "1.0",
                    "target": f"target-{scan['code']}",
                    "targetDigest": "sha256:" + "c" * 64,
                    "critical": 0,
                    "high": 0,
                    "medium": 1,
                    "low": 2,
                }
            )
        for control in report["controls"]:
            control.update({"status": "PASS", "summary": "verified by field test"})
    elif evidence_type == "edgeRollback":
        report.update(
            {
                "nodeId": "edge-001",
                "fromVersion": "1.0.0",
                "attemptedVersion": "1.0.1-bad",
                "finalVersion": "1.0.0",
                "packageSha256": "d" * 64,
                "signatureVerified": True,
                "healthFailureDetected": True,
                "rollbackSucceeded": True,
                "heartbeatRestored": True,
                "tasksRestored": True,
                "offlineReplayVerified": True,
            }
        )
    elif evidence_type == "observabilityDashboard":
        report.update(
            {
                "dashboardUrl": "https://monitor.example.invalid/d/linsight",
                "coverage": sorted(MODULE.OBSERVABILITY_COVERAGE),
                "alertRoutes": [
                    {
                        "name": "runtime-down",
                        "channel": "on-call",
                        "owner": "video-platform-team",
                        "testStatus": "PASS",
                    }
                ],
                "dashboardCaptured": True,
            }
        )
    run_id = report["runId"]
    if evidence_type == "weakNetwork30Minutes":
        raw.write_text(
            json.dumps(
                collector_artifact(
                    run_id,
                    {
                        "observedSeconds": 1800,
                        "controlPlaneConfigured": True,
                        "controlPlaneReachableSamples": 0,
                        "runningTasksMin": 1,
                        "analysisFpsMin": 15,
                        "activeStreamsMax": 1,
                        "pendingEventsFirst": 0,
                        "pendingEventsMax": 180,
                        "evidenceBacklogBytesFirst": 0,
                        "evidenceBacklogBytesMax": 1024,
                        "missingMediaFilesMax": 0,
                        "deadLetterTransitionsFirst": 0,
                        "deadLetterTransitionsMax": 0,
                        "deadLetterTransitionsFinal": 0,
                    },
                )
            ),
            encoding="utf-8",
        )
        recovery = root / "raw/weakNetwork30Minutes-recovery.json"
        recovery.write_text(
            json.dumps(
                collector_artifact(
                    run_id,
                    {
                        "observedSeconds": 0,
                        "controlPlaneConfigured": True,
                        "controlPlaneReachableSamples": 1,
                        "pendingEventsFinal": 0,
                        "pendingTransitionsFinal": 0,
                        "missingMediaFilesMax": 0,
                        "deadLetterTransitionsFirst": 0,
                        "deadLetterTransitionsMax": 0,
                        "deadLetterTransitionsFinal": 0,
                    },
                )
            ),
            encoding="utf-8",
        )
        report["rawArtifacts"] = [
            {
                "path": f"../raw/{raw.name}",
                "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            },
            {
                "path": f"../raw/{recovery.name}",
                "sha256": hashlib.sha256(recovery.read_bytes()).hexdigest(),
            },
        ]
    elif evidence_type == "apiLoadP95":
        runtime_series = root / "raw/api-load-runtime-series.json"
        runtime_series.write_text(
            json.dumps(
                collector_artifact(
                    run_id,
                    {
                        "activeStreamsMax": 8,
                        "analysisFpsMin": 15,
                        "inferenceP95MillisMax": 45,
                    },
                )
            ),
            encoding="utf-8",
        )
        admin_report = root / "raw/admin-api-load-report.json"
        admin_report.write_text(json.dumps(report["adminApi"]), encoding="utf-8")
        report["rawArtifacts"] = [
            {
                "path": f"../raw/{runtime_series.name}",
                "sha256": hashlib.sha256(runtime_series.read_bytes()).hexdigest(),
            },
            {
                "path": f"../raw/{admin_report.name}",
                "sha256": hashlib.sha256(admin_report.read_bytes()).hexdigest(),
            },
        ]
    elif evidence_type == "observabilityDashboard":
        runtime_series = root / "raw/observability-runtime-series.json"
        runtime_series.write_text(
            json.dumps(collector_artifact(run_id, {}, with_snapshot=True)),
            encoding="utf-8",
        )
        dashboard = root / "raw/observability-dashboard.png"
        dashboard.write_bytes(b"valid dashboard screenshot fixture")
        report["rawArtifacts"] = [
            {
                "path": f"../raw/{runtime_series.name}",
                "sha256": hashlib.sha256(runtime_series.read_bytes()).hexdigest(),
            },
            {
                "path": f"../raw/{dashboard.name}",
                "sha256": hashlib.sha256(dashboard.read_bytes()).hexdigest(),
            },
        ]
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report, report_path


def test_all_six_structured_reports_and_assembled_manifest_pass(tmp_path) -> None:
    MODULE.initialize_workspace(tmp_path, ENVIRONMENT)
    for evidence_type in MODULE.EVIDENCE_TYPES:
        report, report_path = valid_report(evidence_type, tmp_path)
        assert MODULE.validate_evidence_report(
            report, evidence_type, report_path, tmp_path, ENVIRONMENT
        ) == []

    manifest = MODULE.assemble_manifest(tmp_path)
    assert MODULE.validate_manifest(manifest) == []
    assert RELEASE_MODULE.external_acceptance_check(manifest).status == "PASS"


def test_workspace_initialization_refuses_to_overwrite_evidence(tmp_path) -> None:
    MODULE.initialize_workspace(tmp_path, ENVIRONMENT)
    try:
        MODULE.initialize_workspace(tmp_path, ENVIRONMENT)
    except FileExistsError as error:
        assert "refusing to overwrite" in str(error)
    else:
        raise AssertionError("existing evidence workspace was overwritten")


def test_algorithm_threshold_and_full_asset_set_are_enforced(tmp_path) -> None:
    report, report_path = valid_report("algorithmAcceptance", tmp_path)
    report["modelAssets"].pop()
    report["algorithms"][0]["metrics"]["eventRecall"] = 0.1

    errors = MODULE.validate_evidence_report(
        report, "algorithmAcceptance", report_path, tmp_path, ENVIRONMENT
    )
    assert any("modelAssets missing codes" in error for error in errors)
    assert any("eventRecall does not meet" in error for error in errors)


def test_raw_artifact_hash_and_environment_binding_are_enforced(tmp_path) -> None:
    report, report_path = valid_report("weakNetwork30Minutes", tmp_path)
    raw = tmp_path / "raw/weakNetwork30Minutes.log"
    raw.write_text("tampered\n", encoding="utf-8")

    errors = MODULE.validate_evidence_report(
        report,
        "weakNetwork30Minutes",
        report_path,
        tmp_path,
        {**ENVIRONMENT, "softwareVersion": "another-version"},
    )
    assert "environment must exactly match production-acceptance.json" in errors
    assert "rawArtifacts[0].sha256 does not match" in errors


def test_plain_attachment_cannot_replace_runtime_collector_output(tmp_path) -> None:
    report, report_path = valid_report("apiLoadP95", tmp_path)
    raw = tmp_path / "raw/api-load-runtime-series.json"
    raw.write_text('{"note":"manually entered load result"}', encoding="utf-8")
    report["rawArtifacts"][0]["sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()

    errors = MODULE.validate_evidence_report(
        report, "apiLoadP95", report_path, tmp_path, ENVIRONMENT
    )

    assert any("requires a runtimeObservabilitySeries" in error for error in errors)


def test_runtime_collector_environment_and_run_id_are_bound(tmp_path) -> None:
    report, report_path = valid_report("observabilityDashboard", tmp_path)
    raw = tmp_path / "raw/observability-runtime-series.json"
    artifact = json.loads(raw.read_text(encoding="utf-8"))
    artifact["environment"] = {**ENVIRONMENT, "hardware": "different-node"}
    artifact["runId"] = "another-field-run"
    raw.write_text(json.dumps(artifact), encoding="utf-8")
    report["rawArtifacts"][0]["sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()

    errors = MODULE.validate_evidence_report(
        report, "observabilityDashboard", report_path, tmp_path, ENVIRONMENT
    )

    assert any("environment must exactly match" in error for error in errors)
    assert any("runId must exactly match" in error for error in errors)
