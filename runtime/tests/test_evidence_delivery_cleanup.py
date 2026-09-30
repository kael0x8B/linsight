import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ai_runtime.app.event.store import OfflineEventStore, PendingEvent
from edge_agent.app.main import _deliver_event


def queued(root: Path, finalized: bool = True) -> PendingEvent:
    directory = root / "event-1"
    directory.mkdir(exist_ok=True)
    (directory / "snapshot.jpg").write_bytes(b"snapshot")
    (directory / "evidence.mp4").write_bytes(b"video")
    return PendingEvent.model_validate(
        {
            "sourceEventId": "event-1",
            "payload": {},
            "finalized": finalized,
            "snapshotPath": directory / "snapshot.jpg",
            "videoPath": directory / "evidence.mp4",
        }
    )


def test_ack_removes_only_finalized_uploaded_media(tmp_path: Path) -> None:
    store = OfflineEventStore(tmp_path / "delivery.sqlite3")
    event = queued(tmp_path, False)
    store.upsert_event(event)
    with pytest.raises(ValueError, match="not finalized"):
        store.acknowledge_event(event.source_event_id)
    assert event.snapshot_path.exists() and event.video_path.exists()
    assert len(store.list_events()) == 1
    store.finalize_event(event.source_event_id, event.video_path, None)
    store.acknowledge_event(event.source_event_id)
    store.acknowledge_event(event.source_event_id)  # Replayed ACK is safe.
    assert not event.snapshot_path.parent.exists()
    assert store.list_events() == []
    assert (tmp_path / "delivery.sqlite3").exists()
    store.close()


def test_cleanup_survives_failed_unlink_and_restart(tmp_path: Path) -> None:
    database = tmp_path / "delivery.sqlite3"
    store = OfflineEventStore(database)
    event = queued(tmp_path)
    store.upsert_event(event)
    with patch.object(Path, "unlink", side_effect=PermissionError):
        store.acknowledge_event(event.source_event_id)
    assert event.snapshot_path.exists()
    assert (
        store._connection.execute("SELECT COUNT(*) FROM delivered_media_cleanup").fetchone()[0] == 2
    )
    store.close()
    reopened = OfflineEventStore(database)
    assert not event.snapshot_path.parent.exists()
    assert (
        reopened._connection.execute("SELECT COUNT(*) FROM delivered_media_cleanup").fetchone()[0]
        == 0
    )
    reopened.close()


def test_cleanup_preserves_unacknowledged_and_unrelated_files(tmp_path: Path) -> None:
    store = OfflineEventStore(tmp_path / "delivery.sqlite3")
    event = queued(tmp_path)
    unrelated = event.snapshot_path.parent / "operator-note.txt"
    unrelated.write_text("keep")
    store.upsert_event(event)
    store.cleanup_delivered_media()
    assert event.snapshot_path.exists()
    store.acknowledge_event(event.source_event_id)
    assert unrelated.read_text() == "keep"
    store.close()


def test_cleanup_rejects_external_or_symlink_paths(tmp_path: Path) -> None:
    root = tmp_path / "events"
    store = OfflineEventStore(root / "delivery.sqlite3")
    external = tmp_path / "snapshot.jpg"
    external.write_bytes(b"keep")
    directory = root / "event-1"
    directory.mkdir()
    link = directory / "snapshot.jpg"
    link.symlink_to(external)
    for value in (external, link):
        store.upsert_event(
            PendingEvent.model_validate(
                {
                    "sourceEventId": "event-1",
                    "payload": {},
                    "finalized": True,
                    "snapshotPath": value,
                }
            )
        )
        store.acknowledge_event("event-1")
    assert external.read_bytes() == b"keep"
    assert link.is_symlink()
    store.close()


@pytest.mark.parametrize("failure", ["upload", "empty_snapshot", "empty_video"])
def test_failed_media_delivery_never_acknowledges(tmp_path: Path, failure: str) -> None:
    from types import SimpleNamespace

    event = queued(tmp_path)
    if failure == "empty_snapshot":
        event.snapshot_path.write_bytes(b"")
    if failure == "empty_video":
        event.video_path.write_bytes(b"")
    client = AsyncMock()
    client.ingest_event.return_value = 1
    if failure == "upload":
        client.upload_event_media.side_effect = RuntimeError("upload unavailable")
    runtime = AsyncMock()
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(
            _deliver_event(
                SimpleNamespace(runtime_data_root=tmp_path),
                object(),
                client,
                runtime,
                event.model_dump(mode="json", by_alias=True),
            )
        )
    runtime.acknowledge_event.assert_not_called()
    assert event.snapshot_path.exists() and event.video_path.exists()


def test_successful_media_delivery_acknowledges_after_both_uploads(tmp_path: Path) -> None:
    from types import SimpleNamespace

    event = queued(tmp_path)
    client, runtime = AsyncMock(), AsyncMock()
    client.ingest_event.return_value = 1

    async def acknowledge(source: str) -> None:
        assert source == event.source_event_id
        assert client.upload_event_media.await_count == 2

    runtime.acknowledge_event.side_effect = acknowledge
    asyncio.run(
        _deliver_event(
            SimpleNamespace(runtime_data_root=tmp_path),
            object(),
            client,
            runtime,
            event.model_dump(mode="json", by_alias=True),
        )
    )
    runtime.acknowledge_event.assert_awaited_once()
