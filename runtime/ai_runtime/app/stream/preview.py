import asyncio
import contextlib
import logging
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ai_runtime.app.core.config import RuntimeSettings

LOGGER = logging.getLogger("linsight.runtime.preview")
HLS_SEGMENT_PATTERN = re.compile(r"^segment-\d{6}\.ts$")


class PreviewState(StrEnum):
    STARTING = "STARTING"
    READY = "READY"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"


class PreviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: int = Field(alias="cameraId", gt=0)
    source_url: SecretStr = Field(alias="sourceUrl")
    stream_type: str = Field(default="MAIN", alias="streamType", pattern="^(MAIN|SUB)$")


class PreviewSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    camera_id: int = Field(alias="cameraId")
    protocol: str = "HLS"
    state: PreviewState
    subscriber_count: int = Field(alias="subscriberCount", ge=0)
    diagnostic_id: str = Field(alias="diagnosticId")


class PreviewUnavailableError(RuntimeError):
    def __init__(self, error_code: str, diagnostic_id: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.diagnostic_id = diagnostic_id


class Process(Protocol):
    returncode: int | None

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[[list[str]], Awaitable[Process]]


@dataclass
class PreviewSession:
    session_id: str
    camera_id: int
    worker_key: tuple[int, str]
    worker: "StreamWorker"
    last_access_monotonic: float = field(default_factory=time.monotonic)


class StreamWorker:
    def __init__(
        self,
        camera_id: int,
        source_url: SecretStr,
        output_dir: Path,
        settings: RuntimeSettings,
        process_factory: ProcessFactory | None = None,
    ) -> None:
        self.camera_id = camera_id
        self.source_url = source_url
        self.output_dir = output_dir
        self.settings = settings
        self.diagnostic_id = str(uuid4())
        self.state = PreviewState.STARTING
        self.subscribers: set[str] = set()
        self._process_factory = process_factory or self._create_process
        self._process: Process | None = None
        self._runner: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._closing = False

    @property
    def playlist_path(self) -> Path:
        return self.output_dir / "index.m3u8"

    async def ensure_started(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run(), name=f"preview-camera-{self.camera_id}")
        try:
            await asyncio.wait_for(self._ready.wait(), self.settings.preview_startup_seconds)
        except TimeoutError as error:
            raise PreviewUnavailableError("PREVIEW_START_TIMEOUT", self.diagnostic_id) from error
        if self.state is not PreviewState.READY:
            raise PreviewUnavailableError("PREVIEW_STREAM_OPEN_FAILED", self.diagnostic_id)

    async def stop(self) -> None:
        self._closing = True
        await self._stop_process()
        if self._runner is not None:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
        await asyncio.to_thread(shutil.rmtree, self.output_dir, True)

    async def _run(self) -> None:
        retry_seconds = 0.5
        first_attempt = True
        while not self._closing:
            self.state = PreviewState.STARTING if first_attempt else PreviewState.RECONNECTING
            await asyncio.to_thread(self._reset_output_dir)
            try:
                self._process = await self._process_factory(self._build_ffmpeg_args())
                await self._wait_until_ready_or_exited()
                if self.playlist_path.is_file():
                    self.state = PreviewState.READY
                    self._ready.set()
                    retry_seconds = 0.5
                    await self._process.wait()
                    if not self._closing and self.subscribers:
                        self.state = PreviewState.RECONNECTING
                elif first_attempt:
                    self.state = PreviewState.FAILED
                    self._ready.set()
            except (FileNotFoundError, OSError):
                self.state = PreviewState.FAILED
                self._ready.set()
            finally:
                self._process = None
            if self._closing or not self.subscribers:
                return
            first_attempt = False
            await asyncio.sleep(retry_seconds)
            retry_seconds = min(retry_seconds * 2, 8.0)

    async def _wait_until_ready_or_exited(self) -> None:
        assert self._process is not None
        deadline = time.monotonic() + self.settings.preview_startup_seconds
        while time.monotonic() < deadline:
            if self.playlist_path.is_file():
                return
            if self._process.returncode is not None:
                return
            await asyncio.sleep(0.05)

    async def _stop_process(self) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()

    async def _create_process(self, args: list[str]) -> Process:
        return await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    def _build_ffmpeg_args(self) -> list[str]:
        source_url = self.source_url.get_secret_value()
        args = [self.settings.ffmpeg_binary, "-nostdin", "-hide_banner", "-loglevel", "error"]
        if source_url.lower().startswith("rtsp://"):
            args.extend(["-rtsp_transport", "tcp"])
        args.extend(
            [
                "-i",
                source_url,
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-tune",
                "zerolatency",
                "-g",
                "30",
                "-sc_threshold",
                "0",
                "-force_key_frames",
                f"expr:gte(t,n_forced*{self.settings.preview_hls_segment_seconds})",
                "-f",
                "hls",
                "-hls_time",
                str(self.settings.preview_hls_segment_seconds),
                "-hls_list_size",
                str(self.settings.preview_hls_list_size),
                "-hls_flags",
                "delete_segments+append_list+independent_segments",
                "-hls_segment_filename",
                str(self.output_dir / "segment-%06d.ts"),
                str(self.playlist_path),
            ]
        )
        return args

    def _reset_output_dir(self) -> None:
        shutil.rmtree(self.output_dir, ignore_errors=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


class PreviewManager:
    def __init__(
        self,
        settings: RuntimeSettings,
        worker_factory: Callable[[int, SecretStr, Path, RuntimeSettings], StreamWorker]
        | None = None,
    ) -> None:
        self.settings = settings
        self._worker_factory = worker_factory or StreamWorker
        self._workers: dict[tuple[int, str], StreamWorker] = {}
        self._sessions: dict[str, PreviewSession] = {}
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task[None] | None = None

    @property
    def active_stream_count(self) -> int:
        return len(self._workers)

    async def start(self) -> None:
        self.settings.preview_root.mkdir(parents=True, exist_ok=True)
        if self._reaper is None:
            self._reaper = asyncio.create_task(self._reap_idle_sessions(), name="preview-reaper")

    async def close(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper
            self._reaper = None
        async with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
            self._sessions.clear()
        await asyncio.gather(*(worker.stop() for worker in workers), return_exceptions=True)

    async def create_session(self, request: PreviewCreateRequest) -> PreviewSessionResponse:
        session_id = uuid4().hex
        worker_key = (request.camera_id, request.stream_type)
        async with self._lock:
            worker = self._workers.get(worker_key)
            if worker is None:
                worker = self._worker_factory(
                    request.camera_id,
                    request.source_url,
                    self.settings.preview_root
                    / f"camera-{request.camera_id}-{request.stream_type.lower()}",
                    self.settings,
                )
                self._workers[worker_key] = worker
            elif worker.source_url.get_secret_value() != request.source_url.get_secret_value():
                raise PreviewUnavailableError("PREVIEW_SOURCE_CHANGED", worker.diagnostic_id)
            worker.subscribers.add(session_id)
            self._sessions[session_id] = PreviewSession(
                session_id, request.camera_id, worker_key, worker
            )
        try:
            await worker.ensure_started()
        except PreviewUnavailableError:
            await self.release_session(session_id)
            raise
        return self._response(session_id, worker)

    async def get_session(self, session_id: str) -> PreviewSessionResponse:
        session = await self._require_session(session_id)
        session.last_access_monotonic = time.monotonic()
        return self._response(session_id, session.worker)

    async def get_media(self, session_id: str, file_name: str) -> tuple[Path, str]:
        if file_name != "index.m3u8" and HLS_SEGMENT_PATTERN.fullmatch(file_name) is None:
            raise FileNotFoundError(file_name)
        session = await self._require_session(session_id)
        session.last_access_monotonic = time.monotonic()
        path = session.worker.output_dir / file_name
        if not path.is_file():
            raise FileNotFoundError(file_name)
        return path, "application/vnd.apple.mpegurl" if file_name.endswith(
            ".m3u8"
        ) else "video/mp2t"

    async def release_session(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return
            worker = session.worker
            worker.subscribers.discard(session_id)
            should_stop = not worker.subscribers
            if should_stop:
                self._workers.pop(session.worker_key, None)
        if should_stop:
            await worker.stop()

    async def _require_session(self, session_id: str) -> PreviewSession:
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    async def _reap_idle_sessions(self) -> None:
        while True:
            await asyncio.sleep(min(5.0, self.settings.preview_idle_seconds / 2))
            deadline = time.monotonic() - self.settings.preview_idle_seconds
            async with self._lock:
                expired = [
                    session_id
                    for session_id, session in self._sessions.items()
                    if session.last_access_monotonic < deadline
                ]
            for session_id in expired:
                await self.release_session(session_id)

    @staticmethod
    def _response(session_id: str, worker: StreamWorker) -> PreviewSessionResponse:
        return PreviewSessionResponse(
            sessionId=session_id,
            cameraId=worker.camera_id,
            state=worker.state,
            subscriberCount=len(worker.subscribers),
            diagnosticId=worker.diagnostic_id,
        )
