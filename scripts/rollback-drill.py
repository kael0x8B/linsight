#!/usr/bin/env python3
"""Execute a controlled V1 -> failed V2 -> V1 rollback drill from explicit command arrays."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "acceptance/rollback-drill.example.json"
DEFAULT_JSON = ROOT / "artifacts/production-readiness/rollback-test-report.json"
DEFAULT_MD = ROOT / "artifacts/production-readiness/rollback-test-report.md"
REQUIRED_POST_CHECKS = {
    "java-service",
    "ai-service",
    "model",
    "configuration",
    "camera",
    "data",
    "historical-events",
}
SECRET_PATTERN = re.compile(
    r"(?i)(authorization|token|password|secret|api[-_]?key)(\s*[:=]\s*)([^\s,;]+)"
)


def redact(value: str) -> str:
    return SECRET_PATTERN.sub(r"\1\2[REDACTED]", value)


def safe_command(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a non-empty command array")
    return value


def execute(name: str, command: list[str]) -> dict[str, Any]:
    started = datetime.now(UTC)
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = redact((result.stdout + result.stderr)[-4000:])
    return {
        "name": name,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exitCode": result.returncode,
        "startedAt": started.isoformat(),
        "finishedAt": datetime.now(UTC).isoformat(),
        "outputTail": output,
    }


def waiting(reason: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "WAITING_FOR_FIELD_TEST",
        "reason": reason,
        "requiredPostChecks": sorted(REQUIRED_POST_CHECKS),
        "steps": [],
    }


def run_drill(config_path: Path, execute_changes: bool) -> dict[str, Any]:
    if not config_path.is_file():
        return waiting(f"missing rollback config: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("environmentType") != "TARGET_HARDWARE":
        return waiting("environmentType must be TARGET_HARDWARE")
    if not execute_changes:
        return waiting("rerun with --execute on the isolated target after reviewing every command")
    steps = []
    try:
        for check in config.get("preChecks", []):
            steps.append(execute(f"pre:{check['name']}", safe_command(check.get("command"), check["name"])))
        steps.append(execute("upgrade-v1-to-v2", safe_command(config.get("upgradeCommand"), "upgradeCommand")))
        steps.append(execute("inject-v2-failure", safe_command(config.get("failureInjectionCommand"), "failureInjectionCommand")))
        failure = execute("detect-upgrade-failure", safe_command(config.get("failureDetectionCommand"), "failureDetectionCommand"))
        failure["status"] = "PASS" if failure["exitCode"] != 0 else "FAIL"
        steps.append(failure)
        steps.append(execute("rollback-v2-to-v1", safe_command(config.get("rollbackCommand"), "rollbackCommand")))
        for check in config.get("postChecks", []):
            steps.append(execute(f"post:{check['name']}", safe_command(check.get("command"), check["name"])))
    except (KeyError, OSError, ValueError) as error:
        return {**waiting("rollback drill configuration or execution failed"), "steps": steps, "errors": [str(error)]}
    observed_post = {value["name"].removeprefix("post:") for value in steps if value["name"].startswith("post:")}
    missing = sorted(REQUIRED_POST_CHECKS - observed_post)
    passed = not missing and all(value["status"] == "PASS" for value in steps)
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "environment": config.get("environment"),
        "fromVersion": config.get("fromVersion"),
        "attemptedVersion": config.get("attemptedVersion"),
        "finalVersion": config.get("fromVersion") if passed else "UNVERIFIED",
        "missingPostChecks": missing,
        "steps": steps,
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Rollback Test Report",
        "",
        f"- 状态：`{report['status']}`",
        f"- V1：`{report.get('fromVersion', 'UNSET')}`",
        f"- 故障 V2：`{report.get('attemptedVersion', 'UNSET')}`",
        f"- 最终版本：`{report.get('finalVersion', 'UNVERIFIED')}`",
        "",
        "| 步骤 | 结果 |",
        "| --- | --- |",
    ]
    lines.extend(f"| {value['name']} | {value['status']} |" for value in report.get("steps", []))
    if report.get("reason"):
        lines.extend(["", f"原因：{report['reason']}"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    report = run_drill(args.config.resolve(), args.execute)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.json_output)}, ensure_ascii=False))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
