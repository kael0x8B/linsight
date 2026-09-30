import asyncio
import os

from ai_runtime.app.gateway.platform_connection import (
    normalize_platform_url,
    read_platform_connection,
    write_platform_connection,
)
from edge_agent.app.core.config import AgentSettings
from edge_agent.app.log_delivery.buffer import BufferedLogHandler


def test_platform_connection_normalizes_ip_and_persists_private_override(tmp_path):
    assert normalize_platform_url("192.168.2.11") == "http://192.168.2.11:48888"
    assert normalize_platform_url("https://platform.example") == "https://platform.example"
    assert read_platform_connection(tmp_path, "http://10.0.0.1:48888")["source"] == "DEPLOYMENT"

    saved = write_platform_connection(tmp_path, "192.168.2.17:48888")

    assert saved["platformUrl"] == "http://192.168.2.17:48888"
    assert read_platform_connection(tmp_path, "http://10.0.0.1:48888") == saved
    path = tmp_path / "gateway/platform-connection.json"
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_agent_restarts_loops_when_local_platform_url_changes(tmp_path, monkeypatch):
    async def scenario():
        from edge_agent.app import main as module

        started = asyncio.Event()
        restarted = asyncio.Event()
        urls = []

        async def fake_run(settings, _buffer):
            urls.append(settings.control_plane_url)
            (restarted if len(urls) > 1 else started).set()
            await asyncio.Event().wait()

        monkeypatch.setattr(module, "run", fake_run)
        settings = AgentSettings(
            control_plane_url="http://10.0.0.1:48888",
            node_code="NODE-1",
            node_name="Node 1",
            runtime_api_key="runtime-key",
            runtime_data_root=tmp_path,
        )
        worker = asyncio.create_task(
            module.run_with_platform_reload(
                settings, BufferedLogHandler(100, 60), poll_interval_seconds=0.01
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        write_platform_connection(tmp_path, "http://10.0.0.2:48888")
        await asyncio.wait_for(restarted.wait(), 1)
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        assert urls == ["http://10.0.0.1:48888", "http://10.0.0.2:48888"]

    asyncio.run(scenario())
