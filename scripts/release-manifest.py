#!/usr/bin/env python3
"""Create an immutable, hash-bound LInsight production version manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts/production-readiness/release-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def image_digest(image: str) -> str | None:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", image],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and "@sha256:" in value else None


def gateway_console() -> tuple[dict[str, Any], list[str]]:
    manifest_path = ROOT / "runtime/gateway-console/manifest.json"
    blockers: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("schemaVersion") != "1.0"
            or manifest.get("artifactType") != "linsightGatewayConsole"
        ):
            raise ValueError("unsupported gateway console manifest")
        artifact_meta = manifest["artifact"]
        file_name = artifact_meta["fileName"]
        expected_sha256 = artifact_meta["sha256"]
        expected_size = artifact_meta["sizeBytes"]
        if (
            not isinstance(file_name, str)
            or Path(file_name).name != file_name
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or file_name != f"gateway-console-{expected_sha256[:12]}.tar.gz"
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise ValueError("invalid gateway console artifact metadata")
        artifact = manifest_path.parent / file_name
        if not artifact.is_file():
            blockers.append("GATEWAY_CONSOLE_ARTIFACT_MISSING")
            actual_sha256 = "MISSING"
        else:
            actual_sha256 = sha256(artifact)
            if artifact.stat().st_size != expected_size:
                blockers.append("GATEWAY_CONSOLE_SIZE_MISMATCH")
            if actual_sha256 != expected_sha256:
                blockers.append("GATEWAY_CONSOLE_SHA256_MISMATCH")
        return (
            {
                "manifest": str(manifest_path.relative_to(ROOT)),
                "version": manifest.get("version", "UNKNOWN"),
                "sourceSha256": manifest.get("sourceSha256", "UNKNOWN"),
                "artifact": str(artifact.relative_to(ROOT)),
                "sha256": actual_sha256,
            },
            blockers,
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError):
        return (
            {
                "manifest": str(manifest_path.relative_to(ROOT)),
                "artifact": "MISSING",
                "sha256": "MISSING",
            },
            ["GATEWAY_CONSOLE_MANIFEST_INVALID"],
        )


def build(version: str, images: list[str]) -> dict[str, Any]:
    commit = git_commit()
    console, console_blockers = gateway_console()
    java_jars = sorted((ROOT / "backend").glob("*/target/*.jar"))
    python_files = [
        path
        for base in (ROOT / "runtime/ai_runtime", ROOT / "runtime/edge_agent")
        for path in base.rglob("*.py")
    ] + [ROOT / "runtime/pyproject.toml", ROOT / "runtime/uv.lock"]
    model_dir = ROOT / "var/model-assets/v1"
    asset_lock_path = model_dir / "assets-lock.json"
    asset_lock = (
        json.loads(asset_lock_path.read_text(encoding="utf-8"))
        if asset_lock_path.is_file()
        else {"assets": []}
    )
    locked_models = [
        {
            "key": entry["key"],
            "path": model_dir / entry["fileName"],
            "expectedSha256": entry["sha256"],
        }
        for entry in asset_lock.get("assets", [])
    ]
    missing_models = [entry for entry in locked_models if not entry["path"].is_file()]
    mismatched_models = [
        entry
        for entry in locked_models
        if entry["path"].is_file() and sha256(entry["path"]) != entry["expectedSha256"]
    ]
    config_files = sorted(
        [
            path
            for base in (ROOT / "deploy", ROOT / "backend/linsight-server/src/main/resources")
            for path in base.rglob("*")
            if path.is_file() and path.suffix in {".yaml", ".yml", ".json"}
        ]
    )
    image_entries = [{"image": image, "digest": image_digest(image) or "MISSING"} for image in images]
    blockers = list(console_blockers)
    if not commit:
        blockers.append("GIT_COMMIT_MISSING")
    if not image_entries or any(value["digest"] == "MISSING" for value in image_entries):
        blockers.append("DOCKER_IMAGE_DIGEST_MISSING")
    if not java_jars:
        blockers.append("JAVA_ARTIFACT_MISSING")
    if not locked_models or missing_models:
        blockers.append("MODEL_ARTIFACTS_MISSING")
    if mismatched_models:
        blockers.append("MODEL_SHA256_MISMATCH")
    return {
        "schemaVersion": "1.0",
        "version": version,
        "gitCommit": commit or "MISSING",
        "dockerImages": image_entries,
        "javaArtifacts": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for path in java_jars
        ],
        "pythonSha256": tree_hash(python_files),
        "gatewayConsole": console,
        "models": [
            {
                "key": entry["key"],
                "path": str(entry["path"].relative_to(ROOT)),
                "sha256": sha256(entry["path"]),
                "sizeBytes": entry["path"].stat().st_size,
            }
            for entry in locked_models
            if entry["path"].is_file()
        ],
        "configurationVersion": tree_hash(config_files),
        "buildTime": datetime.now(UTC).isoformat(),
        "status": "PASS" if not blockers else "WAITING_FOR_IMMUTABLE_RELEASE",
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build(args.version, args.image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
