#!/usr/bin/env python3
"""Generate a Docker/Java/Python/OS security release report with field blockers."""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "artifacts/production-readiness/security-release-report.json"
DEFAULT_MD = ROOT / "artifacts/production-readiness/security-release-report.md"


def run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return result.returncode, (result.stdout + result.stderr)[-20000:].strip()


def dockerfile_findings() -> list[dict[str, str]]:
    findings = []
    for path in sorted((ROOT / "backend").glob("*/Dockerfile")):
        text = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(ROOT))
        from_match = re.search(r"^FROM\s+(\S+)", text, re.MULTILINE)
        image = from_match.group(1) if from_match else "UNKNOWN"
        if "@sha256:" not in image:
            findings.append({"severity": "HIGH", "target": relative, "issue": "base image is not pinned by digest"})
        if not re.search(r"^USER\s+(?!root\b)\S+", text, re.MULTILINE):
            findings.append({"severity": "HIGH", "target": relative, "issue": "container runs as root"})
        if re.search(r"\b(?:curl|wget|ssh|telnet|netcat|nc)\b", text, re.IGNORECASE):
            findings.append({"severity": "MEDIUM", "target": relative, "issue": "review unnecessary network tooling"})
    return findings


def dependency_summary() -> dict[str, Any]:
    path = ROOT / "artifacts/security/dependency-audit-latest.json"
    if not path.is_file():
        return {"status": "MISSING", "reason": "run make dependency-audit"}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "FAIL", "reason": "dependency audit JSON is invalid"}
    return {
        "status": report.get("status", "FAIL"),
        "generatedAt": report.get("generatedAt"),
        "components": report.get("components", {}),
    }


def os_baseline(target: bool) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "kernel": platform.platform(),
        "ssh": "NOT_INSTALLED",
        "firewall": "UNKNOWN",
        "openPorts": [],
        "defaultAccounts": "REQUIRES_SITE_REVIEW",
        "defaultPasswords": "REQUIRES_SITE_REVIEW",
        "dangerousServices": "REQUIRES_SITE_REVIEW",
    }
    if shutil.which("ss"):
        code, output = run(["ss", "-lntup"])
        checks["openPorts"] = output.splitlines() if code == 0 else ["COLLECTION_FAILED"]
    elif shutil.which("lsof"):
        code, output = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
        checks["openPorts"] = output.splitlines() if code == 0 else ["COLLECTION_FAILED"]
    if shutil.which("sshd"):
        code, output = run(["sshd", "-T"])
        checks["ssh"] = output.splitlines() if code == 0 else "COLLECTION_FAILED"
    if shutil.which("ufw"):
        _, checks["firewall"] = run(["ufw", "status", "verbose"])
    elif shutil.which("firewall-cmd"):
        _, checks["firewall"] = run(["firewall-cmd", "--list-all"])
    checks["status"] = "COLLECTED_TARGET" if target else "LOCAL_ONLY_NOT_ACCEPTANCE"
    return checks


def trivy_image(image: str) -> dict[str, Any]:
    trivy = shutil.which("trivy")
    if not trivy:
        return scout_image(image)
    result = subprocess.run(
        [trivy, "image", "--quiet", "--format", "json", image],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {"target": image, "status": "SCAN_FAILED", "error": result.stderr[-2000:]}
    value = json.loads(result.stdout)
    vulnerabilities = [
        finding
        for item in value.get("Results", [])
        for finding in item.get("Vulnerabilities") or []
    ]
    counts = {
        level: sum(str(item.get("Severity", "")).upper() == level for item in vulnerabilities)
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    }
    return {
        "target": image,
        "status": "PASS" if counts["CRITICAL"] == counts["HIGH"] == 0 else "FAIL",
        "critical": counts["CRITICAL"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
        "findings": [
            {
                "id": item.get("VulnerabilityID"),
                "severity": item.get("Severity"),
                "package": item.get("PkgName"),
                "installedVersion": item.get("InstalledVersion"),
                "fixedVersion": item.get("FixedVersion"),
            }
            for item in vulnerabilities
            if str(item.get("Severity", "")).upper() in {"CRITICAL", "HIGH"}
        ],
    }


def scout_image(image: str) -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        return {"target": image, "status": "MISSING_SCANNER", "critical": None, "high": None}
    try:
        result = subprocess.run(
            [docker, "scout", "cves", "--format", "sarif", f"local://{image}"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"target": image, "status": "SCAN_FAILED", "error": "Docker Scout timeout"}
    if result.returncode != 0:
        return {"target": image, "status": "SCAN_FAILED", "error": result.stderr[-2000:]}
    try:
        value = json.loads(result.stdout)
        run_value = value.get("runs", [{}])[0]
        rules = {
            item.get("id"): item
            for item in run_value.get("tool", {}).get("driver", {}).get("rules", [])
        }
        findings = []
        counts = {level: 0 for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
        for item in run_value.get("results", []):
            rule = rules.get(item.get("ruleId"), {})
            severity = str(
                rule.get("properties", {}).get("cvssV3_severity", "UNKNOWN")
            ).upper()
            if severity in counts:
                counts[severity] += 1
            if severity in {"CRITICAL", "HIGH"}:
                purls = rule.get("properties", {}).get("purls", [])
                findings.append(
                    {
                        "id": item.get("ruleId"),
                        "severity": severity,
                        "package": purls[0] if purls else "UNKNOWN",
                        "fixedVersion": rule.get("properties", {}).get("fixed_version"),
                    }
                )
    except (IndexError, json.JSONDecodeError, TypeError) as error:
        return {"target": image, "status": "SCAN_FAILED", "error": str(error)}
    return {
        "target": image,
        "scanner": "Docker Scout",
        "status": "PASS" if counts["CRITICAL"] == counts["HIGH"] == 0 else "FAIL",
        "critical": counts["CRITICAL"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
        "findings": findings,
    }


def build_report(images: list[str], target: bool) -> dict[str, Any]:
    static_findings = dockerfile_findings()
    image_scans = [trivy_image(image) for image in images]
    critical_high = [
        item for item in static_findings if item["severity"] in {"CRITICAL", "HIGH"}
    ] + [
        finding
        for scan in image_scans
        for finding in scan.get("findings", [])
        if finding.get("severity") in {"CRITICAL", "HIGH"}
    ]
    external_ready = bool(images) and all(scan.get("status") == "PASS" for scan in image_scans)
    dependency = dependency_summary()
    status = (
        "PASS"
        if target and external_ready and dependency.get("status") == "PASS" and not critical_high
        else "WAITING_FOR_FIELD_TEST"
    )
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": status,
        "scope": "TARGET_PRODUCTION" if target else "LOCAL_ENGINEERING",
        "criticalAndHigh": critical_high,
        "docker": {"staticFindings": static_findings, "imageScans": image_scans},
        "javaPythonFrontendDependencies": dependency,
        "operatingSystem": os_baseline(target),
        "requiredBeforePass": [
            "scan every immutable production image digest",
            "scan the final Java artifact and target OS packages",
            "review SSH, firewall, open ports, default accounts/passwords and dangerous services on target",
            "confirm no Critical or High finding remains",
        ],
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Security Release Report",
        "",
        f"- 状态：`{report['status']}`",
        f"- 范围：`{report['scope']}`",
        f"- 生成时间：`{report['generatedAt']}`",
        "",
        "## Critical / High",
        "",
    ]
    if report["criticalAndHigh"]:
        lines.extend(
            f"- **{item.get('severity')}** {item.get('target', item.get('package', 'unknown'))}: {item.get('issue', item.get('id', 'finding'))}"
            for item in report["criticalAndHigh"]
        )
    else:
        lines.append("当前已执行范围内未发现 Critical/High；目标镜像和目标 OS 未扫描时不能据此判定 PASS。")
    lines.extend(["", "## 发布前仍需", ""])
    lines.extend(f"- {value}" for value in report["requiredBeforePass"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--target", action="store_true", help="declare this run is on final production hardware")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    report = build_report(args.image, args.target)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.json_output)}, ensure_ascii=False))
    return 0 if report["status"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
