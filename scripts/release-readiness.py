#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from production_evidence import EVIDENCE_TYPES, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_EVIDENCE_KEYS = set(EVIDENCE_TYPES)


@dataclass
class Check:
    name: str
    status: str
    detail: str
    duration_seconds: float = 0


def command_check(
    name: str, command: list[str], cwd: Path, env: dict[str, str]
) -> Check:
    started = time.monotonic()
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, check=False
    )
    detail = (result.stdout + result.stderr)[-4000:].strip()
    return Check(
        name,
        "PASS" if result.returncode == 0 else "FAIL",
        detail or f"exitCode={result.returncode}",
        round(time.monotonic() - started, 3),
    )


def source_integrity_check() -> Check:
    forbidden = (
        "\ufffd",
        "\u00c3",
        "\u00c2",
        "\u00e2\u20ac\u2122",
        "\u00e2\u20ac\u0153",
        "\u00e2\u20ac",
    )
    suffixes = {".java", ".py", ".ts", ".vue", ".sql", ".md", ".yaml", ".yml"}
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(
            part in {"node_modules", "target", ".venv", ".git", "dist"}
            for part in path.parts
        ):
            continue
        value = path.read_text(encoding="utf-8", errors="replace")
        if any(token in value for token in forbidden):
            hits.append(str(path.relative_to(ROOT)))
    return Check(
        "UTF-8 source integrity",
        "PASS" if not hits else "FAIL",
        "no mojibake markers" if not hits else "markers found: " + ", ".join(hits[:20]),
    )


def migration_check() -> Check:
    migrations = sorted((ROOT / "backend/sql/mysql/migrations/ai-video").glob("V*.sql"))
    names = [path.name.split("__", 1)[0] for path in migrations]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    runner = ROOT / "scripts/apply-ai-video-migrations.sh"
    runner_text = runner.read_text(encoding="utf-8") if runner.is_file() else ""
    runner_forces_utf8mb4 = "mysql --default-character-set=utf8mb4" in runner_text
    status = "PASS" if not duplicates and runner_forces_utf8mb4 else "FAIL"
    return Check(
        "database migration contract",
        status,
        f"count={len(migrations)}, duplicateVersions={duplicates}, "
        f"runnerForcesUtf8mb4={runner_forces_utf8mb4}",
    )


def source_credential_check() -> Check:
    roots = (
        ROOT / "backend/linsight-module-ai-video/linsight-module-ai-video-server/src/main",
        ROOT / "frontend/apps/web-antd/src",
        ROOT / "runtime/ai_runtime/app",
        ROOT / "runtime/edge_agent/app",
        ROOT / "deploy",
    )
    suffixes = {".java", ".py", ".ts", ".vue", ".yaml", ".yml"}
    patterns = {
        "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "cloud-access-key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "credential-in-url": re.compile(r"\b(?:https?|rtsp)://[^/\s:@]+:[^/\s@]+@"),
    }
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            value = path.read_text(encoding="utf-8", errors="replace")
            for name, pattern in patterns.items():
                if pattern.search(value):
                    hits.append(f"{path.relative_to(ROOT)}:{name}")
    return Check(
        "source credential scan",
        "PASS" if not hits else "FAIL",
        "no embedded credentials or private keys" if not hits else ", ".join(hits[:20]),
    )


def backend_dependency_manifest_sha256() -> str:
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


def known_dependency_mitigation_check() -> Check:
    backport = (
        ROOT
        / "backend/linsight-framework/linsight-spring-boot-starter-mybatis/src/main/java"
        / "com/baomidou/dynamic/datasource/processor/DsSpelExpressionProcessor.java"
    )
    invalid: list[str] = []
    try:
        content = backport.read_text(encoding="utf-8")
    except OSError as error:
        return Check("known dependency mitigations", "FAIL", f"missing SpEL backport: {error}")
    for token in ("context.setTypeLocator", "context.setConstructorResolvers(Collections.emptyList())"):
        if token not in content:
            invalid.append(f"SpEL backport missing {token}")
    for path in (ROOT / "backend").rglob("*.java"):
        if "target" in path.parts or "src/test" in path.as_posix():
            continue
        value = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"@DS\s*\(", value):
            invalid.append(f"dynamic datasource expression introduced: {path.relative_to(ROOT)}")
        if "httpJobHandler" in value:
            invalid.append(f"XXL-JOB sample HTTP handler introduced: {path.relative_to(ROOT)}")
    return Check(
        "known dependency mitigations",
        "PASS" if not invalid else "FAIL",
        "SpEL type/constructor access blocked; no @DS expression or XXL sample HTTP handler"
        if not invalid
        else "; ".join(invalid[:20]),
    )


def dependency_audit_check() -> Check:
    path = ROOT / "artifacts/security/dependency-audit-latest.json"
    if not path.is_file():
        return Check(
            "locked dependency audit",
            "FAIL",
            "missing artifacts/security/dependency-audit-latest.json; run make dependency-audit",
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Check("locked dependency audit", "FAIL", f"invalid report: {error}")
    invalid: list[str] = []
    if value.get("schemaVersion") != "1.0":
        invalid.append("schemaVersion must be 1.0")
    if value.get("status") != "PASS":
        invalid.append("report status is not PASS")
    try:
        generated = datetime.fromisoformat(
            str(value.get("generatedAt")).replace("Z", "+00:00")
        )
        if generated.tzinfo is None:
            raise ValueError("timezone missing")
        now = datetime.now(UTC)
        if generated > now + timedelta(minutes=5) or generated < now - timedelta(days=7):
            invalid.append("generatedAt must be within the last 7 days")
    except (TypeError, ValueError):
        invalid.append("generatedAt must be an ISO-8601 timestamp with timezone")
    expected = {
        "frontend": ROOT / "frontend/pnpm-lock.yaml",
        "runtime": ROOT / "runtime/uv.lock",
    }
    components = value.get("components")
    if not isinstance(components, dict):
        invalid.append("components must be an object")
        components = {}
    for name, lock in expected.items():
        component = components.get(name)
        if not isinstance(component, dict):
            invalid.append(f"components.{name} is missing")
            continue
        if component.get("status") != "PASS":
            invalid.append(f"components.{name}.status is not PASS")
        actual_hash = hashlib.sha256(lock.read_bytes()).hexdigest()
        if component.get("lockSha256") != actual_hash:
            invalid.append(f"components.{name}.lockSha256 does not match current lock")
    frontend = components.get("frontend", {})
    counts = frontend.get("vulnerabilities", {}) if isinstance(frontend, dict) else {}
    try:
        frontend_zero = all(
            int(counts.get(level, -1)) == 0
            for level in ("low", "moderate", "high", "critical")
        )
    except (TypeError, ValueError):
        frontend_zero = False
    if not frontend_zero:
        invalid.append("frontend vulnerability counts are not all zero")
    runtime = components.get("runtime", {})
    if not isinstance(runtime, dict) or runtime.get("vulnerabilityCount") != 0:
        invalid.append("runtime vulnerabilityCount is not zero")
    backend = components.get("backend", {})
    if not isinstance(backend, dict):
        invalid.append("components.backend is missing")
    else:
        if backend.get("status") != "PASS":
            invalid.append("components.backend.status is not PASS")
        if backend.get("sourceManifestSha256") != backend_dependency_manifest_sha256():
            invalid.append("components.backend.sourceManifestSha256 does not match current source")
        if backend.get("unacceptedRiskCount") != 0:
            invalid.append("backend has unaccepted dependency risks")
        sbom = ROOT / "artifacts/security/linsight-server-bom.cdx.json"
        if not sbom.is_file() or backend.get("sbomSha256") != hashlib.sha256(sbom.read_bytes()).hexdigest():
            invalid.append("backend SBOM is missing or its SHA256 does not match")
        try:
            expires = datetime.fromisoformat(
                str(backend.get("riskAcceptanceExpiresAt")).replace("Z", "+00:00")
            )
            if expires.tzinfo is None or expires <= datetime.now(UTC):
                invalid.append("backend dependency risk acceptance is expired")
        except (TypeError, ValueError):
            invalid.append("backend dependency risk acceptance expiry is invalid")
    return Check(
        "locked dependency audit",
        "PASS" if not invalid else "FAIL",
        "frontend/runtime locks and backend source manifest match a fresh dependency audit"
        if not invalid
        else "; ".join(invalid),
    )


def external_acceptance_check(path: Path) -> Check:
    if not path.exists():
        return Check(
            "production evidence",
            "BLOCKED_EXTERNAL",
            f"missing {path}; initialize the field workspace with scripts/production_evidence.py init",
        )
    invalid = validate_manifest(path)
    return Check(
        "production evidence",
        "PASS" if not invalid else "BLOCKED_EXTERNAL",
        "all six structured production reports and raw artifact hashes are valid"
        if not invalid
        else f"invalid={invalid}",
    )


def local_load_smoke(url: str, requests: int = 100, concurrency: int = 10) -> Check:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request() -> tuple[int, float]:
        started = time.monotonic()
        try:
            with opener.open(url, timeout=5) as response:
                status = response.status
        except (urllib.error.URLError, TimeoutError, OSError):
            status = 0
        return status, (time.monotonic() - started) * 1000

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        values = list(pool.map(lambda _: request(), range(requests)))
    codes, durations = zip(*values, strict=True)
    p95 = statistics.quantiles(durations, n=100)[94]
    passed = all(code == 200 for code in codes) and p95 < 500
    successful = sum(code == 200 for code in codes)
    return Check(
        "local API load smoke",
        "PASS" if passed else "FAIL",
        f"url={url}, requests={requests}, success={successful}, "
        f"concurrency={concurrency}, p95Ms={p95:.2f}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LInsight V1.0 release gates")
    parser.add_argument(
        "--evidence", type=Path, default=ROOT / "evidence/production-acceptance.json"
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--health-url", default="http://127.0.0.1:48888/actuator/health"
    )
    args = parser.parse_args()

    env = os.environ.copy()
    java_home = subprocess.run(
        ["/usr/libexec/java_home", "-v", "17"],
        text=True,
        capture_output=True,
        check=False,
    )
    if java_home.returncode == 0:
        env["JAVA_HOME"] = java_home.stdout.strip()
        env["PATH"] = f"{env['JAVA_HOME']}/bin:{env['PATH']}"
    node_bin = Path.home() / ".nvm/versions/node/v22.19.0/bin"
    if node_bin.is_dir():
        env["PATH"] = f"{node_bin}:{env['PATH']}"

    checks = [
        migration_check(),
        source_integrity_check(),
        source_credential_check(),
        known_dependency_mitigation_check(),
        dependency_audit_check(),
    ]
    if not args.skip_build:
        checks.extend(
            [
                command_check(
                    "Java tests",
                    [
                        "mvn",
                        "-pl",
                        "linsight-module-ai-video/linsight-module-ai-video-server",
                        "-am",
                        "test",
                    ],
                    ROOT / "backend",
                    env,
                ),
                command_check(
                    "Runtime lint and tests",
                    [str(ROOT / "runtime/.venv/bin/ruff"), "check", "runtime"],
                    ROOT,
                    env,
                ),
                command_check(
                    "Runtime tests",
                    [str(ROOT / "runtime/.venv/bin/pytest"), "-q", "runtime/tests"],
                    ROOT,
                    env,
                ),
                command_check(
                    "Frontend typecheck",
                    ["corepack", "pnpm@11.7.0", "-F", "@linsight/console", "typecheck"],
                    ROOT / "frontend",
                    env,
                ),
                command_check(
                    "Frontend production build",
                    ["corepack", "pnpm@11.7.0", "-F", "@linsight/console", "build"],
                    ROOT / "frontend",
                    env,
                ),
            ]
        )
    checks.append(local_load_smoke(args.health_url))
    checks.append(external_acceptance_check(args.evidence))

    overall = "PASS"
    if any(check.status == "FAIL" for check in checks):
        overall = "FAIL"
    elif any(check.status == "BLOCKED_EXTERNAL" for check in checks):
        overall = "BLOCKED_EXTERNAL"
    report = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "overall": overall,
        "checks": [asdict(check) for check in checks],
    }
    output = ROOT / "artifacts/release-readiness"
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
