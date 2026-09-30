import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/release-readiness.py"
SPEC = importlib.util.spec_from_file_location("release_readiness", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def manifest(evidence_path: Path, sha256: str) -> dict:
    entry = {
        "status": "PASS",
        "summary": "verified",
        "evidenceFiles": [{"path": evidence_path.name, "sha256": sha256}],
    }
    return {
        "schemaVersion": "1.1",
        "generatedAt": datetime.now(UTC).isoformat(),
        "environment": {
            "name": "acceptance-lab",
            "hardware": "CPU/GPU fixture",
            "softwareVersion": "v1.0.0-test",
        },
        **{key: entry for key in MODULE.EXTERNAL_EVIDENCE_KEYS},
    }


def test_external_acceptance_rejects_unstructured_or_tampered_files(tmp_path) -> None:
    evidence = tmp_path / "report.json"
    evidence.write_text('{"verified":true}\n', encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    path = tmp_path / "production-acceptance.json"
    path.write_text(json.dumps(manifest(evidence, digest)), encoding="utf-8")

    unstructured = MODULE.external_acceptance_check(path)
    assert unstructured.status == "BLOCKED_EXTERNAL"
    assert "structured JSON report" in unstructured.detail

    evidence.write_text('{"verified":false}\n', encoding="utf-8")
    result = MODULE.external_acceptance_check(path)
    assert result.status == "BLOCKED_EXTERNAL"
    assert "sha256 does not match" in result.detail


def test_dependency_audit_is_fresh_and_bound_to_current_locks(tmp_path, monkeypatch) -> None:
    frontend_lock = tmp_path / "frontend/pnpm-lock.yaml"
    runtime_lock = tmp_path / "runtime/uv.lock"
    backend_pom = tmp_path / "backend/pom.xml"
    backport = (
        tmp_path
        / "backend/linsight-framework/linsight-spring-boot-starter-mybatis/src/main/java"
        / "com/baomidou/dynamic/datasource/processor/DsSpelExpressionProcessor.java"
    )
    risk = tmp_path / "docs/security/dependency-risk-acceptance.json"
    sbom = tmp_path / "artifacts/security/linsight-server-bom.cdx.json"
    report_path = tmp_path / "artifacts/security/dependency-audit-latest.json"
    frontend_lock.parent.mkdir(parents=True)
    runtime_lock.parent.mkdir(parents=True)
    backend_pom.parent.mkdir(parents=True)
    backport.parent.mkdir(parents=True)
    risk.parent.mkdir(parents=True)
    report_path.parent.mkdir(parents=True)
    frontend_lock.write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    runtime_lock.write_text("version = 1\n", encoding="utf-8")
    backend_pom.write_text("<project/>\n", encoding="utf-8")
    backport.write_text("safe backport\n", encoding="utf-8")
    risk.write_text('{"acceptedRisks":[]}\n', encoding="utf-8")
    sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    report = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "components": {
            "frontend": {
                "status": "PASS",
                "lockSha256": hashlib.sha256(frontend_lock.read_bytes()).hexdigest(),
                "vulnerabilities": {
                    "low": 0,
                    "moderate": 0,
                    "high": 0,
                    "critical": 0,
                },
            },
            "runtime": {
                "status": "PASS",
                "lockSha256": hashlib.sha256(runtime_lock.read_bytes()).hexdigest(),
                "vulnerabilityCount": 0,
            },
            "backend": {
                "status": "PASS",
                "sourceManifestSha256": MODULE.backend_dependency_manifest_sha256(),
                "unacceptedRiskCount": 0,
                "sbomSha256": hashlib.sha256(sbom.read_bytes()).hexdigest(),
                "riskAcceptanceExpiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
        },
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")

    assert MODULE.dependency_audit_check().status == "PASS"

    frontend_lock.write_text("lockfileVersion: '9.1'\n", encoding="utf-8")
    tampered = MODULE.dependency_audit_check()
    assert tampered.status == "FAIL"
    assert "lockSha256 does not match" in tampered.detail

    frontend_lock.write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    report["generatedAt"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    report_path.write_text(json.dumps(report), encoding="utf-8")
    stale = MODULE.dependency_audit_check()
    assert stale.status == "FAIL"
    assert "within the last 7 days" in stale.detail
