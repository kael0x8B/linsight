import asyncio
import hashlib
import hmac
import json
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.event.store import OfflineEventStore, PendingEvent
from ai_runtime.app.gateway.console import create_app
from ai_runtime.app.gateway.event_stream import GatewayEventStream
from ai_runtime.app.gateway.store import GatewayStore


def make_event(root, event_type="AREA_INTRUSION", task_id=7):
    source_id = str(uuid4())
    path = root / "events" / source_id / "snapshot.jpg"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 48), "blue").save(path)
    plate_event = event_type == "VEHICLE_PLATE_RECOGNIZED"
    return PendingEvent.model_validate(
        {
            "sourceEventId": source_id,
            "snapshotPath": str(path),
            "finalized": True,
            "payload": {
                "sourceEventId": source_id,
                "taskId": task_id,
                "cameraId": 12,
                "algorithmId": 30,
                "modelVersionId": 40,
                "ruleId": 50,
                "trackId": "person-1",
                "durationMs": 1500,
                "eventType": event_type,
                "occurredTime": 1_790_200_000_000,
                "objectSnapshot": {
                    "class": "license_plate" if plate_event else "person",
                    "attributes": (
                        {"plateNumber": "京A12345", "plateText": "京A12345"}
                        if plate_event else {}
                    ),
                },
                "taskSnapshot": {
                    "displayNames": {
                        "task": "入口",
                        "algorithm": "车牌识别" if plate_event else "区域入侵",
                        "camera": "东侧机位",
                    }
                },
            },
        }
    )


async def frame(reader):
    return json.loads(await asyncio.wait_for(reader.readline(), 4))


async def connect(port, key, task_ids=None, event_types=None):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    challenge = await frame(reader)
    assert challenge["type"] == "challenge"
    assert challenge["version"] == "3.0"
    digest = hmac.new(key.encode(), challenge["nonce"].encode(), hashlib.sha256).hexdigest()
    writer.write((json.dumps({"type": "auth", "hmac": digest}) + "\n").encode())
    await writer.drain()
    assert (await frame(reader))["type"] == "authenticated"
    writer.write(
        (
            json.dumps(
                {"type": "subscribe", "taskIds": task_ids or [], "eventTypes": event_types or []}
            )
            + "\n"
        ).encode()
    )
    await writer.drain()
    assert (await frame(reader)) == {"type": "subscribed"}
    return reader, writer


async def next_event(reader):
    while True:
        value = await frame(reader)
        if value["type"] != "heartbeat":
            return value


def test_tcp_subscription_live_only_and_signed_image(tmp_path):
    asyncio.run(_subscription_live_only_and_signed_image(tmp_path))


def test_v2_internal_cursor_column_migrates_without_replay(tmp_path):
    database = tmp_path / "events/delivery.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TABLE gateway_tcp_event (cursor INTEGER PRIMARY KEY AUTOINCREMENT, "
            "source_event_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, "
            "snapshot_path TEXT NOT NULL, created_at INTEGER NOT NULL)"
        )
        db.execute(
            "INSERT INTO gateway_tcp_event(source_event_id,payload,snapshot_path,created_at) "
            "VALUES (?,?,?,?)",
            (str(uuid4()), "{}", "unused", 1),
        )
    events = OfflineEventStore(database, retain_history=True)
    secrets = GatewayStore(tmp_path / "gateway")
    try:
        stream = GatewayEventStream(events, secrets, tmp_path / "events", "127.0.0.1", 0)
        assert stream._latest_sequence() == 1
        with events.transaction() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(gateway_tcp_event)")}
        assert "sequence" in columns and "cursor" not in columns
    finally:
        events.close()
        secrets.close()


async def _subscription_live_only_and_signed_image(tmp_path):
    events = OfflineEventStore(tmp_path / "events/delivery.sqlite3", retain_history=True)
    secrets = GatewayStore(tmp_path / "gateway")
    stream = GatewayEventStream(events, secrets, tmp_path / "events", "127.0.0.1", 0)
    stream.server = await asyncio.start_server(stream._client, "127.0.0.1", 0)
    port = stream.server.sockets[0].getsockname()[1]
    with pytest.raises(ValueError, match="subscriber key"):
        stream.configure(True, False, 0)
    key = stream.configure(True, True, 0)["key"]
    try:
        old = make_event(tmp_path)
        events.upsert_event(old)
        reader, writer = await connect(port, key, task_ids=[7], event_types=["AREA_INTRUSION"])
        assert (await frame(reader)) == {"type": "heartbeat"}
        # 空闲时不能再按旧的 0.5 秒间隔发送心跳；随后事件仍要及时到达。
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(reader.readline(), 0.8)
        skipped = make_event(tmp_path, "VEHICLE_PLATE_RECOGNIZED", 9)
        accepted = make_event(tmp_path)
        events.upsert_event(skipped)
        events.upsert_event(accepted)
        event = await next_event(reader)
        assert event["sourceEventId"] == accepted.source_event_id
        assert event["version"] == "3.0"
        assert "cursor" not in event
        assert event["data"]["cameraName"] == "东侧机位"
        assert event["data"]["algorithmName"] == "区域入侵"
        assert event["data"]["result"]["class"] == "person"
        assert event["data"]["result"]["attributes"] == {}
        snapshot = event["data"]["snapshot"]
        assert "base64" not in snapshot
        assert snapshot["url"].startswith("http://127.0.0.1:48901/event-images/")
        assert hashlib.sha256(accepted.snapshot_path.read_bytes()).hexdigest() == snapshot["sha256"]
        settings = RuntimeSettings(api_key="x" * 32, runtime_data_root=tmp_path)
        app = create_app(settings, event_stream=stream, static_root=tmp_path)
        url = urlsplit(snapshot["url"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            image = await client.get(url.path + "?" + url.query)
            assert image.status_code == 200
            assert image.content == accepted.snapshot_path.read_bytes()
            bad = await client.get(url.path + "?expires=1&signature=bad")
            assert bad.status_code == 404
        writer.close()
        await writer.wait_closed()
        reader, writer = await connect(port, key)
        assert (await frame(reader)) == {"type": "heartbeat"}
        writer.close()
        await writer.wait_closed()
        stream.configure(True, True, 1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get(url.path + "?" + url.query)).status_code == 404
    finally:
        await stream.close()
        events.close()
        secrets.close()


def test_bad_key_and_key_rotation_disconnect(tmp_path):
    asyncio.run(_bad_key_and_key_rotation_disconnect(tmp_path))


async def _bad_key_and_key_rotation_disconnect(tmp_path):
    events = OfflineEventStore(tmp_path / "events/delivery.sqlite3", retain_history=True)
    secrets = GatewayStore(tmp_path / "gateway")
    stream = GatewayEventStream(events, secrets, tmp_path / "events", "127.0.0.1", 0)
    stream.server = await asyncio.start_server(stream._client, "127.0.0.1", 0)
    port = stream.server.sockets[0].getsockname()[1]
    key = stream.configure(True, True, 0)["key"]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await frame(reader)
        writer.write(b'{"type":"auth","hmac":"wrong"}\n')
        await writer.drain()
        assert (await frame(reader))["code"] == "UNAUTHORIZED"
        writer.close()
        await writer.wait_closed()
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        challenge = await frame(reader)
        digest = hmac.new(key.encode(), challenge["nonce"].encode(), hashlib.sha256).hexdigest()
        writer.write((json.dumps({"type": "auth", "hmac": digest}) + "\n").encode())
        await writer.drain()
        assert (await frame(reader))["type"] == "authenticated"
        writer.write(b'{"type":"subscribe","cursor":0,"taskIds":[],"eventTypes":[]}\n')
        await writer.drain()
        assert (await frame(reader))["code"] == "BAD_REQUEST"
        writer.close()
        await writer.wait_closed()
        reader, writer = await connect(port, key)
        assert (await frame(reader)) == {"type": "heartbeat"}
        stream.configure(True, True, 1)
        assert (await frame(reader))["code"] == "CONFIG_CHANGED"
        writer.close()
        await writer.wait_closed()
    finally:
        await stream.close()
        events.close()
        secrets.close()
