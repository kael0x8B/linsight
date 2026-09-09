"""Run the authenticated LAN entrance in the Runtime process and event loop."""

import asyncio
import logging
import socket
from contextlib import AsyncExitStack, nullcontext, suppress

import httpx
import uvicorn
from fastapi import FastAPI

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.gateway.console import console_static_root, create_app

LOGGER = logging.getLogger("linsight.gateway.console")


class _EmbeddedServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, ready: asyncio.Event):
        super().__init__(config)
        self.ready = ready

    def capture_signals(self):
        # Only the outer Runtime server may own SIGTERM/SIGINT.
        return nullcontext()

    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        self.ready.set()


class GatewayListener:
    def __init__(self, settings: RuntimeSettings, runtime: FastAPI):
        self.settings = settings
        self.runtime = runtime
        self.port = settings.gateway_console_port
        self.server: _EmbeddedServer | None = None
        self.worker: asyncio.Task | None = None
        self.ready = asyncio.Event()
        self._stopping = False
        self._resources = AsyncExitStack()

    def _bind(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.settings.gateway_console_host, self.port))
            sock.setblocking(False)
            self.port = sock.getsockname()[1]
            return sock
        except OSError:
            sock.close()
            raise

    async def start(self) -> None:
        if not self.settings.gateway_console_enabled:
            return
        if not (console_static_root() / "gateway.html").is_file():
            raise RuntimeError("Gateway console assets missing from Runtime package")
        # Bind before acknowledging Runtime startup; occupied ports cannot look healthy.
        sock = self._bind()
        try:
            app = create_app(
                self.settings, transport=httpx.ASGITransport(app=self.runtime), runtime_owned=True
            )
            await self._resources.enter_async_context(app.router.lifespan_context(app))
            self.worker = asyncio.create_task(self._serve(app, sock), name="gateway-console")
            async with asyncio.timeout(10):
                await self.ready.wait()
            LOGGER.info("Gateway console ready port=%s owner=runtime", self.port)
        except BaseException:
            sock.close()
            await self.close()
            raise

    async def _serve(self, app: FastAPI, sock: socket.socket) -> None:
        while not self._stopping:
            try:
                self.server = _EmbeddedServer(
                    uvicorn.Config(
                        app,
                        lifespan="off",
                        log_config=None,
                        access_log=False,
                        proxy_headers=False,
                        timeout_graceful_shutdown=5,
                    ),
                    self.ready,
                )
                await self.server.serve(sockets=[sock])
            except Exception as error:
                LOGGER.error("Gateway console failed errorType=%s", type(error).__name__)
            finally:
                self.ready.clear()
                if self.server:
                    self.server.started = False
                    for listener in getattr(self.server, "servers", []):
                        listener.close()
                        await listener.wait_closed()
                sock.close()
            if not self._stopping:
                LOGGER.warning("Gateway console restarting port=%s", self.port)
                while not self._stopping:
                    await asyncio.sleep(3)
                    try:
                        sock = self._bind()
                        break
                    except OSError:
                        LOGGER.warning("Gateway console port unavailable port=%s", self.port)

    async def close(self) -> None:
        self._stopping = True
        if self.server:
            self.server.should_exit = True
        if self.worker:
            try:
                await asyncio.wait_for(asyncio.shield(self.worker), timeout=8)
            except TimeoutError:
                self.worker.cancel()
                with suppress(asyncio.CancelledError):
                    await self.worker
        await self._resources.aclose()
