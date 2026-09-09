import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from edge_agent.app.upgrade.activation import begin, finish
from edge_agent.app.upgrade.manager import (
    ReleaseManifest,
    UpgradeManager,
    sign_release,
)

SIGNING_KEY = b"test-only-signing-key-that-is-at-least-32-bytes"


def test_verified_install_and_rollback(tmp_path: Path) -> None:
    manager = UpgradeManager(tmp_path / "agent", SIGNING_KEY)
    for version in ("1.0.0", "1.1.0"):
        package = tmp_path / f"edge-agent-{version}.tar.gz"
        _write_package(package, version)
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        manager.install(
            package,
            ReleaseManifest(version, digest, sign_release(version, digest, SIGNING_KEY)),
        )
        finish(tmp_path / "agent", begin(tmp_path / "agent"))

    assert manager.current_version() == "1.1.0"
    assert manager.rollback().name == "1.0.0"
    assert manager.current_version() == "1.0.0"


def test_install_rejects_bad_signature_and_path_traversal(tmp_path: Path) -> None:
    manager = UpgradeManager(tmp_path / "agent", SIGNING_KEY)
    package = tmp_path / "bad.tar.gz"
    _write_package(package, "1.0.0")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="signature"):
        manager.install(package, ReleaseManifest("1.0.0", digest, "0" * 64))

    traversal = tmp_path / "traversal.tar.gz"
    with tarfile.open(traversal, "w:gz") as archive:
        value = b"unsafe"
        info = tarfile.TarInfo("../outside")
        info.size = len(value)
        archive.addfile(info, io.BytesIO(value))
    digest = hashlib.sha256(traversal.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        manager.install(
            traversal,
            ReleaseManifest("1.0.1", digest, sign_release("1.0.1", digest, SIGNING_KEY)),
        )


def _write_package(path: Path, version: str) -> None:
    with tarfile.open(path, "w:gz") as archive:
        payload = f"#!/bin/sh\necho {version}\n".encode()
        info = tarfile.TarInfo("bin/edge-agent")
        info.mode = 0o755
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
