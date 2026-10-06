import httpx
from fastapi.testclient import TestClient

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.gateway.console import create_app as create_console
from ai_runtime.app.main import create_app


def test_local_upgrade_requires_session_and_rejects_cross_origin(tmp_path):
    forwarded = []

    def runtime(request):
        forwarded.append(request)
        return httpx.Response(200, json={"ok": True, "data": {"supported": True}})

    settings = RuntimeSettings(
        api_key="test-runtime-key-at-least-24-characters", runtime_data_root=tmp_path
    )
    app = create_console(settings, transport=httpx.MockTransport(runtime))
    body = {"action": "app-upgrade.install", "payload": {"id": "test"}}
    with TestClient(app) as client:
        assert client.post("/gateway-api/rpc", json=body).status_code == 401
        assert not forwarded
        password = (tmp_path / "gateway/local-password").read_text()
        assert client.post("/gateway-api/login", json={"password": password}).status_code == 200
        assert (
            client.post(
                "/gateway-api/rpc", json=body, headers={"Origin": "https://untrusted.invalid"}
            ).status_code
            == 403
        )
        assert not forwarded
        assert client.post("/gateway-api/rpc", json=body).status_code == 200
        assert len(forwarded) == 1


def test_runtime_upgrade_requires_api_key_and_reports_missing_installer(tmp_path, monkeypatch):
    from ai_runtime.app.gateway import application_upgrade

    monkeypatch.setattr(application_upgrade, "SOCKET", tmp_path / "absent.sock")
    settings = RuntimeSettings(
        api_key="test-runtime-key-at-least-24-characters",
        runtime_data_root=tmp_path,
        gateway_console_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        body = {"action": "app-upgrade.status", "payload": {}}
        assert client.post("/v1/gateway/rpc", json=body).status_code in {401, 403}
        response = client.post(
            "/v1/gateway/rpc", json=body, headers={"X-Runtime-Key": settings.api_key}
        )
        assert response.status_code == 200
        assert response.json()["data"]["supported"] is False
