import asyncio
import hashlib
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_gateway_autonomy import settings_for
from test_task_manager import FakeModelPool, FakeSharedStream, request

from ai_runtime.app.gateway.service import GatewayChange, GatewayConflict, GatewayService
from ai_runtime.app.gateway.store import GatewayStore
from ai_runtime.app.main import create_app
from ai_runtime.app.task.manager import TaskManager
from edge_agent.app.client.control_plane import ControlPlaneClient
from edge_agent.app.core.identity import NodeIdentity
from edge_agent.app.main import sync_task_removals


def test_removal_survives_restart_ack_and_rejects_queued_start(tmp_path):
    async def scenario():
        settings = settings_for(tmp_path)
        pool = FakeModelPool()
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        config = request(51, str(uuid4()))
        await gateway.platform_start(config, 0)
        await gateway.platform_stop(51, config.run_id, 1)
        change = GatewayChange(taskId=51, expectedRevision=2, requestId=str(uuid4()))
        await gateway.remove(change)
        await gateway.remove(change)
        assert not gateway.statuses()  # TaskManager still has the old STOPPED run.
        assert not gateway.snapshot()["tasks"]
        pending = gateway.store.removals(pending_only=True)
        assert len(pending) == 1
        assert pending[0]["gatewayRevision"] == 3
        assert pending[0]["runId"] == config.run_id
        with pytest.raises(GatewayConflict):
            await gateway.platform_start(config, 0)  # even a duplicate old command
        await gateway.close()
        await manager.close()

        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        assert gateway.store.removals(pending_only=True) == pending
        with pytest.raises(ValueError):
            gateway.store.acknowledge_removal(51, str(uuid4()), 3)
        gateway.store.acknowledge_removal(51, str(change.request_id), 3)
        assert not gateway.store.removals(pending_only=True)
        with pytest.raises(GatewayConflict):
            await gateway.change(
                GatewayChange(taskId=51, expectedRevision=0, requestId=str(uuid4()))
            )
        await gateway.close()
        await manager.close()
        store = GatewayStore(tmp_path / "gateway")
        assert store.is_removed(51)
        assert not store.removals(pending_only=True)
        store.close()

    asyncio.run(scenario())


def test_upgrade_recovers_only_verified_legacy_delete_receipts(tmp_path):
    store = GatewayStore(tmp_path)
    run = str(uuid4())
    removal_id = str(uuid4())
    with store._db:
        store._db.executemany(
            "INSERT INTO mutation_receipt VALUES (?, ?, ?, ?)",
            [
                (f"platform-start:{run}:2", "start-fingerprint", 31, 1),
                (str(uuid4()), "stop-fingerprint", 31, 2),
                (removal_id, hashlib.sha256(b"remove:31:2").hexdigest(), 31, 2),
                # Merely being absent, even after a start, is not proof of deletion.
                (f"platform-start:{uuid4()}:1", "start-fingerprint", 32, 1),
                # Local-only task IDs must never delete a platform task.
                (str(uuid4()), hashlib.sha256(b"remove:33:1").hexdigest(), 33, 1),
            ],
        )
    store.close()
    store = GatewayStore(tmp_path)
    records = store.removals()
    assert len(records) == 2
    assert records[0]["taskId"] == 31
    assert records[0]["runId"] == run
    assert records[0]["configVersion"] == 2
    assert records[0]["requestId"] == removal_id
    assert records[0]["platformManaged"]
    assert records[1]["platformManaged"] is False
    assert not store.is_removed(32)
    store.acknowledge_removal(31, removal_id, 3)
    store.close()
    store = GatewayStore(tmp_path)
    assert [item["taskId"] for item in store.removals(pending_only=True)] == [33]
    store.close()


def test_removal_journal_and_configuration_rollback_together(tmp_path):
    store = GatewayStore(tmp_path)
    document = {"revision": 1, "config": {"taskId": 31, "runId": str(uuid4()), "configVersion": 1}}
    store.save(document, "already-used", "seed")
    with pytest.raises(sqlite3.IntegrityError):
        store.remove(31, 1, "already-used", "remove-fingerprint")
    assert store.get(31) == document
    assert not store.removals()
    store.close()


def test_agent_acknowledges_only_after_platform_accepts_and_retries_lost_ack():
    async def scenario():
        identity = SimpleNamespace(node_id=1)
        removals = [{"taskId": 31, "requestId": str(uuid4()), "gatewayRevision": 3}]
        client = SimpleNamespace(report_task_removal=AsyncMock(side_effect=RuntimeError("offline")))
        runtime = SimpleNamespace(
            gateway_rpc=AsyncMock(return_value={"ok": True, "data": removals})
        )
        await sync_task_removals(identity, client, runtime)
        assert runtime.gateway_rpc.await_count == 1  # no ACK after a failed report
        client.report_task_removal.side_effect = None
        runtime.gateway_rpc.reset_mock()
        runtime.gateway_rpc.side_effect = [{"ok": True, "data": removals}, OSError("lost ack")]
        await sync_task_removals(identity, client, runtime)
        runtime.gateway_rpc.side_effect = [{"ok": True, "data": removals}, {"ok": True}]
        await sync_task_removals(identity, client, runtime)
        assert client.report_task_removal.await_count == 3
        runtime.gateway_rpc.assert_awaited_with(
            {"action": "task-removal.ack", "payload": removals[0]}
        )

    asyncio.run(scenario())


def test_removed_local_task_keeps_local_event_ownership(tmp_path):
    async def scenario():
        settings = settings_for(tmp_path)
        pool = FakeModelPool()
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        config = request(100001, str(uuid4()))
        raw = config.model_dump(mode="json", by_alias=True)
        raw["sourceUrl"] = config.source_url.get_secret_value()
        await gateway.change(
            GatewayChange(
                taskId=100001,
                expectedRevision=0,
                requestId=str(uuid4()),
                configuration=raw,
                enabled=False,
            )
        )
        await gateway.remove(
            GatewayChange(taskId=100001, expectedRevision=1, requestId=str(uuid4()))
        )
        assert gateway.store.removals()[0]["platformManaged"] is False
        assert 100001 in manager.event_store.local_task_ids
        await gateway.close()
        await manager.close()

    asyncio.run(scenario())


def test_agent_and_runtime_removal_contract_requires_ack_origin(tmp_path):
    app = create_app(settings_for(tmp_path))
    gateway = app.state.gateway
    config = request(51, str(uuid4()))
    raw = config.model_dump(mode="json", by_alias=True)
    removal_id = str(uuid4())
    gateway.store.save({"config": raw, "revision": 2, "platformManaged": True}, "seed", "seed")
    gateway.store.remove(51, 2, removal_id, hashlib.sha256(b"remove:51:2").hexdigest())
    client = TestClient(app)
    headers = {"X-Runtime-Key": settings_for(tmp_path).api_key}
    response = client.post("/v1/gateway/rpc", headers=headers, json={"action": "task-removal.list"})
    removal = response.json()["data"][0]
    assert "platformManaged" not in removal
    body = {"action": "task-removal.ack", "payload": removal}
    assert not client.post("/v1/gateway/rpc", headers=headers, json=body).json()["ok"]
    assert gateway.store.removals(pending_only=True)
    headers["X-Gateway-Origin"] = "PLATFORM"
    assert client.post("/v1/gateway/rpc", headers=headers, json=body).json()["ok"]
    assert not gateway.store.removals(pending_only=True)

    async def report():
        control = ControlPlaneClient("http://platform.invalid", 10)
        await control.close()

        def handle(req):
            assert req.url.path == "/node-api/ai-video/task/removal/report"
            assert req.headers["X-Node-Id"] == "1"
            assert req.headers["tenant-id"] == "1"
            assert req.headers["X-Node-Credential"] == "test-node-credential"
            return httpx.Response(200, json={"code": 0, "data": True})

        control._client = httpx.AsyncClient(
            base_url="http://platform.invalid", transport=httpx.MockTransport(handle)
        )
        await control.report_task_removal(
            NodeIdentity(node_id=1, tenant_id=1, credential="test-node-credential"), removal
        )
        await control.close()
        await gateway.close()
        await gateway.tasks.close()

    asyncio.run(report())
