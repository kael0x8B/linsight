"""Bounded durable transfer of active entrance evidence to existing event media storage."""

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from uuid import UUID

LOGGER = logging.getLogger("linsight.edge_agent")


def save_pending(root: Path, command_id: str, evidence: dict):
    directory = root / "entry-evidence-outbox"
    directory.mkdir(parents=True, exist_ok=True)
    command_id = str(UUID(command_id))
    allowed = (root / "entry-evidence" / command_id).resolve()
    members = []
    for key, filename in evidence.items():
        path = Path(filename).resolve()
        if not path.is_relative_to(allowed) or not path.is_file():
            raise ValueError("invalid entrance evidence path")
        members.append(
            {
                "path": str(path),
                "type": "SNAPSHOT" if key == "snapshotPath" else "VIDEO",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    target = directory / (command_id + ".json")
    temporary = target.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump({"commandId": command_id, "members": members}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(target)


async def deliver_pending(root, identity, client, path):
    record = json.loads(path.read_text())
    state = await client.get_entry_command(identity, record["commandId"], state=True)
    if state.get("status") not in {"SUCCEEDED", "CANCELLED", "FAILED"}:
        return
    for member in record["members"]:
        media = await asyncio.to_thread(Path(member["path"]).resolve)
        allowed = (root / "entry-evidence" / str(UUID(record["commandId"]))).resolve()
        if not media.is_relative_to(allowed):
            raise ValueError("invalid pending evidence path")
        if not media.exists():
            continue
        if state.get("eventId") is not None:
            if hashlib.sha256(media.read_bytes()).hexdigest() != member["sha256"]:
                raise ValueError("pending evidence SHA256 mismatch")
            await client.upload_event_media(
                identity,
                int(state["eventId"]),
                member["type"],
                media,
                "image/jpeg" if member["type"] == "SNAPSHOT" else "video/mp4",
            )
        media.unlink()
    path.unlink()


async def entry_evidence_loop(settings, identity, client):
    retry = {}
    while True:
        for path in sorted((settings.runtime_data_root / "entry-evidence-outbox").glob("*.json"))[
            :256
        ]:
            if retry.get(path, 0) > time.monotonic():
                continue
            try:
                await deliver_pending(settings.runtime_data_root, identity, client, path)
                retry.pop(path, None)
            except Exception as error:
                LOGGER.warning(
                    "Entrance evidence pending nodeId=%s errorType=%s",
                    identity.node_id,
                    type(error).__name__,
                )
                retry[path] = time.monotonic() + 60
        await asyncio.sleep(5)
