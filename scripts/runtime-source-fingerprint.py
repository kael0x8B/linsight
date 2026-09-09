#!/usr/bin/env python3
"""Create a deterministic fingerprint for the Runtime source deployed by the platform."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOTS = ("ai_runtime", "edge_agent")


def source_files(root: Path) -> list[Path]:
    root = root.resolve()
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        raise ValueError(f"Runtime root does not contain pyproject.toml: {root}")

    files = [pyproject]
    for package_root in PACKAGE_ROOTS:
        directory = root / package_root
        if not directory.is_dir():
            raise ValueError(f"Runtime package root is missing: {directory}")
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_bytes(root: Path, files: list[Path]) -> bytes:
    root = root.resolve()
    lines = [
        f"{file_sha256(path)}  {path.relative_to(root).as_posix()}\n"
        for path in files
    ]
    return "".join(lines).encode("utf-8")


def fingerprint(root: Path) -> dict[str, object]:
    root = root.resolve()
    files = source_files(root)
    digest = hashlib.sha256(manifest_bytes(root, files)).hexdigest()
    return {
        "schemaVersion": "1.0",
        "artifactType": "runtimeSourceFingerprint",
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "fingerprint": {
            "algorithm": "SHA-256 over sorted '<file-sha256>  <relative-path>\\n' records",
            "sha256": digest,
            "fileCount": len(files),
            "inputs": [
                "runtime/pyproject.toml",
                "runtime/ai_runtime/**/*",
                "runtime/edge_agent/**/*",
            ],
            "excluded": ["**/__pycache__/**", "**/*.pyc"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "runtime",
        help="Runtime source root; defaults to <project>/runtime",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(fingerprint(args.root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
