import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.main import create_app


def settings_for(root, **kwargs):
    return RuntimeSettings(
        api_key="gateway-listener-integration-test-key",
        runtime_data_root=root,
        gateway_console_host="127.0.0.1",
        gateway_console_port=0,
        gateway_runtime_url="http://127.0.0.1:1",  # No loopback HTTP proxy is needed.
        **kwargs,
    )


def test_listener_shares_runtime_auth_state_and_recovers_without_another_service(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app(settings)
    with TestClient(app) as internal:
        listener = app.state.gateway_console
        address = f"http://127.0.0.1:{listener.port}"
        password = (tmp_path / "gateway/local-password").read_text()
        with httpx.Client(base_url=address, trust_env=False) as local:
            assert local.get("/").status_code == 200
            assert local.get("/gateway-health").json() == {"status": "UP", "owner": "runtime"}
            assert local.get("/v1/tasks/statuses").status_code == 404
            assert local.post("/gateway-api/rpc", json={"action": "snapshot"}).status_code == 401
            assert local.post("/gateway-api/login", json={"password": password}).is_success
            assert local.post("/gateway-api/rpc", json={"action": "snapshot"}).json()["ok"]

            async def restart_listener():
                old_server = listener.server
                listener.ready.clear()
                old_server.should_exit = True
                async with asyncio.timeout(8):
                    await listener.ready.wait()
                assert listener.server is not old_server

            internal.portal.call(restart_listener)
            assert local.get("/gateway-health").is_success
            assert local.post("/gateway-api/rpc", json={"action": "snapshot"}).json()["ok"]
            updated = internal.post(
                "/v1/gateway/rpc",
                headers={"X-Runtime-Key": settings.api_key},
                json={"action": "access.password", "payload": {"password": "new-password-12345"}},
            )
            assert updated.json()["ok"]
            assert local.post("/gateway-api/rpc", json={"action": "snapshot"}).status_code == 401
    assert listener.worker.done()
    with pytest.raises(httpx.ConnectError):
        httpx.get(address, timeout=1, trust_env=False)


def test_missing_assets_or_occupied_port_prevent_false_healthy_start(tmp_path, monkeypatch):
    from ai_runtime.app.gateway import listener as module

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        settings = settings_for(tmp_path / "occupied")
        settings.gateway_console_port = occupied.getsockname()[1]
        with pytest.raises(OSError), TestClient(create_app(settings)):
            pytest.fail("Runtime must not announce ready with a broken LAN listener")
    monkeypatch.setattr(module, "console_static_root", lambda: tmp_path / "missing")
    with (
        pytest.raises(RuntimeError, match="assets missing"),
        TestClient(create_app(settings_for(tmp_path / "missing-assets"))),
    ):
        pytest.fail("Missing UI assets must fail before deployment commit")


def test_existing_uvicorn_command_starts_both_ports_and_stops_cleanly(tmp_path):
    def free_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    runtime_port, console_port = free_port(), free_port()
    env = dict(
        os.environ,
        LINSIGHT_RUNTIME_API_KEY="subprocess-runtime-test-key-12345",
        LINSIGHT_RUNTIME_DATA_ROOT=str(tmp_path),
        LINSIGHT_RUNTIME_GATEWAY_CONSOLE_ENABLED="true",
        LINSIGHT_RUNTIME_GATEWAY_CONSOLE_HOST="127.0.0.1",
        LINSIGHT_RUNTIME_GATEWAY_CONSOLE_PORT=str(console_port),
    )
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "ai_runtime.app.main:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(runtime_port),
    ]
    initial_password = None
    for _ in range(2):
        with (tmp_path / "runtime.log").open("a") as log:
            process = subprocess.Popen(  # noqa: S603 - current interpreter, fixed local module
                command,
                env=env,
                cwd=Path(__file__).resolve().parents[1],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 15
                while True:
                    assert process.poll() is None, (tmp_path / "runtime.log").read_text()
                    try:
                        response = httpx.get(
                            f"http://127.0.0.1:{runtime_port}/v1/health", timeout=1, trust_env=False
                        )
                        if response.is_success:
                            break
                    except httpx.ConnectError:
                        pass
                    assert time.monotonic() < deadline, "Runtime startup timeout"
                    time.sleep(0.05)
                response = httpx.get(
                    f"http://127.0.0.1:{console_port}/gateway-health", timeout=2, trust_env=False
                )
                assert response.json() == {"status": "UP", "owner": "runtime"}
                assert httpx.get(f"http://127.0.0.1:{console_port}/", trust_env=False).is_success
                password = (tmp_path / "gateway/local-password").read_text()
                if initial_password is None:
                    initial_password = password
                assert password == initial_password
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    pytest.fail("SIGTERM did not shut down both listeners")
            with pytest.raises(httpx.ConnectError):
                httpx.get(f"http://127.0.0.1:{console_port}/", timeout=1, trust_env=False)
