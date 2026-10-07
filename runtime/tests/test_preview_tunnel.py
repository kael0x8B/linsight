import asyncio
import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from edge_agent.app.core.config import AgentSettings
from edge_agent.app.core.identity import NodeIdentity
from edge_agent.app.preview_tunnel import _handle_request, _tunnel_uri, preview_tunnel_loop


def settings(control_plane_url: str = "http://192.168.2.10:48888") -> AgentSettings:
    return AgentSettings(
        control_plane_url=control_plane_url,
        node_code="edge-1",
        node_name="Edge 1",
        runtime_api_key=SecretStr("runtime-secret"),
    )


def request(action: str, payload: dict) -> str:
    return json.dumps(
        {
            "version": "1.0",
            "requestId": str(uuid4()),
            "action": action,
            "payload": payload,
        }
    )


def test_private_control_plane_uses_outbound_websocket() -> None:
    assert _tunnel_uri(settings()) == "ws://192.168.2.10:48888/node-api/ai-video/preview/tunnel"


def test_explicit_strict_transport_policy_rejects_public_plaintext() -> None:
    with pytest.raises(ValueError, match="private network"):
        _tunnel_uri(settings("http://8.8.8.8:48888").model_copy(
            update={"preview_tunnel_allow_insecure": False}
        ))


@pytest.mark.parametrize("url", ["http://169.139.10.99:48888", "ftp://example.com"])
def test_rejected_tunnel_does_not_cancel_other_agent_workers(
    url: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    connect = Mock()
    monkeypatch.setattr("edge_agent.app.preview_tunnel.connect", connect)
    identity = NodeIdentity(node_id=7, tenant_id=1, credential=SecretStr("node-secret"))
    completed = []

    async def heartbeat_worker() -> None:
        await asyncio.sleep(0)
        completed.append("heartbeat")

    async def scenario() -> None:
        strict_settings = settings(url).model_copy(
            update={"preview_tunnel_allow_insecure": False}
        )
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(preview_tunnel_loop(strict_settings, identity, AsyncMock()))
            tasks.create_task(heartbeat_worker())

    asyncio.run(scenario())
    assert completed == ["heartbeat"]
    connect.assert_not_called()
    assert "Preview tunnel configuration rejected nodeId=7" in caplog.text
    assert "HTTPS" in caplog.text
    assert "node-secret" not in caplog.text


def test_default_transport_supports_http_and_https_control_planes() -> None:
    assert _tunnel_uri(settings("https://example.com")) == (
        "wss://example.com/node-api/ai-video/preview/tunnel"
    )
    assert _tunnel_uri(settings("http://169.139.10.99:48888")) == (
        "ws://169.139.10.99:48888/node-api/ai-video/preview/tunnel"
    )


def test_create_preview_is_forwarded_only_to_local_runtime() -> None:
    async def scenario() -> None:
        websocket = AsyncMock()
        runtime = AsyncMock()
        runtime.create_preview.return_value = {
            "sessionId": uuid4().hex,
            "cameraId": 7,
            "protocol": "HLS",
            "state": "READY",
            "subscriberCount": 1,
            "diagnosticId": str(uuid4()),
        }
        await _handle_request(
            websocket,
            asyncio.Lock(),
            asyncio.Semaphore(1),
            settings(),
            runtime,
            request(
                "preview.create",
                {
                    "cameraId": 7,
                    "sourceUrl": "rtsp://operator:secret@192.168.2.20/live",
                    "streamType": "MAIN",
                },
            ),
        )
        runtime.create_preview.assert_awaited_once_with(
            {
                "cameraId": 7,
                "sourceUrl": "rtsp://operator:secret@192.168.2.20/live",
                "streamType": "MAIN",
            }
        )
        response = json.loads(websocket.send.await_args.args[0])
        assert response["ok"] is True
        assert "sourceUrl" not in response["payload"]

    asyncio.run(scenario())


def test_media_uses_metadata_then_raw_binary_frame() -> None:
    async def scenario() -> None:
        websocket = AsyncMock()
        runtime = AsyncMock()
        runtime.get_preview_media.return_value = (b"segment", "video/mp2t")
        session_id = uuid4().hex
        raw = request("preview.media", {"sessionId": session_id, "fileName": "segment-000001.ts"})
        request_id = json.loads(raw)["requestId"]
        await _handle_request(
            websocket,
            asyncio.Lock(),
            asyncio.Semaphore(1),
            settings(),
            runtime,
            raw,
        )
        assert websocket.send.await_count == 2
        metadata = json.loads(websocket.send.await_args_list[0].args[0])
        assert metadata["frameType"] == "media-meta"
        assert metadata["contentLength"] == 7
        assert websocket.send.await_args_list[1].args[0] == request_id.encode() + b"segment"
        runtime.get_preview_media.assert_awaited_once_with(session_id, "segment-000001.ts")

    asyncio.run(scenario())


def test_webrtc_offer_is_forwarded_without_returning_source_secret() -> None:
    async def scenario() -> None:
        websocket = AsyncMock()
        runtime = AsyncMock()
        runtime.create_webrtc.return_value = {
            "sessionId": uuid4().hex,
            "cameraId": 7,
            "protocol": "WEBRTC",
            "state": "CONNECTING",
            "subscriberCount": 1,
            "diagnosticId": str(uuid4()),
            "answerSdp": "v=0\\r\\n",
            "answerType": "answer",
        }
        payload = {
            "cameraId": 7,
            "sourceUrl": "rtsp://operator:secret@192.168.2.20/sub",
            "offerSdp": "v=0\r\n",
            "offerType": "offer",
        }
        await _handle_request(
            websocket,
            asyncio.Lock(),
            asyncio.Semaphore(1),
            settings(),
            runtime,
            request("webrtc.offer", payload),
        )

        runtime.create_webrtc.assert_awaited_once_with(payload)
        response = json.loads(websocket.send.await_args.args[0])
        assert response["ok"] is True
        assert "sourceUrl" not in response["payload"]
        assert "operator" not in websocket.send.await_args.args[0]
        assert "secret" not in websocket.send.await_args.args[0]

    asyncio.run(scenario())


def test_rule_trial_forwards_to_production_rule_engine_without_starting_task() -> None:
    async def scenario() -> None:
        websocket, runtime = AsyncMock(), AsyncMock()
        payload = {"taskId": 1, "cameraId": 2, "ast": {}, "frames": []}
        runtime.dry_run_rule.return_value = {"confirmed": False, "transitions": []}
        await _handle_request(
            websocket,
            asyncio.Lock(),
            asyncio.Semaphore(1),
            settings(),
            runtime,
            request("rule.dry-run", payload),
        )
        runtime.dry_run_rule.assert_awaited_once_with(payload)
        runtime.start_task.assert_not_called()
        response = json.loads(websocket.send.await_args.args[0])
        assert response["ok"] is True
        assert response["payload"]["confirmed"] is False

    asyncio.run(scenario())
