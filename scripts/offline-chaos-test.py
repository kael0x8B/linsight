#!/usr/bin/env python3
"""Run or verify controlled offline/weak-network field scenarios without faking evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "acceptance/offline-chaos.example.json"
DEFAULT_OUTPUT = ROOT / "artifacts/production-readiness/offline-chaos-report.json"
REQUIRED_SCENARIOS = {
    "disconnect-5m",
    "disconnect-10m",
    "disconnect-30m",
    "disconnect-60m",
    "dns-failure",
    "tcp-disconnect",
    "http-timeout",
    "http-500",
    "http-429",
    "server-unreachable",
}


def waiting(reason: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "WAITING_FOR_FIELD_TEST",
        "reason": reason,
        "requiredScenarios": sorted(REQUIRED_SCENARIOS),
        "results": [],
    }


def load_json(base: Path, relative: str) -> dict[str, Any]:
    path = (base / relative).resolve()
    path.relative_to(base.resolve())
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_scenario(
    scenario: dict[str, Any], outage: dict[str, Any], recovery: dict[str, Any], delivery: dict[str, Any]
) -> dict[str, Any]:
    outage_summary = outage.get("summary", {})
    recovery_summary = recovery.get("summary", {})
    minutes = float(scenario.get("durationSeconds", 0)) / 60
    queue_growth = max(
        0,
        int(outage_summary.get("pendingEventsMax", 0))
        - int(outage_summary.get("pendingEventsFirst", 0)),
    )
    checks = {
        "faultActuallyApplied": bool(scenario.get("faultApplied")),
        "controlPlaneUnavailable": int(outage_summary.get("controlPlaneReachableSamples", -1)) == 0,
        "cameraContinued": int(outage_summary.get("activeStreamsMax", 0)) > 0
        and float(outage_summary.get("inputFpsMin", 0)) > 0,
        "aiContinued": int(outage_summary.get("runningTasksMin", 0)) > 0
        and float(outage_summary.get("analysisFpsMin", 0)) > 0,
        "eventsPersisted": int(outage_summary.get("pendingEventsMax", 0))
        >= int(outage_summary.get("pendingEventsFirst", 0)),
        "mediaIntegrity": int(outage_summary.get("missingMediaFilesMax", 1)) == 0,
        "queueBounded": queue_growth / max(minutes, 0.001)
        <= float(scenario.get("maxQueueGrowthPerMinute", 1000)),
        "diskSafe": float(outage_summary.get("systemDiskPeakPercent", 100))
        <= float(scenario.get("maxDiskPercent", 90)),
        "automaticRecovery": int(recovery_summary.get("controlPlaneReachableSamples", 0)) > 0,
        "eventQueueDrained": int(recovery_summary.get("pendingEventsFinal", -1)) == 0,
        "transitionQueueDrained": int(recovery_summary.get("pendingTransitionsFinal", -1)) == 0,
        "noNewDeadLetters": int(recovery_summary.get("deadLetterTransitionsFinal", 1))
        <= int(recovery_summary.get("deadLetterTransitionsFirst", 0)),
        "exactlyOnceEvents": int(delivery.get("generatedEvents", -1))
        == int(delivery.get("uploadedEvents", -2))
        and int(delivery.get("duplicateEvents", -1)) == 0
        and int(delivery.get("missingEvents", -1)) == 0,
        "exactlyOnceMedia": int(delivery.get("generatedMedia", -1))
        == int(delivery.get("uploadedMedia", -2))
        and int(delivery.get("duplicateMedia", -1)) == 0
        and int(delivery.get("missingMedia", -1)) == 0,
        "idempotencyVerified": delivery.get("idempotencyVerified") is True,
        "eventOrderVerified": delivery.get("eventOrderVerified") is True,
        "restartPersistenceVerified": delivery.get("restartPersistenceVerified") is True,
    }
    return {
        "name": scenario.get("name"),
        "faultType": scenario.get("faultType"),
        "durationSeconds": scenario.get("durationSeconds"),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "queueGrowthPerMinute": round(queue_growth / max(minutes, 0.001), 3),
        "diskPeakPercent": outage_summary.get("systemDiskPeakPercent"),
        "recoverySeconds": delivery.get("recoverySeconds"),
    }


def execute_commands(scenario: dict[str, Any]) -> None:
    for key in ("applyCommand", "captureOutageCommand", "recoverCommand", "captureRecoveryCommand", "deliveryVerificationCommand"):
        command = scenario.get(key)
        if not isinstance(command, list) or not command or not all(isinstance(value, str) for value in command):
            raise ValueError(f"{scenario.get('name')}.{key} must be a non-empty command array")
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"{scenario.get('name')}.{key} failed with {result.returncode}")


def evaluate(config_path: Path, execute: bool = False) -> dict[str, Any]:
    if not config_path.is_file():
        return waiting(f"missing chaos config: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    results = []
    errors = []
    declared = set()
    for scenario in config.get("scenarios", []):
        name = scenario.get("name")
        if isinstance(name, str):
            declared.add(name)
        try:
            if execute:
                execute_commands(scenario)
            outage = load_json(config_path.parent, scenario["outageArtifact"])
            recovery = load_json(config_path.parent, scenario["recoveryArtifact"])
            delivery = load_json(config_path.parent, scenario["deliveryArtifact"])
            results.append(validate_scenario(scenario, outage, recovery, delivery))
        except (KeyError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            errors.append(f"{name or 'unknown'}: {error}")
    missing = sorted(REQUIRED_SCENARIOS - declared)
    status = (
        "PASS"
        if not missing and not errors and results and all(value["status"] == "PASS" for value in results)
        else "WAITING_FOR_FIELD_TEST"
    )
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": status,
        "environment": config.get("environment"),
        "missingScenarios": missing,
        "errors": errors,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--execute", action="store_true", help="run the explicit command arrays before validation")
    args = parser.parse_args()
    report = evaluate(args.config.resolve(), args.execute)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
