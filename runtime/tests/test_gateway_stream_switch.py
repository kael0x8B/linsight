import asyncio
from uuid import uuid4

from pydantic import SecretStr
from test_gateway_autonomy import settings_for
from test_task_manager import FakeModelPool, FakeSharedStream, request

from ai_runtime.app.gateway.service import GatewayChange, GatewayService
from ai_runtime.app.task.manager import TaskManager


def test_stream_selection_survives_offline_restart_and_same_version_platform_start(tmp_path):
    async def scenario():
        settings = settings_for(tmp_path)
        pool = FakeModelPool()
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        config = request(1, str(uuid4()))
        main = "rtsp://operator:main-secret@camera.invalid/main"
        config.stream_urls = {"MAIN": SecretStr(main), "SUB": config.source_url}
        await gateway.platform_start(config, 0)
        result = await gateway.change(GatewayChange(
            taskId=1, expectedRevision=1, requestId=str(uuid4()),
            configuration={"parameters": {"schemaVersion": "1.0", "streamType": "MAIN"}},
        ))
        assert result["revision"] == result["appliedRevision"] == 2
        assert manager._tasks[1].request.source_url.get_secret_value() == main
        await gateway.close()
        await manager.close()

        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        await gateway.reconcile()  # No platform or network access needed.
        assert manager._tasks[1].request.source_url.get_secret_value() == main
        assert manager._tasks[1].request.parameters.stream_type == "MAIN"
        await gateway.platform_start(config.model_copy(update={"run_id": str(uuid4())}), 2)
        assert manager._tasks[1].request.source_url.get_secret_value() == main
        assert gateway.task(1)["config"]["parameters"]["streamType"] == "MAIN"
        await gateway.change(GatewayChange(
            taskId=1, expectedRevision=3, requestId=str(uuid4()),
            configuration={"parameters": {"schemaVersion": "1.0", "streamType": "SUB"}},
        ))
        assert manager._tasks[1].request.source_url == config.source_url
        await gateway.close()
        await manager.close()

    asyncio.run(scenario())
