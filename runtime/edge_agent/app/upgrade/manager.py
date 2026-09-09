import hashlib
import hmac
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from edge_agent.app.upgrade.activation import read_pending, stage


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    sha256: str
    signature: str


class UpgradeManager:
    """Install immutable releases and atomically switch current/previous pointers."""

    def __init__(self, root: Path, signing_key: bytes) -> None:
        self._root = root.resolve()
        self._releases = self._root / "releases"
        self._signing_key = signing_key
        self._releases.mkdir(parents=True, exist_ok=True)

    def install(self, package: Path, manifest: ReleaseManifest) -> Path:
        if len(self._signing_key) < 32:
            raise ValueError("upgrade signing key must contain at least 32 bytes")
        self._validate_version(manifest.version)
        digest = _sha256(package)
        if not hmac.compare_digest(digest, manifest.sha256):
            raise ValueError("upgrade package SHA256 mismatch")
        signed_value = f"{manifest.version}:{manifest.sha256}".encode()
        expected = hmac.new(self._signing_key, signed_value, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, manifest.signature):
            raise ValueError("upgrade package signature mismatch")

        destination = self._releases / manifest.version
        if destination.exists():
            recorded = destination / ".package-sha256"
            if not recorded.is_file() or recorded.read_text().strip() != digest:
                raise ValueError("release version already exists with different content")
            self.activate(manifest.version)
            return destination
        staging = Path(tempfile.mkdtemp(prefix=f".{manifest.version}-", dir=self._releases))
        try:
            self._extract_safe(package, staging)
            executable = staging / "bin" / "edge-agent"
            if not executable.is_file():
                raise ValueError("upgrade package is missing bin/edge-agent")
            executable.chmod(executable.stat().st_mode | 0o500)
            (staging / ".package-sha256").write_text(digest)
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self.activate(manifest.version)
        return destination

    def activate(self, version: str) -> None:
        self._validate_version(version)
        destination = self._releases / version
        if not destination.is_dir():
            raise ValueError("release version is not installed")
        current = self._root / "current"
        previous = self._root / "previous"
        old_target = _link_target(current)
        pending = read_pending(self._root)
        if pending is not None and pending["version"] != version:
            raise ValueError("an Agent release is still awaiting activation")
        if old_target == destination:
            return  # An interrupted command may be retried after its atomic pointer switch.
        if pending is None:
            stage(self._root, version, old_target)
        if old_target is not None and old_target != destination:
            self._replace_link(previous, old_target)
        self._replace_link(current, destination)

    def rollback(self) -> Path:
        previous = _link_target(self._root / "previous")
        current = _link_target(self._root / "current")
        if previous is None or not previous.is_dir():
            raise ValueError("no verified previous release is available")
        previous.resolve().relative_to(self._releases)
        stage(self._root, previous.name, current)
        self._replace_link(self._root / "current", previous)
        if current is not None and current.is_dir():
            self._replace_link(self._root / "previous", current)
        return previous

    def current_version(self) -> str | None:
        current = _link_target(self._root / "current")
        return None if current is None else current.name

    def _replace_link(self, link: Path, target: Path) -> None:
        target.resolve().relative_to(self._releases)
        temporary = self._root / f".{link.name}.next"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, link)

    @staticmethod
    def _validate_version(version: str) -> None:
        if (
            not version
            or version in {".", ".."}
            or len(version) > 64
            or any(
                character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                for character in version
            )
        ):
            raise ValueError("release version is invalid")

    @staticmethod
    def _extract_safe(package: Path, staging: Path) -> None:
        with tarfile.open(package, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > 10000 or sum(member.size for member in members) > 512 * 1024 * 1024:
                raise ValueError("upgrade package exceeds extraction limits")
            for member in members:
                if member.issym() or member.islnk() or member.isdev():
                    raise ValueError("upgrade package contains an unsafe link or device")
                target = (staging / member.name).resolve()
                target.relative_to(staging.resolve())
            archive.extractall(staging, filter="data")  # noqa: S202 - members validated above


def sign_release(version: str, sha256: str, signing_key: bytes) -> str:
    return hmac.new(signing_key, f"{version}:{sha256}".encode(), hashlib.sha256).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _link_target(link: Path) -> Path | None:
    if not link.is_symlink():
        return None
    return link.resolve()
