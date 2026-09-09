"""Durable activation journal shared by the launcher and accepted-heartbeat loop."""
import json
import os
import time
import uuid
from pathlib import Path


def read_pending(root: Path) -> dict | None:
    path = root / "pending-activation.json"
    return json.loads(path.read_text()) if path.is_file() else None


def write_pending(root: Path, value: dict) -> None:
    temporary = root / ".pending-activation.tmp"
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, root / "pending-activation.json")


def stage(root: Path, version: str, previous: Path | None) -> None:
    if read_pending(root) is not None:
        raise ValueError("an Agent release is still awaiting activation")
    (root / "failed-activation-version").unlink(missing_ok=True)
    write_pending(root, {"version": version, "previous": str(previous) if previous else None,
                         "token": uuid.uuid4().hex, "startedAt": None})


def acknowledge(root: Path, version: str) -> None:
    pending = read_pending(root)
    if pending and pending["version"] == version and pending.get("startedAt") is not None:
        # Separate ack file: never overwrite a journal changed by a concurrent launcher.
        ack = root / ("healthy-" + pending["token"])
        with ack.open("w") as stream:
            os.chmod(ack, 0o600)
            stream.write(version)


def begin(root: Path) -> dict | None:
    pending = read_pending(root)
    if pending and pending.get("startedAt") is None:
        pending["startedAt"] = time.time()
        write_pending(root, pending)
    return pending


def healthy(root: Path, pending: dict) -> bool:
    ack = root / ("healthy-" + pending["token"])
    return ack.is_file() and ack.read_text() == pending["version"]


def finish(root: Path, pending: dict) -> None:
    current = read_pending(root)
    if current and current["token"] == pending["token"]:
        (root / "pending-activation.json").unlink(missing_ok=True)
        (root / ("healthy-" + pending["token"])).unlink(missing_ok=True)


def restore(root: Path, pending: dict) -> None:
    previous = pending.get("previous")
    current = root / "current"
    if previous:
        target = Path(previous).resolve(strict=True)
        target.relative_to((root / "releases").resolve())
        temporary = root / ".current.restore"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, current)
    else:
        # The first signed release falls back to the source baseline.
        current.unlink(missing_ok=True)
    (root / "failed-activation-version").write_text(pending["version"])
    finish(root, pending)


def failed_version(root: Path) -> str | None:
    try:
        value = (root / "failed-activation-version").read_text().strip()
        return value if 0 < len(value) <= 64 else None
    except OSError:
        return None
