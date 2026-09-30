import asyncio
import json
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

from .contracts import (
    ProbeStageName,
    ProbeStageResult,
    ProbeStageStatus,
    StreamProbeRequest,
    StreamProbeResult,
    VideoStreamInfo,
)


@dataclass(frozen=True)
class ProcessResult:
    return_code: int
    stdout: bytes
    stderr: bytes


Resolver = Callable[[str, int], Awaitable[None]]
Connector = Callable[[str, int], Awaitable[None]]
ProcessRunner = Callable[[list[str], float], Awaitable[ProcessResult]]


class StreamProbeService:
    def __init__(
        self,
        ffprobe_binary: str = "ffprobe",
        resolver: Resolver | None = None,
        connector: Connector | None = None,
        process_runner: ProcessRunner | None = None,
    ) -> None:
        self._ffprobe_binary = ffprobe_binary
        self._resolver = resolver or self._resolve
        self._connector = connector or self._connect
        self._process_runner = process_runner or self._run_process

    async def probe(self, request: StreamProbeRequest) -> StreamProbeResult:
        stages: list[ProbeStageResult] = []
        diagnostic_id = str(uuid4())

        failure = await self._run_stage(
            stages,
            ProbeStageName.DNS,
            lambda: self._resolver(request.host.strip("[]"), request.port),
            min(3.0, request.timeout_seconds),
            "域名或地址解析成功",
            "DNS_RESOLUTION_FAILED",
            "无法解析设备地址",
        )
        if failure:
            return self._failed(request, diagnostic_id, stages, *failure)

        failure = await self._run_stage(
            stages,
            ProbeStageName.TCP,
            lambda: self._connector(request.host.strip("[]"), request.port),
            min(3.0, request.timeout_seconds),
            "设备端口可连接",
            "TCP_CONNECT_FAILED",
            "无法连接设备端口",
        )
        if failure:
            return self._failed(request, diagnostic_id, stages, *failure)

        started = time.monotonic()
        try:
            process = await self._process_runner(
                self._build_ffprobe_args(request), request.timeout_seconds
            )
        except TimeoutError:
            stages.append(
                self._stage(ProbeStageName.AUTH, ProbeStageStatus.FAILED, started, "设备响应超时")
            )
            return self._failed(request, diagnostic_id, stages, "STREAM_TIMEOUT", "取流检测超时")
        except (FileNotFoundError, OSError):
            stages.append(
                self._stage(ProbeStageName.AUTH, ProbeStageStatus.FAILED, started, "检测组件不可用")
            )
            return self._failed(
                request, diagnostic_id, stages, "PROBE_UNAVAILABLE", "节点检测组件不可用"
            )

        if process.return_code != 0:
            auth_failed = self._is_auth_failure(process.stderr)
            failed_stage = ProbeStageName.AUTH if auth_failed else ProbeStageName.STREAM
            stages.append(
                self._stage(
                    failed_stage,
                    ProbeStageStatus.FAILED,
                    started,
                    "设备认证失败" if auth_failed else "设备未返回可用视频流",
                )
            )
            return self._failed(
                request,
                diagnostic_id,
                stages,
                "AUTH_FAILED" if auth_failed else "STREAM_OPEN_FAILED",
                "设备认证失败" if auth_failed else "无法打开视频流",
            )

        stages.append(
            self._stage(ProbeStageName.AUTH, ProbeStageStatus.SUCCESS, started, "设备认证通过")
        )
        try:
            payload = json.loads(process.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError):
            stages.append(
                self._stage(
                    ProbeStageName.STREAM, ProbeStageStatus.FAILED, started, "视频元数据不可解析"
                )
            )
            return self._failed(
                request, diagnostic_id, stages, "PROBE_OUTPUT_INVALID", "视频检测结果无效"
            )

        video_stream = self._first_video_stream(payload)
        if video_stream is None:
            stages.append(
                self._stage(
                    ProbeStageName.STREAM, ProbeStageStatus.FAILED, started, "未发现视频轨道"
                )
            )
            return self._failed(
                request, diagnostic_id, stages, "VIDEO_STREAM_MISSING", "未发现视频轨道"
            )
        if (video_stream.get("codec_name") or "").lower() != "h264":
            stages.append(
                self._stage(
                    ProbeStageName.STREAM,
                    ProbeStageStatus.FAILED,
                    started,
                    "视频编码不是 H.264",
                )
            )
            return self._failed(
                request,
                diagnostic_id,
                stages,
                "UNSUPPORTED_VIDEO_CODEC",
                "视频编码不是 H.264，请将摄像头主、子码流均设置为 H.264",
            )
        stages.append(
            self._stage(ProbeStageName.STREAM, ProbeStageStatus.SUCCESS, started, "视频轨道可读取")
        )

        has_keyframe = any(frame.get("key_frame") == 1 for frame in payload.get("frames", []))
        if not has_keyframe:
            stages.append(
                self._stage(
                    ProbeStageName.KEYFRAME,
                    ProbeStageStatus.FAILED,
                    started,
                    "检测窗口内未收到关键帧",
                )
            )
            return self._failed(
                request, diagnostic_id, stages, "KEYFRAME_TIMEOUT", "检测窗口内未收到关键帧"
            )
        stages.append(
            self._stage(ProbeStageName.KEYFRAME, ProbeStageStatus.SUCCESS, started, "已收到关键帧")
        )

        return StreamProbeResult(
            camera_id=request.camera_id,
            online=True,
            checked_at=datetime.now(UTC),
            diagnostic_id=diagnostic_id,
            stages=stages,
            stream=VideoStreamInfo(
                codec=video_stream.get("codec_name"),
                width=video_stream.get("width"),
                height=video_stream.get("height"),
                average_frame_rate=video_stream.get("avg_frame_rate"),
            ),
        )

    async def _run_stage(
        self,
        stages: list[ProbeStageResult],
        name: ProbeStageName,
        operation: Callable[[], Awaitable[None]],
        stage_limit_seconds: float,
        success_message: str,
        error_code: str,
        error_message: str,
    ) -> tuple[str, str] | None:
        started = time.monotonic()
        try:
            await asyncio.wait_for(operation(), timeout=stage_limit_seconds)
        except (TimeoutError, OSError, socket.gaierror):
            stages.append(self._stage(name, ProbeStageStatus.FAILED, started, error_message))
            return error_code, error_message
        stages.append(self._stage(name, ProbeStageStatus.SUCCESS, started, success_message))
        return None

    @staticmethod
    async def _resolve(host: str, port: int) -> None:
        loop = asyncio.get_running_loop()
        await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)

    @staticmethod
    async def _connect(host: str, port: int) -> None:
        _reader, writer = await asyncio.open_connection(host, port)
        writer.close()
        await writer.wait_closed()

    @staticmethod
    async def _run_process(args: list[str], process_limit_seconds: float) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=process_limit_seconds
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise
        return ProcessResult(process.returncode or 0, stdout, stderr)

    def _build_ffprobe_args(self, request: StreamProbeRequest) -> list[str]:
        return [
            self._ffprobe_binary,
            "-v",
            "error",
            "-rtsp_transport",
            "tcp",
            "-read_intervals",
            "%+5",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,avg_frame_rate:frame=key_frame",
            "-show_streams",
            "-show_frames",
            "-of",
            "json",
            self._build_rtsp_url(request),
        ]

    @staticmethod
    def _build_rtsp_url(request: StreamProbeRequest) -> str:
        raw_uri = request.stream_uri.get_secret_value().strip()
        parsed = urlsplit(
            raw_uri if "://" in raw_uri else f"rtsp://placeholder/{raw_uri.lstrip('/')}"
        )
        host = request.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        username = request.username.get_secret_value() if request.username else None
        password = request.password.get_secret_value() if request.password else None
        user_info = ""
        if username:
            user_info = quote(username, safe="")
            if password is not None:
                user_info += f":{quote(password, safe='')}"
            user_info += "@"
        return urlunsplit(
            ("rtsp", f"{user_info}{host}:{request.port}", parsed.path, parsed.query, "")
        )

    @staticmethod
    def _first_video_stream(payload: dict[str, Any]) -> dict[str, Any] | None:
        return next(
            (
                stream
                for stream in payload.get("streams", [])
                if stream.get("codec_type") in (None, "video")
            ),
            None,
        )

    @staticmethod
    def _is_auth_failure(stderr: bytes) -> bool:
        lowered = stderr.decode("utf-8", errors="ignore").lower()
        return any(marker in lowered for marker in ("401", "403", "unauthorized", "forbidden"))

    @staticmethod
    def _stage(
        name: ProbeStageName,
        status: ProbeStageStatus,
        started: float,
        message: str,
    ) -> ProbeStageResult:
        return ProbeStageResult(
            name=name,
            status=status,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            message=message,
        )

    @staticmethod
    def _failed(
        request: StreamProbeRequest,
        diagnostic_id: str,
        stages: list[ProbeStageResult],
        error_code: str,
        error_message: str,
    ) -> StreamProbeResult:
        attempted = {stage.name for stage in stages}
        for name in ProbeStageName:
            if name not in attempted:
                stages.append(
                    ProbeStageResult(
                        name=name,
                        status=ProbeStageStatus.SKIPPED,
                        duration_ms=0,
                        message="前置阶段未通过",
                    )
                )
        return StreamProbeResult(
            camera_id=request.camera_id,
            online=False,
            checked_at=datetime.now(UTC),
            diagnostic_id=diagnostic_id,
            error_code=error_code,
            error_message=error_message,
            stages=stages,
        )
