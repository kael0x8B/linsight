#!/usr/bin/env python3
"""Verify the hash-bound, credential-free partial field preflight bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
USERINFO_URL = re.compile(r"(?i)(?:rtsp|https?)://[^/\s:@]+:[^@\s/]+@")
SECRET_VALUE = re.compile(
    r'(?i)"(?:password|accessToken|authorization|nodeCredential|runtimeApiKey)"\s*:\s*"[^"*][^"]*"'
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(index_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        document: Any = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"cannot read index: {error}"]
    if not isinstance(document, dict):
        return ["index must be a JSON object"]
    if document.get("schemaVersion") != "1.0":
        errors.append("schemaVersion must be 1.0")
    if document.get("status") not in {"PARTIAL_GATEWAY_OFFLINE", "COMPLETE"}:
        errors.append("status is invalid")
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return errors + ["artifacts must be a non-empty array"]

    root = index_path.parent.resolve()
    paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        field = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{field} must be an object")
            continue
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            errors.append(f"{field}.path must be relative")
            continue
        if relative in paths:
            errors.append(f"{field}.path is duplicated")
            continue
        paths.add(relative)
        try:
            target = (root / relative).resolve(strict=True)
            target.relative_to(root)
        except (OSError, ValueError):
            errors.append(f"{field}.path is missing or escapes the bundle")
            continue
        if not target.is_file() or target.stat().st_size == 0:
            errors.append(f"{field}.path must reference a non-empty regular file")
            continue
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            errors.append(f"{field}.sha256 is invalid")
        elif sha256(target) != expected:
            errors.append(f"{field}.sha256 does not match")
        if target.suffix.lower() in {".json", ".log", ".txt"}:
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"{field} text artifact is not UTF-8")
                continue
            if USERINFO_URL.search(text) or SECRET_VALUE.search(text) or PRIVATE_KEY.search(text):
                errors.append(f"{field} contains credential-like material")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    args = parser.parse_args()
    errors = validate(args.index)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("field preflight evidence is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
