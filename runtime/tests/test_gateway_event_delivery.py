import asyncio
import base64
import json
import socket
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from ai_runtime.app.event.store import OfflineEventStore, PendingEvent
from ai_runtime.app.gateway.event_delivery import (
    DeliveryConflict,
    GatewayEventDelivery,
    RouteChange,
    TargetChange,
    _resolve_target,
    _safe_address,
)
from ai_runtime.app.gateway.store import GatewayStore

PLATE_EVENT = "VEHICLE_PLATE_RECOGNIZED"


def setup(root):
    events = OfflineEventStore(root / "events/delivery.sqlite3", retain_history=True)
    secrets = GatewayStore(root / "gateway")
    delivery = GatewayEventDelivery(events, secrets, root / "events")
    return events, secrets, delivery


def target(delivery, **overrides):
    body = dict(
        id=str(uuid4()),
        expectedRevision=0,
        requestId=str(uuid4()),
        name="矿区接收",
        url="http://10.12.0.5:8080/events",
        network="INTERNAL",
        enabled=True,
        authValue="Bearer test-private-key",
        maxAttempts=2,
    )
    body.update(overrides)
    return delivery.save_target(TargetChange.model_validate(body))


def route(delivery, destination, task=1, event_types=None):
    return delivery.save_route(
        RouteChange.model_validate(
            {
                "taskId": task,
                "expectedRevision": 0,
                "requestId": str(uuid4()),
                "enabled": True,
                "targetIds": [destination["id"]],
                "eventTypes": event_types or [],
                "locationCode": "S01",
                "locationName": "一号料仓",
                "cameraName": "车头机位",
            }
        )
    )


def event(root, task=1, event_type=PLATE_EVENT, status="CONFIRMED"):
    identity = str(uuid4())
    path = root / "events" / identity / "snapshot.jpg"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (80, 50), "blue").save(path)
    return PendingEvent(
        sourceEventId=identity,
        snapshotPath=path,
        finalized=True,
        payload={
            "sourceEventId": identity,
            "taskId": task,
            "cameraId": 9,
            "eventType": event_type,
            "occurredTime": 1_789_900_000_000,
            "objectSnapshot": {
                "class": "license_plate",
                "attributes": {
                    "plateNumber": "皖A12345",
                    "plateConfidence": 0.95,
                    "ocrStatus": status,
                },
            },
            "taskSnapshot": {},
        },
    )


def due(events):
    with events.transaction() as db:
        db.execute("UPDATE gateway_event_delivery SET next_attempt=0")


def test_explicit_task_routing_is_shared_by_different_algorithms(tmp_path):
    events, secrets, delivery = setup(tmp_path)
    first, second = target(delivery), target(delivery)
    route(delivery, first)
    route(delivery, second, task=2)
    events.upsert_event(event(tmp_path, task=3))
    assert delivery.records()["total"] == 0
    recognized = event(tmp_path)
    events.upsert_event(recognized)
    events.upsert_event(recognized)
    assert delivery.records()["total"] == 1
    with events.transaction() as db:
        queued = db.execute("SELECT * FROM gateway_event_delivery").fetchone()
        assert queued["target_id"] == first["id"]
        assert b"test-private-key" not in queued["target_document"]
    stored = next(
        value
        for value in events.list_events()
        if value.source_event_id == recognized.source_event_id
    )
    assert stored.payload["taskSnapshot"]["location"]["locationCode"] == "S01"
    assert "test-private-key" not in json.dumps(delivery.targets())
    intrusion = event(tmp_path, task=2, event_type="AREA_INTRUSION")
    intrusion.payload["objectSnapshot"] = {
        "class": "person",
        "attributes": {"displayLabel": "区域入侵"},
    }
    events.upsert_event(intrusion)
    records = delivery.records()["list"]
    assert len(records) == 2
    assert {item["data"]["eventType"] for item in records} == {PLATE_EVENT, "AREA_INTRUSION"}
    assert (
        next(item for item in records if item["data"]["eventType"] == "AREA_INTRUSION")["data"][
            "result"
        ]["class"]
        == "person"
    )
    secrets.close()
    events.close()


def test_event_type_filter_never_becomes_a_global_subscription(tmp_path):
    events, secrets, delivery = setup(tmp_path)
    route(delivery, target(delivery), event_types=["HELMET_MISSING"])
    events.upsert_event(event(tmp_path))
    events.upsert_event(event(tmp_path, task=2, event_type="HELMET_MISSING"))
    assert delivery.records()["total"] == 0
    helmet = event(tmp_path, event_type="HELMET_MISSING")
    helmet.payload["objectSnapshot"] = {"class": "person", "attributes": {"helmet": "absent"}}
    events.upsert_event(helmet)
    assert delivery.records()["total"] == 1
    assert delivery.records()["list"][0]["data"]["result"]["attributes"] == {"helmet": "absent"}
    secrets.close()
    events.close()


def test_platform_ack_does_not_ack_box_or_remove_its_snapshot(tmp_path):
    events, secrets, delivery = setup(tmp_path)
    route(delivery, target(delivery))
    recognized = event(tmp_path)
    events.upsert_event(recognized)
    events.acknowledge_event(recognized.source_event_id)
    with events.transaction() as db:
        db.execute("UPDATE local_event_history SET stored_at=0")
    events.prune_history(1)
    assert recognized.snapshot_path.exists()
    assert events.history()["total"] == 1
    assert delivery.records()["list"][0]["status"] == "PENDING"

    async def send(_target, body, source_id):
        assert source_id == recognized.source_event_id
        assert body["deliverySource"] == "GATEWAY"
        assert body["data"]["location"]["locationName"] == "一号料仓"
        assert base64.b64decode(body["data"]["snapshot"]["base64"]).startswith(b"\xff\xd8")
        return 200

    delivery._send = send
    asyncio.run(delivery.deliver_once())
    assert delivery.records()["list"][0]["status"] == "SUCCEEDED"
    events.prune_history(1)
    assert not recognized.snapshot_path.exists()
    secrets.close()
    events.close()


def test_box_success_does_not_ack_platform_upload_and_local_tasks_still_send(tmp_path):
    events, secrets, delivery = setup(tmp_path)
    endpoint = target(delivery)
    route(delivery, endpoint)
    route(delivery, endpoint, task=2)
    events.local_task_ids.add(2)
    remote, local = event(tmp_path), event(tmp_path, task=2)
    events.upsert_event(remote)
    events.upsert_event(local)

    async def send(*_):
        return 204

    delivery._send = send
    asyncio.run(delivery.deliver_once())
    assert {row["status"] for row in delivery.records()["list"]} == {"SUCCEEDED"}
    assert [value.source_event_id for value in events.list_events()] == [remote.source_event_id]
    assert next(
        row for row in events.history()["list"] if row["sourceEventId"] == local.source_event_id
    )["localOnly"]
    secrets.close()
    events.close()


def test_restart_dead_letter_replay_and_immutable_destination(tmp_path):
    events, secrets, delivery = setup(tmp_path)
    endpoint = target(delivery)
    route(delivery, endpoint)
    recognized = event(tmp_path)
    events.upsert_event(recognized)

    async def unavailable(*_):
        return 503

    delivery._send = unavailable
    asyncio.run(delivery.deliver_once())
    identity = delivery.records()["list"][0]["id"]
    secrets.close()
    events.close()

    events, secrets, delivery = setup(tmp_path)
    changed = target(
        delivery,
        id=endpoint["id"],
        expectedRevision=1,
        url="http://10.12.0.8:8080/changed",
        enabled=False,
    )
    due(events)
    delivery._send = unavailable
    asyncio.run(delivery.deliver_once())
    assert delivery.records()["list"][0]["attempts"] == 1
    target(
        delivery,
        id=endpoint["id"],
        expectedRevision=changed["revision"],
        url="http://10.12.0.8:8080/changed",
        enabled=True,
    )
    asyncio.run(delivery.deliver_once())
    assert delivery.records()["list"][0]["status"] == "DEAD"
    events.acknowledge_event(recognized.source_event_id)
    with events.transaction() as db:
        db.execute("UPDATE local_event_history SET stored_at=0")
    events.prune_history(1)
    assert recognized.snapshot_path.exists()
    request_id = str(uuid4())
    delivery.retry(identity, request_id)
    delivery.retry(identity, request_id)

    async def restored(destination, body, source_id):
        assert destination["url"] == endpoint["url"]
        assert body["messageId"] == identity
        assert source_id == recognized.source_event_id
        return 200

    delivery._send = restored
    asyncio.run(delivery.deliver_once())
    assert delivery.records()["list"][0]["status"] == "SUCCEEDED"
    secrets.close()
    events.close()


def test_configuration_conflicts_secret_retention_and_queue_crash_recovery(tmp_path):
    events, secrets, delivery = setup(tmp_path)
    endpoint = target(delivery)
    change = TargetChange(
        id=endpoint["id"],
        expectedRevision=1,
        requestId=str(uuid4()),
        name="更新",
        url=endpoint["url"],
        network="INTERNAL",
        enabled=True,
    )
    updated = delivery.save_target(change)
    assert updated["authConfigured"]
    assert delivery.save_target(change) == updated
    with pytest.raises(DeliveryConflict):
        delivery.save_target(change.model_copy(update={"name": "different"}))
    with pytest.raises(DeliveryConflict):
        delivery.save_target(change.model_copy(update={"request_id": uuid4()}))
    route(delivery, endpoint)
    events.upsert_event(event(tmp_path))
    with events.transaction() as db:
        db.execute("UPDATE gateway_event_delivery SET status='SENDING'")
    secrets.close()
    events.close()
    events, secrets, delivery = setup(tmp_path)
    assert delivery.records()["list"][0]["status"] == "RETRY"
    secrets.close()
    events.close()


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "::1", "169.254.169.254", "0.0.0.0", "ff02::1", "::ffff:127.0.0.1"],  # noqa: S104
)
def test_sensitive_addresses_rejected_for_both_network_modes(address):
    assert not _safe_address(address, "INTERNAL")
    assert not _safe_address(address, "PUBLIC")


def test_private_public_network_contracts():
    assert _safe_address("10.0.0.2", "INTERNAL")
    assert not _safe_address("10.0.0.2", "PUBLIC")
    assert _safe_address("8.8.8.8", "PUBLIC")
    assert not _safe_address("8.8.8.8", "INTERNAL")
    with pytest.raises(ValueError):
        TargetChange(
            id=uuid4(),
            expectedRevision=0,
            requestId=uuid4(),
            name="bad",
            url="http://example.com",
            network="PUBLIC",
        )


def test_http_delivery_pins_dns_preserves_tls_host_and_does_not_redirect(tmp_path, monkeypatch):
    events, secrets, delivery = setup(tmp_path)
    endpoint = target(delivery, url="https://receiver.example/events", network="PUBLIC")
    route(delivery, endpoint)
    recognized = event(tmp_path)
    events.upsert_event(recognized)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    requests = []

    def receive(request):
        requests.append(request)
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "receiver.example"
        assert request.extensions["sni_hostname"] == "receiver.example"
        assert request.headers["authorization"] == "Bearer test-private-key"
        assert request.headers["x-linsight-source-event-id"] == recognized.source_event_id
        assert request.headers["x-linsight-delivery-source"] == "GATEWAY"
        payload = json.loads(request.content)
        assert payload["data"]["result"]["attributes"]["plateNumber"] == "皖A12345"
        assert payload["data"]["snapshot"]["contentType"] == "image/jpeg"
        return httpx.Response(302, headers={"Location": "https://other.example"})

    original_client = httpx.AsyncClient

    def client(**options):
        assert options["trust_env"] is False
        assert options["follow_redirects"] is False
        return original_client(transport=httpx.MockTransport(receive), **options)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    asyncio.run(delivery.deliver_once())
    assert len(requests) == 1
    assert delivery.records()["list"][0]["lastError"] == "HTTP_302"
    assert events.list_events()[0].source_event_id == recognized.source_event_id
    secrets.close()
    events.close()


def test_dns_mixed_allowed_and_forbidden_addresses_is_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, 443))
            for host in ("8.8.8.8", "127.0.0.1")
        ],
    )
    with pytest.raises(ValueError, match="DESTINATION_ADDRESS_REJECTED"):
        asyncio.run(_resolve_target({"url": "https://receiver.example", "network": "PUBLIC"}))


def test_unreadable_target_is_failed_without_blocking_platform_upload(tmp_path):
    events, secrets, delivery = setup(tmp_path)
    route(delivery, target(delivery))
    recognized = event(tmp_path)
    events.upsert_event(recognized)
    with events.transaction() as db:
        db.execute("UPDATE gateway_event_delivery SET target_document=?", (b"corrupt",))
    asyncio.run(delivery.deliver_once())
    assert delivery.records()["list"][0]["status"] == "DEAD"
    assert events.list_events()[0].source_event_id == recognized.source_event_id
    assert recognized.snapshot_path.exists()
    secrets.close()
    events.close()


def test_gateway_api_requires_authentication_and_configures_tcp_stream(tmp_path):
    from fastapi.testclient import TestClient

    from ai_runtime.app.core.config import RuntimeSettings
    from ai_runtime.app.main import create_app

    key = "gateway-delivery-test-runtime-key"
    app = create_app(RuntimeSettings(api_key=key, runtime_data_root=tmp_path))
    client = TestClient(app)
    assert client.post("/v1/gateway/rpc", json={"action": "event-stream.status"}).status_code == 401

    def rpc(action, payload=None):
        return client.post(
            "/v1/gateway/rpc",
            headers={"X-Runtime-Key": key},
            json={"action": action, "payload": payload or {}},
        ).json()

    assert rpc("event-stream.status")["data"]["enabled"] is False
    saved = rpc("event-stream.configure", {
        "enabled": True, "rotateKey": True, "expectedRevision": 0,
    })
    assert saved["ok"]
    assert saved["data"]["enabled"] is True
    assert saved["data"]["key"]
    assert "key" not in rpc("event-stream.status")["data"]
    assert not rpc("event-target.save", {})["ok"]
    asyncio.run(app.state.gateway.close())
    app.state.gateway.tasks.event_store.close()
