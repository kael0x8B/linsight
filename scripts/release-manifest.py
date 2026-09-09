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


def build(version: str, images: list[str]) -> dict[str, Any]:
    commit = git_commit()
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
    model_files = [entry["path"] for entry in locked_models if entry["path"].is_file()]
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
    blockers = []
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
