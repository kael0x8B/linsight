"""Rockchip MPP/RGA capture adapter fed from the shared encoded camera timeline."""

from __future__ import annotations

import asyncio
import contextlib
import platform
import struct
import subprocess
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.model.environment import model_environment
from ai_runtime.app.stream.frame_stamp import h264_frame_key
from ai_runtime.app.stream.frames import CapturedFrame

PACKET_HEADER = struct.Struct(">4sIqqqB")
FRAME_HEADER = struct.Struct(">4sIq")
PACKET_MAGIC = b"LPKT"
FRAME_MAGIC = b"LFRM"
MAX_FRAME_BYTES = 32 * 1024 * 1024
BACKEND = "ROCKCHIP_MPP_RGA"


class RockchipDecodeError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwarePacket:
    data: bytes
    pts: int
    dts: int
    timestamp_millis: int
    keyframe: bool
    extradata: bytes | None
    width: int
    height: int
    source_fps: Fraction | None = None


@dataclass(frozen=True)
class _FrameMetadata:
    timestamp_millis: int
    offered_monotonic: float
    frame_key: str


def helper_path() -> Path:
    return Path(__file__).with_name("rockchip_gst_helper.py")


def probe(settings: RuntimeSettings) -> bool:
    if not settings.rockchip_hardware_decode:
        return False
    if platform.system() != "Linux" or platform.machine().lower() not in {"aarch64", "arm64"}:
        return False
    python = settings.rockchip_gstreamer_python
    if not python.is_file() or not helper_path().is_file():
        return False
    try:
        result = subprocess.run(  # noqa: S603 - fixed local interpreter and bundled helper
            [str(python), str(helper_path()), "--probe"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == BACKEND


def scaled_size(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return 0, 0
    ratio = min(1.0, max_width / width, max_height / height)
    # MPP/RGA handles even dimensions most reliably for YUV-backed frames.
    return max(2, int(width * ratio) // 2 * 2), max(2, int(height * ratio) // 2 * 2)


def capture_size(settings: RuntimeSettings, width: int, height: int) -> tuple[int, int]:
    max_width, max_height = (
        settings.rockchip_capture_max_width,
        settings.rockchip_capture_max_height,
    )
    if max_width is None or max_height is None:
        targets = model_environment().rknn_targets
        # Detection adapters still resize to the model's fixed input. Keep the
        # sampled source pixels so plate rectification/OCR can crop the 4K image.
        # Match a proven SoC, not a generic ARM64 CPU or arbitrary future board.
        native_4k = bool({"rk3588", "rk3588s"}.intersection(targets))
        default_width, default_height = (3840, 2160) if native_4k else (1920, 1080)
        max_width = default_width if max_width is None else max_width
        max_height = default_height if max_height is None else max_height
    return scaled_size(width, height, max_width, max_height)


def _avcc_parameter_sets(extradata: bytes | None) -> tuple[bytes, int]:
    if not extradata:
        return b"", 4
    if extradata.startswith((b"\x00\x00\x00\x01", b"\x00\x00\x01")):
        return extradata, 4
    if len(extradata) < 7 or extradata[0] != 1:
        return b"", 4
    nal_length_size = (extradata[4] & 3) + 1
    position = 6
    output = bytearray()
    try:
        for _ in range(extradata[5] & 31):
            length = int.from_bytes(extradata[position : position + 2], "big")
            position += 2
            output.extend(b"\x00\x00\x00\x01")
            output.extend(extradata[position : position + length])
            position += length
        count = extradata[position]
        position += 1
        for _ in range(count):
            length = int.from_bytes(extradata[position : position + 2], "big")
            position += 2
            output.extend(b"\x00\x00\x00\x01")
            output.extend(extradata[position : position + length])
            position += length
    except (IndexError, ValueError):
        return b"", nal_length_size
    return bytes(output), nal_length_size


def annex_b(data: bytes, extradata: bytes | None, keyframe: bool) -> bytes:
    parameter_sets, nal_length_size = _avcc_parameter_sets(extradata)
    if data.startswith((b"\x00\x00\x00\x01", b"\x00\x00\x01")):
        converted = data
    else:
        converted_parts: list[bytes] = []
        position = 0
        while position + nal_length_size <= len(data):
            length = int.from_bytes(data[position : position + nal_length_size], "big")
            position += nal_length_size
            if length <= 0 or position + length > len(data):
                converted_parts = []
                break
            converted_parts.extend((b"\x00\x00\x00\x01", data[position : position + length]))
            position += length
        converted = b"".join(converted_parts) if position == len(data) else data
    return parameter_sets + converted if keyframe and parameter_sets else converted


class RockchipMppDecoder:
    def __init__(
        self,
        settings: RuntimeSettings,
        packet: HardwarePacket,
        stream_id: str,
        publish: Callable[[CapturedFrame], None],
    ) -> None:
        self.settings = settings
        self.stream_id = stream_id
        self.publish = publish
        self.width, self.height = capture_size(settings, packet.width, packet.height)
        source_fps = packet.source_fps
        self.source_fps = (
            Fraction(source_fps).limit_denominator(1000)
            if source_fps is not None and 0 < source_fps <= 120
            else None
        )
        # FFmpeg estimates non-integer rates when the camera omits SPS timing.
        # Use the nearby nominal rate as the GStreamer caps hint; packet PTS
        # still carries the actual presentation timing.
        if self.source_fps is not None:
            nominal_fps = round(self.source_fps)
            if nominal_fps > 0 and abs(self.source_fps - nominal_fps) <= Fraction(1, 10):
                self.source_fps = Fraction(nominal_fps, 1)
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._stderr: asyncio.Task | None = None
        self._metadata: OrderedDict[int, _FrameMetadata] = OrderedDict()
        self._failure: BaseException | None = None
        self._closing = False
        self._next_output_pts: float | None = None
        self.stderr_tail: list[str] = []

    async def start(self) -> None:
        fps = Fraction(self.settings.task_capture_fps).limit_denominator(1000)
        source_rate_args = (
            ["--source-fps", f"{self.source_fps.numerator}/{self.source_fps.denominator}"]
            if self.source_fps is not None
            else []
        )
        self._process = await asyncio.create_subprocess_exec(
            str(self.settings.rockchip_gstreamer_python),
            str(helper_path()),
            "--width",
            str(self.width),
            "--height",
            str(self.height),
            "--fps",
            f"{fps.numerator}/{fps.denominator}",
            *source_rate_args,
            "--jpeg-quality",
            "95",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader = asyncio.create_task(self._read_frames(), name="rockchip-mpp-frames")
        self._stderr = asyncio.create_task(self._read_stderr(), name="rockchip-mpp-diagnostics")

    async def offer(self, packet: HardwarePacket) -> None:
        if self._failure is not None:
            raise RockchipDecodeError("Rockchip decoder stopped") from self._failure
        if self._process is None or self._process.stdin is None:
            raise RockchipDecodeError("Rockchip decoder is not running")
        if self._process.returncode is not None:
            raise RockchipDecodeError("Rockchip decoder exited")
        payload = annex_b(packet.data, packet.extradata, packet.keyframe)
        self._metadata[packet.pts] = _FrameMetadata(
            packet.timestamp_millis, time.monotonic(), h264_frame_key(packet.data)
        )
        while len(self._metadata) > 512:
            self._metadata.popitem(last=False)
        self._process.stdin.write(
            PACKET_HEADER.pack(
                PACKET_MAGIC,
                len(payload),
                packet.pts,
                packet.dts,
                packet.timestamp_millis,
                int(packet.keyframe),
            )
            + payload
        )
        try:
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as error:
            raise RockchipDecodeError("Rockchip decoder pipe closed") from error

    def _frame_metadata(self, pts: int) -> _FrameMetadata | None:
        if value := self._metadata.get(pts):
            return value
        if not self._metadata:
            return None
        nearest = min(self._metadata, key=lambda value: abs(value - pts))
        return self._metadata[nearest] if abs(nearest - pts) <= 9_000 else None

    async def _read_frames(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                header = await self._process.stdout.readexactly(FRAME_HEADER.size)
                magic, length, pts = FRAME_HEADER.unpack(header)
                if magic != FRAME_MAGIC or length > MAX_FRAME_BYTES:
                    raise RockchipDecodeError("invalid Rockchip frame envelope")
                data = await self._process.stdout.readexactly(length)
                if self._next_output_pts is not None and pts < self._next_output_pts:
                    continue
                self._next_output_pts = max(
                    (self._next_output_pts or pts) + 90_000 / self.settings.task_capture_fps,
                    pts + 1,
                )
                metadata = self._frame_metadata(pts)
                timestamp = metadata.timestamp_millis if metadata else time.time_ns() // 1_000_000
                self.publish(
                    CapturedFrame(
                        data,
                        timestamp,
                        self.stream_id,
                        pts,
                        (time.monotonic() - metadata.offered_monotonic) * 1000
                        if metadata
                        else None,
                        None,
                        metadata.frame_key if metadata else None,
                    )
                )
        except asyncio.IncompleteReadError as error:
            if not self._closing:
                self._failure = error
        except (OSError, ValueError, RockchipDecodeError) as error:
            if not self._closing:
                self._failure = error

    async def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        while line := await self._process.stderr.readline():
            value = line.decode("utf-8", errors="replace").strip()
            if value:
                self.stderr_tail.append(value[:500])
                del self.stderr_tail[:-20]

    async def close(self) -> None:
        self._closing = True
        process = self._process
        if process is not None and process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await process.stdin.wait_closed()
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), 3)
            except TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 2)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        for task in (self._reader, self._stderr):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._reader, self._stderr) if task is not None),
            return_exceptions=True,
        )
        self._process = None
