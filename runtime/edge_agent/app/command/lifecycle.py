import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path


class NodeLifecycleController:
    """Publish fixed host actions atomically and prevent replay after an Agent restart."""

    def __init__(self, request_path: Path, journal_root: Path | None = None) -> None:
        self._request_path = request_path
        self._journal_root = journal_root or request_path.parent / "lifecycle-journal"

    async def schedule(self, action: str, command_id: str) -> dict[str, object]:
        if action not in {"restart", "shutdown"} or not command_id:
            raise ValueError("unsupported node lifecycle action or missing command ID")
        return await asyncio.to_thread(self._write_request, action, command_id)

    def _write_request(self, action: str, command_id: str) -> dict[str, object]:
        # Persist intent before signalling systemd. An interrupted submission is never
        # blindly replayed: a duplicate may otherwise reboot an already recovered host.
        self._journal_root.mkdir(parents=True, exist_ok=True)
        marker = self._journal_root / hashlib.sha256(command_id.encode()).hexdigest()
        result = {"accepted": True, "action": action, "executionConfirmed": False}
        try:
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            previous = json.loads(marker.read_text())
            if previous["action"] != action:
                raise ValueError("command ID already used for another lifecycle action") from None
            return {**result, "duplicate": True}
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"action": action}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(self._journal_root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        temporary = None
        try:
            # The watcher only sees a complete request, never an empty/truncated file.
            descriptor, name = tempfile.mkstemp(
                prefix=".node-power-", dir=self._request_path.parent
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(f"{action}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._request_path)
        except OSError:
            marker.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return result
