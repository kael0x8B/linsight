from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from ai_runtime.app.api.http import build_router
from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.gateway.listener import GatewayListener
from ai_runtime.app.gateway.service import GatewayService
from ai_runtime.app.model.dependencies import DependencyManager
from ai_runtime.app.model.deployed import DeployedModelRegistry
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.stream.preview import PreviewManager
from ai_runtime.app.stream.probe import StreamProbeService
from ai_runtime.app.stream.shared import CameraMediaHub
from ai_runtime.app.stream.webrtc import WebRtcManager
from ai_runtime.app.task.manager import TaskManager


def create_app(
    settings: RuntimeSettings | None = None,
    preview_manager: PreviewManager | None = None,
    webrtc_manager: WebRtcManager | None = None,
    model_pool: ModelPool | None = None,
    task_manager: TaskManager | None = None,
) -> FastAPI:
    runtime_settings = settings or RuntimeSettings()  # type: ignore[call-arg]
    manager = preview_manager or PreviewManager(runtime_settings)
    media_hub = CameraMediaHub(runtime_settings)
    rtc_manager = webrtc_manager or WebRtcManager(runtime_settings, media_hub=media_hub)
    pool = model_pool or ModelPool(
        runtime_settings.model_pool_size,
        DependencyManager(runtime_settings.runtime_data_root),
        onnx_intra_op_threads=runtime_settings.onnx_intra_op_threads,
        registry=DeployedModelRegistry(runtime_settings.runtime_data_root),
    )
    tasks = task_manager or TaskManager(runtime_settings, pool, media_hub.capture_stream)

    gateway = GatewayService(runtime_settings, pool, tasks)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with AsyncExitStack() as resources:
            resources.push_async_callback(manager.close)
            resources.push_async_callback(media_hub.close)
            resources.push_async_callback(rtc_manager.close)
            resources.push_async_callback(pool.close)
            resources.push_async_callback(tasks.close)
            resources.push_async_callback(gateway.close)
            await manager.start()
            await rtc_manager.start()
            await gateway.start()
            console = GatewayListener(runtime_settings, _app)
            _app.state.gateway_console = console
            resources.push_async_callback(console.close)
            await console.start()
            yield

    app = FastAPI(title="LInsight AI Runtime", version="0.1.0", lifespan=lifespan)
    app.include_router(
        build_router(
            runtime_settings,
            StreamProbeService(ffprobe_binary=runtime_settings.ffprobe_binary),
            manager,
            rtc_manager,
            pool,
            tasks,
            gateway,
        )
    )
    app.state.gateway = gateway
    return app
