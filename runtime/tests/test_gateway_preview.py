import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from ai_runtime.app.gateway.preview import GatewayPreview
from ai_runtime.app.stream.webrtc import WebRtcSessionResponse
from ai_runtime.app.task.contracts import TaskOverlayFrame


def fixture():
    document = {
        "enabled": True,
        "config": {"cameraId": 2, "sourceUrl": "rtsp://user:secret@camera/sub"},
    }
    frame = TaskOverlayFrame(
        taskId=7,
        runId=str(uuid4()),
        cameraId=2,
        frameId="run:1",
        timestamp=datetime.now(UTC),
        sourceWidth=640,
        sourceHeight=480,
        objects=[],
        imageBase64="large-image",
        streamId=str(uuid4()),
        sourcePts=9000,
    )
    gateway = SimpleNamespace(store=Mock(), tasks=Mock())
    gateway.store.get.side_effect = lambda task_id: document if task_id == 7 else None
    gateway.tasks.latest_overlay.return_value = frame
    response = WebRtcSessionResponse(
        sessionId="session-7",
        cameraId=2,
        state="READY",
        subscriberCount=1,
        diagnosticId=str(uuid4()),
        answerSdp="answer",
        answerType="answer",
    )
    manager = SimpleNamespace(
        create_session=AsyncMock(return_value=response),
        get_session=AsyncMock(return_value=response),
        release_session=AsyncMock(),
        has_session=Mock(return_value=True),
    )
    return GatewayPreview(gateway, manager), document, frame


def test_gateway_uses_registered_source_shared_manager_and_metadata_without_jpeg():
    async def scenario():
        preview, _, frame = fixture()
        result = await preview.invoke(
            "preview.open",
            {
                "taskId": 7,
                "offerSdp": "offer",
                "sourceUrl": "rtsp://untrusted/other",
                "cameraId": 999,
            },
        )
        offer = preview.manager.create_session.await_args.args[0]
        assert (
            offer.camera_id == 2
            and offer.source_url.get_secret_value() == "rtsp://user:secret@camera/sub"
        )
        assert "secret" not in str(result)
        result = await preview.invoke("preview.frame", {"taskId": 7, "sessionId": "session-7"})
        assert "imageBase64" not in result
        assert result["sourcePts"] == frame.source_pts and result["streamId"] == frame.stream_id
        assert result["sessionId"] == "session-7" and result["taskId"] == 7
        await preview.invoke("preview.close", {"taskId": 7, "sessionId": "session-7"})
        preview.manager.release_session.assert_awaited_once_with("session-7")
        assert preview.sessions == {}

    asyncio.run(scenario())


def test_unknown_tasks_and_foreign_or_expired_sessions_are_rejected_and_stopped_results_clear():
    async def scenario():
        preview, document, _ = fixture()
        with pytest.raises(KeyError):
            await preview.invoke("preview.open", {"taskId": 8, "offerSdp": "offer"})
        preview.manager.create_session.assert_not_awaited()
        await preview.invoke("preview.open", {"taskId": 7, "offerSdp": "offer"})
        with pytest.raises(KeyError):
            await preview.invoke("preview.frame", {"taskId": 7, "sessionId": "foreign-session"})
        document["enabled"] = False
        assert (
            await preview.invoke("preview.frame", {"taskId": 7, "sessionId": "session-7"}) is None
        )
        preview.manager.has_session.return_value = False
        with pytest.raises(KeyError):
            await preview.invoke("preview.status", {"taskId": 7, "sessionId": "session-7"})
        assert preview.sessions == {}

    asyncio.run(scenario())


def test_multi_algorithm_preview_only_returns_enabled_same_camera_metadata():
    async def scenario():
        preview, document, frame = fixture()
        document['config']['taskId'] = 7
        preview.gateway.store.all.return_value = [document,
            {'enabled': False, 'config': {'cameraId': 2, 'taskId': 8}},
            {'enabled': True, 'config': {'cameraId': 3, 'taskId': 9}},
            {'enabled': True, 'config': {'cameraId': 2, 'taskId': 10}}]
        preview.gateway.tasks.latest_overlay.side_effect = lambda task_id: frame.model_copy(update={'task_id': task_id})
        await preview.invoke('preview.open', {'taskId': 7, 'offerSdp': 'offer'})
        result = await preview.invoke('preview.frames', {'taskId': 7, 'sessionId': 'session-7'})
        assert [item['taskId'] for item in result] == [7, 10]
        assert all('imageBase64' not in item for item in result)
        assert preview.manager.create_session.await_count == 1
    asyncio.run(scenario())
