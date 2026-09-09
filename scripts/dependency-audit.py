#!/usr/bin/env python3
"""Create a lock-bound dependency vulnerability report for local release gates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/security/dependency-audit-latest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backend_manifest_sha256() -> str:
    digest = hashlib.sha256()
    paths = sorted((ROOT / "backend").rglob("pom.xml"))
    paths.extend(
        [
            ROOT
            / "backend/linsight-framework/linsight-spring-boot-starter-mybatis/src/main/java"
            / "com/baomidou/dynamic/datasource/processor/DsSpelExpressionProcessor.java",
            ROOT / "docs/security/dependency-risk-acceptance.json",
        ]
    )
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def node_environment() -> dict[str, str]:
    env = os.environ.copy()
    nvm_root = Path.home() / ".nvm/versions/node"
    candidates = sorted(
        (path for path in nvm_root.glob("v*") if (path / "bin/corepack").is_file()),
        reverse=True,
    )
    compatible = [
        path
        for path in candidates
        if path.name.startswith("v24.") or path.name.startswith("v22.")
    ]
    if compatible:
        env["PATH"] = f"{compatible[0] / 'bin'}:{env.get('PATH', '')}"
    return env


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def java_environment() -> dict[str, str]:
    env = os.environ.copy()
    java_home = run(["/usr/libexec/java_home", "-v", "17"], ROOT)
    if java_home.returncode == 0:
        home = java_home.stdout.strip()
        env["JAVA_HOME"] = home
        env["PATH"] = f"{home}/bin:{env.get('PATH', '')}"
    return env


def curl_json(url: str, payload: dict | None = None) -> dict:
    command = [
        "curl",
        "-fsS",
        "--max-time",
        "90",
        "-H",
        "Accept: application/json",
        "-H",
        "User-Agent: linsight-dependency-audit/1.0",
    ]
    if payload is not None:
        command.extend(
            ["-H", "Content-Type: application/json", "--data-binary", "@-"]
        )
    command.append(url)
    result = subprocess.run(
        command,
        cwd=ROOT,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {result.stderr[-1000:].strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid JSON from {url}") from error


def frontend_audit() -> dict:
    lock = ROOT / "frontend/pnpm-lock.yaml"
    result = run(
        [
            "corepack",
            "pnpm@11.7.0",
            "audit",
            "--prod",
            "--registry=https://registry.npmjs.org",
            "--json",
        ],
        ROOT / "frontend",
        node_environment(),
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"pnpm audit did not return JSON (exit={result.returncode}): "
            f"{result.stderr[-1000:].strip()}"
        ) from error
    metadata = value.get("metadata", {})
    counts = metadata.get("vulnerabilities", {})
    advisories = [
        {
            "id": str(advisory.get("id", key)),
            "module": advisory.get("module_name"),
            "severity": advisory.get("severity"),
            "title": advisory.get("title"),
            "url": advisory.get("url"),
            "patchedVersions": advisory.get("patched_versions"),
        }
        for key, advisory in sorted(value.get("advisories", {}).items())
    ]
    lock_text = lock.read_text(encoding="utf-8")
    snapshots = lock_text.split("\nsnapshots:\n", 1)
    lock_dependency_count = (
        sum(1 for line in snapshots[1].splitlines() if re.match(r"^  \S.*:\s*(?:\{\})?$", line))
        if len(snapshots) == 2
        else 0
    )
    dependency_count = int(metadata.get("dependencies", 0)) or lock_dependency_count
    return {
        "status": "PASS" if not advisories else "FAIL",
        "lockFile": "frontend/pnpm-lock.yaml",
        "lockSha256": sha256(lock),
        "registry": "https://registry.npmjs.org",
        "dependencies": dependency_count,
        "vulnerabilities": {
            name: int(counts.get(name, 0))
            for name in ("info", "low", "moderate", "high", "critical")
        },
        "advisories": advisories,
    }


def runtime_audit() -> dict:
    lock = ROOT / "runtime/uv.lock"
    export = run(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--format",
            "requirements-txt",
            "--no-emit-project",
        ],
        ROOT / "runtime",
    )
    if export.returncode != 0:
        raise RuntimeError(f"uv export failed: {export.stderr[-1000:].strip()}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8") as file:
        file.write(export.stdout)
        file.flush()
        result = run(
            [
                "uvx",
                "--from",
                "pip-audit",
                "pip-audit",
                "-r",
                file.name,
                "--no-deps",
                "--disable-pip",
                "--format",
                "json",
            ],
            ROOT / "runtime",
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"pip-audit did not return JSON (exit={result.returncode}): "
            f"{result.stderr[-1000:].strip()}"
        ) from error
    dependencies = value.get("dependencies", [])
    vulnerabilities = [
        {
            "package": dependency.get("name"),
            "version": dependency.get("version"),
            "id": vulnerability.get("id"),
            "fixVersions": vulnerability.get("fix_versions", []),
            "description": vulnerability.get("description"),
        }
        for dependency in dependencies
        for vulnerability in dependency.get("vulns", [])
    ]
    return {
        "status": "PASS" if not vulnerabilities else "FAIL",
        "lockFile": "runtime/uv.lock",
        "lockSha256": sha256(lock),
        "index": "PyPI advisory service via pip-audit",
        "dependencies": len(dependencies),
        "vulnerabilityCount": len(vulnerabilities),
        "vulnerabilities": vulnerabilities,
    }


def normalize_purl(purl: str) -> str:
    return purl.split("?", 1)[0]


def backend_audit() -> dict:
    backend = ROOT / "backend"
    env = java_environment()
    install = run(["mvn", "-q", "-DskipTests", "install"], backend, env)
    if install.returncode != 0:
        raise RuntimeError(f"Maven install failed: {(install.stdout + install.stderr)[-2000:]}")
    bom = backend / "linsight-server/target/linsight-server-bom.json"
    generate = run(
        [
            "mvn",
            "-q",
            "-pl",
            "linsight-server",
            "-DskipTests",
            "-Dcyclonedx.skipAttach=true",
            "-DincludeTestScope=false",
            "-DoutputFormat=json",
            "-DoutputName=linsight-server-bom",
            "org.cyclonedx:cyclonedx-maven-plugin:2.9.1:makeBom",
        ],
        backend,
        env,
    )
    if generate.returncode != 0 or not bom.is_file():
        raise RuntimeError(
            f"CycloneDX generation failed: {(generate.stdout + generate.stderr)[-2000:]}"
        )
    value = json.loads(bom.read_text(encoding="utf-8"))
    components = [
        component
        for component in value.get("components", [])
        if component.get("purl")
        and not component["purl"].startswith("pkg:maven/com.linsight/")
    ]
    batch = curl_json(
        "https://api.osv.dev/v1/querybatch",
        {"queries": [{"package": {"purl": item["purl"]}} for item in components]},
    )
    results = batch.get("results", [])
    if len(results) != len(components):
        raise RuntimeError("OSV querybatch result count does not match the SBOM")

    risk_path = ROOT / "docs/security/dependency-risk-acceptance.json"
    risks = json.loads(risk_path.read_text(encoding="utf-8"))
    if risks.get("schemaVersion") != "1.0":
        raise RuntimeError("dependency risk acceptance schemaVersion must be 1.0")
    try:
        reviewed_at = datetime.fromisoformat(risks["reviewedAt"].replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(risks["expiresAt"].replace("Z", "+00:00"))
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError("dependency risk acceptance timestamps are invalid") from error
    now = datetime.now(UTC)
    if reviewed_at.tzinfo is None or expires_at.tzinfo is None:
        raise RuntimeError("dependency risk acceptance timestamps require timezone")
    if reviewed_at > now or expires_at <= now or expires_at > reviewed_at + timedelta(days=366):
        raise RuntimeError("dependency risk acceptance is expired or has an invalid review window")
    accepted = {
        (entry.get("id"), entry.get("package")): entry
        for entry in risks.get("acceptedRisks", [])
    }
    findings: list[dict] = []
    detail_cache: dict[str, dict] = {}
    for component, result in zip(components, results, strict=True):
        package = normalize_purl(component["purl"])
        for item in result.get("vulns", []):
            identifier = item["id"]
            if identifier not in detail_cache:
                detail_cache[identifier] = curl_json(
                    f"https://api.osv.dev/v1/vulns/{identifier}"
                )
            detail = detail_cache[identifier]
            severity = str(
                detail.get("database_specific", {}).get("severity", "UNKNOWN")
            ).upper()
            exception = accepted.get((identifier, package))
            is_accepted = exception is not None and severity in {"LOW", "MODERATE"}
            findings.append(
                {
                    "id": identifier,
                    "package": package,
                    "version": component.get("version"),
                    "severity": severity,
                    "summary": detail.get("summary"),
                    "url": f"https://osv.dev/vulnerability/{identifier}",
                    "acceptedRisk": is_accepted,
                    "riskReason": exception.get("reason") if is_accepted else None,
                }
            )
    unaccepted = [finding for finding in findings if not finding["acceptedRisk"]]
    artifact = OUTPUT.parent / "linsight-server-bom.cdx.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(bom, artifact)
    return {
        "status": "PASS" if not unaccepted else "FAIL",
        "sourceManifestSha256": backend_manifest_sha256(),
        "sbomFile": "artifacts/security/linsight-server-bom.cdx.json",
        "sbomSha256": sha256(artifact),
        "advisoryService": "https://api.osv.dev/v1/querybatch",
        "dependencies": len(components),
        "vulnerabilityCount": len(findings),
        "acceptedRiskCount": len(findings) - len(unaccepted),
        "unacceptedRiskCount": len(unaccepted),
        "riskAcceptanceFile": "docs/security/dependency-risk-acceptance.json",
        "riskAcceptanceSha256": sha256(risk_path),
        "riskAcceptanceExpiresAt": risks["expiresAt"],
        "vulnerabilities": findings,
    }


def main() -> int:
    report = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "components": {},
        "limitations": [
            "This report covers frontend production, Python runtime and local Java server dependencies.",
            "Production container images and OS packages remain required external securityScan evidence.",
        ],
    }
    for name, audit in (
        ("frontend", frontend_audit),
        ("runtime", runtime_audit),
        ("backend", backend_audit),
    ):
        try:
            report["components"][name] = audit()
        except (OSError, RuntimeError) as error:
            report["components"][name] = {"status": "FAIL", "error": str(error)}
            report["status"] = "FAIL"
    if any(
        component.get("status") != "PASS"
        for component in report["components"].values()
    ):
        report["status"] = "FAIL"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
