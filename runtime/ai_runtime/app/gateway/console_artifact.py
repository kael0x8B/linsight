"""Build, verify, and install the immutable gateway console artifact."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1.0"
MAX_FILES = 10_000
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024
IGNORED_SOURCE_PARTS = {
    ".git",
    ".turbo",
    "__pycache__",
    "dist",
    "node_modules",
}
IGNORED_SOURCE_NAMES = {"dist.zip"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint(root: Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.name not in IGNORED_SOURCE_NAMES
            and not any(part in IGNORED_SOURCE_PARTS for part in path.relative_to(root).parts)
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
        digest.update(b"\0")
    return digest.hexdigest()


def _dist_files(dist: Path) -> list[Path]:
    dist = dist.resolve()
    if not (dist / "gateway.html").is_file():
        raise ValueError("gateway.html is missing from the frontend build")
    files = sorted(
        (path for path in dist.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(dist).as_posix(),
    )
    if len(files) > MAX_FILES:
        raise ValueError("gateway console contains too many files")
    if sum(path.stat().st_size for path in files) > MAX_EXTRACTED_BYTES:
        raise ValueError("gateway console exceeds the extracted size limit")
    return files


def _write_deterministic_archive(dist: Path, files: list[Path], output: Path) -> None:
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for path in files:
                    relative = path.relative_to(dist).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    info.mode = 0o644
                    with path.open("rb") as source:
                        archive.addfile(info, source)


def build_artifact(dist: Path, bundle_dir: Path, source_root: Path) -> dict[str, Any]:
    dist = dist.resolve()
    bundle_dir = bundle_dir.resolve()
    files = _dist_files(dist)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    temporary_archive = bundle_dir / ".gateway-console.tar.gz"
    _write_deterministic_archive(dist, files, temporary_archive)
    digest = file_sha256(temporary_archive)
    artifact_name = f"gateway-console-{digest[:12]}.tar.gz"
    artifact = bundle_dir / artifact_name
    os.replace(temporary_archive, artifact)
    for stale in bundle_dir.glob("gateway-console-*.tar.gz"):
        if stale != artifact:
            stale.unlink()
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactType": "linsightGatewayConsole",
        "version": digest[:12],
        "sourceSha256": source_fingerprint(source_root),
        "artifact": {
            "fileName": artifact_name,
            "sha256": digest,
            "sizeBytes": artifact.stat().st_size,
        },
        "entrypoints": ["gateway.html", "index.html"],
        "files": [
            {
                "path": path.relative_to(dist).as_posix(),
                "sha256": file_sha256(path),
                "sizeBytes": path.stat().st_size,
            }
            for path in files
        ],
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    install_artifact(bundle_dir, bundle_dir / "current")
    return manifest


def _load_manifest(bundle_dir: Path) -> tuple[dict[str, Any], Path]:
    manifest_path = bundle_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid gateway console manifest: {error}") from error
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("unsupported gateway console manifest schema")
    if manifest.get("artifactType") != "linsightGatewayConsole":
        raise ValueError("unsupported gateway console artifact type")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("gateway console manifest is missing artifact metadata")
    file_name = artifact.get("fileName")
    if not isinstance(file_name, str) or Path(file_name).name != file_name:
        raise ValueError("gateway console artifact filename is invalid")
    archive = bundle_dir / file_name
    if not archive.is_file():
        raise ValueError("gateway console artifact is missing")
    expected_size = artifact.get("sizeBytes")
    if not isinstance(expected_size, int) or archive.stat().st_size != expected_size:
        raise ValueError("gateway console artifact size mismatch")
    expected_sha256 = artifact.get("sha256")
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or artifact.get("fileName") != f"gateway-console-{expected_sha256[:12]}.tar.gz"
        or file_sha256(archive) != expected_sha256
    ):
        raise ValueError("gateway console artifact SHA256 mismatch")
    return manifest, archive


def _validated_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    if len(members) > MAX_FILES:
        raise ValueError("gateway console artifact contains too many files")
    if sum(member.size for member in members) > MAX_EXTRACTED_BYTES:
        raise ValueError("gateway console artifact exceeds the extracted size limit")
    member_names: set[str] = set()
    for member in members:
        relative = PurePosixPath(member.name)
        if (
            member.name.startswith("/")
            or ".." in relative.parts
            or member.name in member_names
            or member.issym()
            or member.islnk()
            or member.isdev()
            or not member.isfile()
        ):
            raise ValueError("gateway console artifact contains an unsafe entry")
        member_names.add(member.name)
    return members


def install_artifact(bundle_dir: Path, target: Path) -> dict[str, Any]:
    bundle_dir = bundle_dir.resolve()
    target = target.resolve()
    manifest, archive_path = _load_manifest(bundle_dir)
    expected_files = manifest.get("files")
    if not isinstance(expected_files, list):
        raise ValueError("gateway console manifest is missing its file inventory")
    declared: dict[str, dict[str, Any]] = {}
    for entry in expected_files:
        if not isinstance(entry, dict):
            raise ValueError("gateway console manifest contains invalid file metadata")
        path = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("sizeBytes")
        if (
            not isinstance(path, str)
            or path.startswith("/")
            or ".." in PurePosixPath(path).parts
            or path in declared
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(size, int)
            or size < 0
        ):
            raise ValueError("gateway console manifest contains invalid file metadata")
        declared[path] = entry
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".gateway-console-", dir=target.parent))
    backup = target.with_name(f".{target.name}.previous")
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = _validated_members(archive)
            archive.extractall(staging, members=members, filter="data")
        actual_paths = sorted(
            path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()
        )
        declared_paths = sorted(declared)
        if actual_paths != declared_paths:
            raise ValueError("gateway console file inventory mismatch")
        for relative in actual_paths:
            path = staging / relative
            entry = declared[relative]
            if path.stat().st_size != entry.get("sizeBytes"):
                raise ValueError(f"gateway console file size mismatch: {relative}")
            if file_sha256(path) != entry.get("sha256"):
                raise ValueError(f"gateway console file SHA256 mismatch: {relative}")
        entrypoints = manifest.get("entrypoints")
        if not isinstance(entrypoints, list) or not entrypoints:
            raise ValueError("gateway console manifest is missing its entrypoints")
        for entrypoint in entrypoints:
            if not isinstance(entrypoint, str) or entrypoint not in declared:
                raise ValueError("gateway console manifest contains an invalid entrypoint")
            if not (staging / entrypoint).is_file():
                raise ValueError(f"gateway console entrypoint is missing: {entrypoint}")
        shutil.rmtree(backup, ignore_errors=True)
        if target.exists():
            os.replace(target, backup)
        os.replace(staging, target)
        shutil.rmtree(backup, ignore_errors=True)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--dist", type=Path, required=True)
    build.add_argument("--bundle-dir", type=Path, required=True)
    build.add_argument("--source-root", type=Path, required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--bundle-dir", type=Path, required=True)
    install.add_argument("--target", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "build":
        manifest = build_artifact(args.dist, args.bundle_dir, args.source_root)
    else:
        manifest = install_artifact(args.bundle_dir, args.target)
    print(
        json.dumps(
            {
                "version": manifest["version"],
                "sha256": manifest["artifact"]["sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
