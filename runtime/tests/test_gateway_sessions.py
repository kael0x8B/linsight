import hashlib
import sqlite3

import httpx
from fastapi.testclient import TestClient

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.gateway import session as session_module
from ai_runtime.app.gateway.console import create_app
from ai_runtime.app.gateway.session import SESSION_TTL, GatewaySessions


def test_session_survives_restart_renews_and_logout_revokes(tmp_path, monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr(session_module.time, "time", lambda: now[0])
    settings = RuntimeSettings(
        api_key="gateway-session-test-runtime-key", runtime_data_root=tmp_path
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    app = create_app(settings, transport=transport)
    password = (tmp_path / "gateway/local-password").read_text()
    with TestClient(app) as client:
        assert client.get("/gateway-api/session").status_code == 401
        login = client.post("/gateway-api/login", json={"password": password})
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=strict" in login.headers["set-cookie"]
        assert f"Max-Age={SESSION_TTL}" in login.headers["set-cookie"]
        token = client.cookies.get("linsight_gateway")
    with TestClient(create_app(settings, transport=transport)) as client:
        client.cookies.set("linsight_gateway", token)
        assert client.get("/gateway-api/session").status_code == 200
        # A failing inference service does not invalidate the console login.
        assert client.post("/gateway-api/rpc", json={"action": "snapshot"}).status_code == 503
        assert client.get("/gateway-api/session").status_code == 200
        now[0] += 29 * 24 * 3600
        renewed = client.get("/gateway-api/session")
        assert renewed.status_code == 200
        assert f"Max-Age={SESSION_TTL}" in renewed.headers["set-cookie"]
        client.cookies.clear()
        client.cookies.set("linsight_gateway", token)
        now[0] += 2 * 24 * 3600
        assert client.get("/gateway-api/session").status_code == 200
        assert client.post("/gateway-api/logout", json={}).status_code == 200
        client.cookies.clear()
        client.cookies.set("linsight_gateway", token)
        assert client.get("/gateway-api/session").status_code == 401
    with TestClient(create_app(settings, transport=transport)) as client:
        client.cookies.set("linsight_gateway", token)
        assert client.get("/gateway-api/session").status_code == 401


def test_expiry_rotation_hash_only_storage_and_bounded_sessions(tmp_path, monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr(session_module.time, "time", lambda: now[0])
    sessions = GatewaySessions(tmp_path)
    digest = hashlib.sha256(b"123456").digest()
    token = sessions.create(digest)
    with sqlite3.connect(sessions.path) as connection:
        row = connection.execute("SELECT token_hash FROM session").fetchone()
        assert row[0] != token
        assert row[0] == hashlib.sha256(token.encode()).hexdigest()
    assert sessions.path.stat().st_mode & 0o777 == 0o600
    now[0] += SESSION_TTL
    assert sessions.validate(token, digest) == (False, False)
    token = sessions.create(digest)
    assert sessions.validate(token, hashlib.sha256(b"654321").digest()) == (False, False)
    assert sessions.validate("forged", digest) == (False, False)
    # Repeated sign-in from the same browser replaces its previous session.
    for _ in range(70):
        token = sessions.create(digest, token)
    assert sessions.validate(token, digest) == (True, False)
