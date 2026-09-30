import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_task_manager import FakeModelPool, FakeSharedStream, request

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.gateway.console import create_app as create_console
from ai_runtime.app.main import create_app
from ai_runtime.app.task.manager import TaskManager


@pytest.fixture
def local_editor(tmp_path):
    settings = RuntimeSettings(
        api_key="local-task-save-test-key-at-least-24-chars",
        runtime_data_root=tmp_path,
        gateway_console_enabled=False,
    )
    pool = FakeModelPool()
    tasks = TaskManager(settings, pool, FakeSharedStream)
    runtime = create_app(settings, model_pool=pool, task_manager=tasks)
    gateway = runtime.state.gateway
    config = request(39, str(uuid4()))
    raw = config.model_dump(mode="json", by_alias=True)
    raw["sourceUrl"] = config.source_url.get_secret_value()
    gateway.store.save(
        {
            "config": raw,
            "revision": 16,
            "platformManaged": True,
            "enabled": False,
            "name": "车辆识别",
        },
        "seed",
        "seed",
    )
    console = create_console(
        settings, transport=httpx.ASGITransport(app=runtime), static_root=tmp_path / "www"
    )
    with TestClient(console) as client:
        password = (tmp_path / "gateway/local-password").read_text()
        assert client.post("/gateway-api/login", json={"password": password}).status_code == 200
        yield client, gateway


def save_payload():
    return {
        "taskId": 39,
        "expectedRevision": 16,
        "requestId": str(uuid4()),
        "configuration": {"parameters": {"schemaVersion": "1.0", "confidence": 0.72}},
    }


@pytest.mark.parametrize("ownership_hint", [None, False, True])
def test_local_save_accepts_current_and_cached_editors_without_changing_ownership(
    local_editor, ownership_hint
):
    client, gateway = local_editor
    payload = save_payload()
    if ownership_hint is not None:
        payload.update(platformManaged=ownership_hint, streamTypeChanged=False)
    result = client.post(
        "/gateway-api/rpc", json={"action": "task.save", "payload": payload}
    ).json()
    assert result["ok"], result
    saved = result["data"]
    assert saved["revision"] == saved["appliedRevision"] == 17
    assert saved["config"]["parameters"]["confidence"] == 0.72
    assert saved["platformManaged"] is True
    assert saved["enabled"] is False
    assert gateway.store.get(39)["origin"] == "LOCAL"

    # Retrying a cached request and its refreshed-page equivalent is one mutation.
    payload.pop("platformManaged", None)
    payload.pop("streamTypeChanged", None)
    replay = client.post(
        "/gateway-api/rpc", json={"action": "task.save", "payload": payload}
    ).json()
    assert replay["ok"] and replay["data"]["revision"] == 17
    payload["requestId"] = str(uuid4())
    conflict = client.post(
        "/gateway-api/rpc", json={"action": "task.save", "payload": payload}
    ).json()
    assert conflict["code"] == 409
    assert gateway.store.get(39)["revision"] == 17


@pytest.mark.parametrize("extra", [{"streamTypeChanged": True}, {"unexpectedField": True}])
def test_local_save_does_not_silently_ignore_stream_switches_or_other_invalid_fields(
    local_editor, extra
):
    client, gateway = local_editor
    result = client.post(
        "/gateway-api/rpc",
        json={"action": "task.save", "payload": {**save_payload(), **extra}},
    ).json()
    assert result["ok"] is False
    assert result["code"] == 422
    if "streamTypeChanged" in extra:
        assert "切换主/子码流" in result["message"]
    else:
        assert "unexpectedField" in result["message"]
    assert gateway.store.get(39)["revision"] == 16


def test_local_stream_switch_changes_source_and_preserves_encrypted_addresses(local_editor):
    client, gateway = local_editor
    main = "rtsp://operator:main-secret@camera.invalid/main"
    payload = save_payload()
    payload["configuration"] = {
        "parameters": {"schemaVersion": "1.0", "streamType": "MAIN"},
        "streamUrls": {"MAIN": main},
    }
    preflight = client.post("/gateway-api/rpc", json={
        "action": "task.capacity.preflight",
        "payload": {"taskId": 39, "configuration": payload["configuration"]},
    }).json()
    assert preflight["ok"], preflight
    assert gateway.store.get(39)["revision"] == 16
    saved = client.post("/gateway-api/rpc", json={"action": "task.save", "payload": payload}).json()
    assert saved["ok"], saved
    assert saved["data"]["availableStreamTypes"] == ["MAIN", "SUB"]
    assert saved["data"]["config"]["parameters"]["streamType"] == "MAIN"
    assert "main-secret" not in json.dumps(saved)
    assert "streamUrls" not in saved["data"]["config"]
    assert gateway.store.get(39)["config"]["sourceUrl"] == main
    assert saved["data"]["enabled"] is False

    # Select SUB without sending any address (the normal local UI request).
    payload.update(expectedRevision=17, requestId=str(uuid4()))
    payload["configuration"] = {
        "parameters": {"schemaVersion": "1.0", "streamType": "SUB"}, "sourceUrl": ""
    }
    saved = client.post("/gateway-api/rpc", json={"action": "task.save", "payload": payload}).json()
    assert saved["ok"], saved
    document = gateway.store.get(39)
    assert document["config"]["sourceUrl"] == "rtsp://camera.invalid/live"
    assert document["config"]["streamUrls"]["MAIN"] == main
    assert document["revision"] == 18
    assert "main-secret" not in json.dumps(gateway.snapshot())
    for path in gateway.settings.runtime_data_root.glob("gateway/configuration.sqlite3*"):
        assert b"main-secret" not in path.read_bytes()


@pytest.mark.parametrize("streams", [None, {"MAIN": "https://secret@camera.invalid/main"},
                                    {"OTHER": "rtsp://camera.invalid/other"}])
def test_local_stream_switch_rejects_missing_or_invalid_address(local_editor, streams):
    client, gateway = local_editor
    payload = save_payload()
    payload["configuration"] = {"parameters": {"schemaVersion": "1.0", "streamType": "MAIN"}}
    if streams is not None:
        payload["configuration"]["streamUrls"] = streams
    result = client.post(
        "/gateway-api/rpc", json={"action": "task.save", "payload": payload}
    ).json()
    assert result["ok"] is False and result["code"] == 422, result
    assert "secret" not in json.dumps(result)
    assert gateway.store.get(39)["revision"] == 16
    assert gateway.store.get(39)["config"]["sourceUrl"] == "rtsp://camera.invalid/live"


def test_platform_address_backfill_preserves_local_source_and_parameters(local_editor):
    client, gateway = local_editor
    payload = save_payload()
    payload["configuration"] = {"streamUrlDefaults": {
        "MAIN": "rtsp://camera.invalid/catalog-main",
        "SUB": "rtsp://camera.invalid/catalog-sub",
    }}
    result = client.post(
        "/gateway-api/rpc", json={"action": "task.save", "payload": payload}
    ).json()
    assert result["ok"], result
    config = gateway.store.get(39)["config"]
    assert config["sourceUrl"] == config["streamUrls"]["SUB"] == "rtsp://camera.invalid/live"
    assert config["streamUrls"]["MAIN"] == "rtsp://camera.invalid/catalog-main"
    assert config["parameters"]["confidence"] == 0.5
    assert "streamUrlDefaults" not in config
