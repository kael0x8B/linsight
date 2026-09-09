import asyncio
import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_model_pool import _write_contract_model
from test_task_manager import FakeModelPool, FakeSharedStream, request

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.event.store import OfflineEventStore, PendingEvent
from ai_runtime.app.gateway.service import GatewayChange, GatewayConflict, GatewayService
from ai_runtime.app.main import create_app
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.task.manager import TaskManager
from edge_agent.app.local_console import create_app as create_console


def settings_for(root):
    return RuntimeSettings(
        api_key="test-runtime-key-at-least-24-characters", runtime_data_root=root
    )


def test_local_edit_conflict_replay_and_restart_without_platform(tmp_path):
    async def scenario():
        settings = settings_for(tmp_path)
        pool = FakeModelPool()
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        config = request(1, str(uuid4()))
        config.source_url = "rtsp://operator:private-password@camera.invalid/live"
        from pydantic import SecretStr

        config.source_url = SecretStr(config.source_url)
        await gateway.platform_start(config, 0)
        change = GatewayChange(
            taskId=1,
            expectedRevision=1,
            requestId=str(uuid4()),
            configuration={"parameters": {"schemaVersion": "1.0", "confidence": 0.72}},
        )
        result = await gateway.change(change)
        assert result["revision"] == result["appliedRevision"] == 2
        assert result["config"]["parameters"]["confidence"] == 0.72
        assert "private-password" not in json.dumps(result)
        replay = await gateway.change(change)
        assert replay["revision"] == 2
        with pytest.raises(GatewayConflict):
            await gateway.change(change.model_copy(update={"request_id": uuid4()}))
        with pytest.raises(GatewayConflict):
            await gateway.platform_stop(1, config.run_id, 1)
        await gateway.close()
        await manager.close()
        assert b"private-password" not in (tmp_path / "gateway/configuration.sqlite3").read_bytes()

        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        await gateway.reconcile()
        assert gateway.status(1).status == "RUNNING"
        assert manager._tasks[1].request.parameters.confidence == 0.72
        assert (
            manager._tasks[1].request.source_url.get_secret_value().startswith("rtsp://operator:")
        )
        await gateway.platform_stop(1, config.run_id, 2)
        assert gateway.status(1).status == "STOPPED"
        await gateway.close()
        await manager.close()

        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        await gateway.reconcile()
        assert not manager.statuses()  # A stopped task must not resurrect after a power loss.
        new_run = config.model_copy(update={"run_id": str(uuid4())})
        await gateway.platform_start(new_run, 3)
        assert manager._tasks[1].request.parameters.confidence == 0.72
        await gateway.close()
        await manager.close()

    asyncio.run(scenario())


def test_concurrent_entrances_only_one_revision_wins(tmp_path):
    async def scenario():
        settings = settings_for(tmp_path)
        pool = FakeModelPool()
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        await gateway.platform_start(request(2, str(uuid4())), 0)
        changes = [
            GatewayChange(taskId=2, expectedRevision=1, requestId=str(uuid4()), name=name)
            for name in ("现场修改", "平台修改")
        ]
        results = await asyncio.gather(
            *(gateway.change(c) for c in changes), return_exceptions=True
        )
        assert sum(isinstance(r, GatewayConflict) for r in results) == 1
        assert gateway.task(2)["revision"] == 2
        await gateway.close()
        await manager.close()

    asyncio.run(scenario())


def test_runtime_restores_real_onnx_model_without_agent(tmp_path):
    async def scenario():
        settings = settings_for(tmp_path)
        path = tmp_path / "models/person.onnx"
        path.parent.mkdir()
        _write_contract_model(path)
        deploy = DeployModelRequest(
            modelVersionId=40,
            artifactPath=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            adapter="person_detection_v1",
        )
        pool = ModelPool(max_models=2)
        await pool.deploy(deploy)
        tasks = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, tasks)
        gateway.models.record(deploy.model_dump(mode="json", by_alias=True, exclude_none=True))
        await gateway.platform_start(request(3, str(uuid4())), 0)
        await gateway.close()
        await tasks.close()
        await pool.close()
        pool = ModelPool(max_models=2)
        tasks = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, tasks)
        assert not pool.is_loaded(40)
        await gateway.reconcile()
        assert pool.is_loaded(40)
        assert gateway.status(3).status == "RUNNING"
        await gateway.close()
        await tasks.close()
        await pool.close()

    asyncio.run(scenario())


def test_local_history_survives_upload_ack_and_respects_pending_evidence(tmp_path):
    store = OfflineEventStore(tmp_path / "delivery.sqlite3", retain_history=True)
    ids = [str(uuid4()), str(uuid4())]
    for event_id in ids:
        root = tmp_path / event_id
        root.mkdir()
        path = root / "snapshot.jpg"
        path.write_bytes(b"evidence")
        store.upsert_event(
            PendingEvent(
                sourceEventId=event_id, payload={"taskId": 1}, snapshotPath=path, finalized=True
            )
        )
    store.acknowledge_event(ids[0])
    assert len(store.list_events()) == 1
    assert store.history()["total"] == 2
    assert store.history_media(ids[0], "snapshot").read_bytes() == b"evidence"
    store._connection.execute("UPDATE local_event_history SET stored_at=0")
    store._connection.commit()
    store.prune_history(1)
    assert store.history()["total"] == 1
    assert store.history_media(ids[1], "snapshot").exists()
    assert not (tmp_path / ids[0] / "snapshot.jpg").exists()
    store.close()


def test_local_login_csrf_internal_api_isolation_and_password_rotation(tmp_path):
    settings = settings_for(tmp_path)
    runtime = create_app(settings)
    console = create_console(
        settings, transport=httpx.ASGITransport(app=runtime), static_root=tmp_path / "www"
    )
    password = (tmp_path / "gateway/local-password").read_text()
    with TestClient(console) as client:
        assert client.post("/gateway-api/rpc", json={"action": "snapshot"}).status_code == 401
        assert client.get("/v1/tasks/statuses").status_code == 404
        assert (
            client.post(
                "/gateway-api/login",
                json={"password": password},
                headers={"Origin": "https://attacker.invalid"},
            ).status_code
            == 403
        )
        assert client.post("/gateway-api/login", json={"password": "wrong"}).status_code == 401
        assert client.post("/gateway-api/login", json={"password": password}).status_code == 200
        snapshot = client.post("/gateway-api/rpc", json={"action": "snapshot"})
        assert snapshot.json()["data"]["tasks"] == []
        assert settings.api_key not in snapshot.text
        assert password not in snapshot.text
        result = client.post(
            "/gateway-api/rpc",
            json={"action": "access.password", "payload": {"password": "new-local-password-123"}},
        )
        assert result.json()["ok"]
        assert client.post("/gateway-api/rpc", json={"action": "snapshot"}).status_code == 401
        assert (
            client.post(
                "/gateway-api/login", json={"password": "new-local-password-123"}
            ).status_code
            == 200
        )


def test_failed_apply_is_persistent_and_recovers(tmp_path):
    class FailingStream(FakeSharedStream):
        failing = True

        async def start(self):
            if self.failing:
                raise OSError("unreachable camera")
            await super().start()

    async def scenario():
        settings = settings_for(tmp_path)
        pool = FakeModelPool()
        tasks = TaskManager(settings, pool, FailingStream)
        gateway = GatewayService(settings, pool, tasks)
        status = await gateway.platform_start(request(4, str(uuid4())), 0)
        assert status.status == "FAILED"
        assert gateway.task(4)["appliedRevision"] == 0
        FailingStream.failing = False
        await gateway.reconcile()
        assert gateway.status(4).status == "RUNNING"
        assert gateway.task(4)["appliedRevision"] == 1
        await gateway.close()
        await tasks.close()

    asyncio.run(scenario())


def test_local_only_events_are_bounded_without_waiting_for_a_platform(tmp_path):
    store = OfflineEventStore(tmp_path / "delivery.sqlite3", retain_history=True)
    store.local_task_ids = {77}
    event_id = str(uuid4())
    root = tmp_path / event_id
    root.mkdir()
    path = root / "snapshot.jpg"
    path.write_bytes(b"local evidence")
    store.upsert_event(
        PendingEvent(
            sourceEventId=event_id, payload={"taskId": 77}, snapshotPath=path, finalized=True
        )
    )
    store.enqueue_transition({"sourceEventId": event_id, "state": "CLOSED"})
    assert not store.list_events()
    assert not store.list_transitions()
    assert store.history()["list"][0]["localOnly"]
    store._connection.execute("UPDATE local_event_history SET stored_at=0")
    store._connection.commit()
    store.prune_history(1)
    assert store.history()["total"] == 0
    assert not path.exists()
    store.close()


def test_local_model_upload_executes_real_onnx_and_rejects_duplicate_version(tmp_path):
    import base64

    settings = settings_for(tmp_path)
    runtime = create_app(settings)
    source = tmp_path / "source.onnx"
    _write_contract_model(source)
    encoded = base64.b64encode(
        json.dumps(
            {
                "modelVersionId": 101,
                "artifactFormat": "ONNX",
                "adapter": "person_detection_v1",
                "device": "CPU",
            }
        ).encode()
    ).decode()
    client = TestClient(runtime)
    headers = {"X-Runtime-Key": settings.api_key, "X-Model-Manifest": encoded}
    response = client.post(
        "/v1/gateway/models/upload", headers=headers, content=source.read_bytes()
    )
    assert response.json()["ok"]
    assert runtime.state.gateway.pool.is_loaded(101)
    assert (
        runtime.state.gateway.models.summaries()[0]["sha256"]
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    repeated = client.post(
        "/v1/gateway/models/upload", headers=headers, content=source.read_bytes()
    )
    assert repeated.json()["code"] == 409
    assert len(list((tmp_path / "models/local").glob("*.artifact"))) == 1
