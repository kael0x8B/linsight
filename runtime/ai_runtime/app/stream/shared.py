"""One encoded camera source and one optional decoder shared by preview and AI."""

import asyncio
import contextlib
import io
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4
from weakref import WeakSet

import av
from aiortc.mediastreams import MediaStreamError, VideoStreamTrack
from pydantic import SecretStr

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.stream.frame_stamp import h264_frame_key, stamp_h264
from ai_runtime.app.stream.frames import CapturedFrame
from ai_runtime.app.stream.rockchip import (
    BACKEND as ROCKCHIP_BACKEND,
)
from ai_runtime.app.stream.rockchip import (
    HardwarePacket,
    RockchipDecodeError,
    RockchipMppDecoder,
)
from ai_runtime.app.stream.rockchip import (
    probe as probe_rockchip,
)

TIME_BASE = Fraction(1, 90_000)
LOGGER = logging.getLogger("linsight.stream.shared")
_HARDWARE_RETRY_SECONDS = 30.0


@dataclass(frozen=True)
class DecodePacket:
    data: bytes
    pts: int
    dts: int
    timestamp_millis: int
    stream_id: str
    generation: tuple[int, int]
    keyframe: bool
    extradata: bytes | None
    width: int
    height: int
    codec_name: str = "h264"
    source_fps: Fraction | None = None


@dataclass(frozen=True)
class StopDecode:
    completed: asyncio.Future[None]


class UnsupportedTimelineCodec(ValueError):
    pass


class PacketReader:
    """Demux encoded camera packets without aiortc's H.264/VP8 codec filter."""

    def __init__(self, url: str, timeout: float) -> None:
        self._container = av.open(
            url,
            options={"rtsp_transport": "tcp", "fflags": "nobuffer", "flags": "low_delay"},
            timeout=timeout,
        )
        self._stream = next(
            (stream for stream in self._container.streams if stream.type == "video"), None
        )
        self._packets = iter(self._container.demux(self._stream)) if self._stream else None
        self._throttle = not url.lower().startswith("rtsp://")
        self._first_pts: int | None = None
        self._first_monotonic: float | None = None
        self._stopped = False
        self.video = self if self._stream else None
        self.audio = None

    async def recv(self) -> av.Packet:
        if self._stopped or self._packets is None:
            raise MediaStreamError
        while True:
            reading = asyncio.create_task(asyncio.to_thread(next, self._packets, None))
            try:
                packet = await asyncio.shield(reading)
            except asyncio.CancelledError:
                # av.demux must finish before its container is closed below.
                with contextlib.suppress(Exception):
                    await reading
                raise
            if packet is None:
                raise MediaStreamError
            if packet.pts is None:
                continue
            if self._throttle:
                now = time.monotonic()
                if self._first_pts is None:
                    self._first_pts = packet.pts
                    self._first_monotonic = now
                assert self._first_monotonic is not None
                delay = (
                    self._first_monotonic
                    + float((packet.pts - self._first_pts) * packet.time_base)
                    - now
                )
                if 0 < delay < 5:
                    await asyncio.sleep(delay)
            return packet

    def stop(self) -> None:
        self._stopped = True
        self._container.close()


class PacketTrack(VideoStreamTrack):
    def __init__(self, source: "CameraSource") -> None:
        super().__init__()
        self.source = source
        self.queue: asyncio.Queue[av.Packet | None] = asyncio.Queue(maxsize=30)
        self.wait_keyframe = True
        self.overruns = 0
        self.delivered = 0
        self.source.packet_tracks.add(self)

    def offer(self, packet: av.Packet, keyframe: bool) -> None:
        if self.queue.full():
            # Dropping arbitrary inter frames leaves a broken prediction chain.
            self.overruns += 1
            while not self.queue.empty():
                self.queue.get_nowait()
            self.wait_keyframe = True
        if self.wait_keyframe and not keyframe:
            return
        self.wait_keyframe = False
        self.queue.put_nowait(packet)

    async def recv(self) -> av.Packet:
        if self.readyState != "live":
            raise MediaStreamError
        packet = await self.queue.get()
        if packet is None:
            raise MediaStreamError
        self.delivered += 1
        return packet

    def reset(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()
        self.wait_keyframe = True

    def stop(self) -> None:
        if self.readyState == "live":
            super().stop()
            self.source.packet_tracks.discard(self)
            self.reset()
            self.queue.put_nowait(None)


class SharedPreviewPlayer:
    """A preview owner; each peer has a bounded encoded-packet subscription."""

    def __init__(self, hub: "CameraMediaHub", source: "CameraSource") -> None:
        self.hub = hub
        self.source = source
        self.video = self
        self.audio = None
        self._stopped = False
        self._tracks: WeakSet[PacketTrack] = WeakSet()
        source.preview_owners += 1

    def subscribe(self) -> PacketTrack:
        track = PacketTrack(self.source)
        self._tracks.add(track)
        return track

    def stop(self) -> None:
        if not self._stopped:
            self._stopped = True
            for track in self._tracks:
                track.stop()
            self._tracks.clear()
            self.source.preview_owners -= 1
            self.hub.schedule_release(self.source)


class CameraSource:
    def __init__(self, camera_id: int, url: SecretStr, settings: RuntimeSettings) -> None:
        self.camera_id = camera_id
        self.url = url
        self.settings = settings
        self.packet_tracks: set[PacketTrack] = set()
        self.capture_callbacks: set[Callable[[CapturedFrame], None]] = set()
        self.capture_reservations = 0
        self.preview_owners = 0
        self.reconnects = 0
        self._ready = asyncio.Event()
        self.capture_ready = asyncio.Event()
        self._closing = False
        self._runner: asyncio.Task | None = None
        self._decode_worker: asyncio.Task | None = None
        self._decode_queue: asyncio.Queue[DecodePacket | StopDecode] = asyncio.Queue(maxsize=30)
        self._decode_wait_keyframe = True
        self._decode_epoch = 0
        self._player: PacketReader | None = None
        self._decoder = None
        self._hevc_encoder = None
        self._next_preview_pts: float | None = None
        self._codec_name: str | None = None
        self._next_sample_pts: float | None = None
        self._stream_id = str(uuid4())
        self._last_transport_pts = -3600
        self._transport_offset: int | None = None
        self._last_packet_monotonic: float | None = None
        self._error: str | None = None
        self._unsupported_codec = False
        self._ingress_packets = 0
        self._last_ingress_report = time.monotonic()
        self._last_reported_packets = 0
        self.capture_generation = 0
        self._decoder_generation: tuple[str, int, int] | None = None
        self.decode_backend = "PENDING"
        self.hardware_decode_failures = 0
        self.decode_queue_overruns = 0
        self.hevc_transcode_failures = 0

    async def start(self) -> None:
        if self._runner is None:
            self._decode_worker = asyncio.create_task(
                self._decode_loop(), name=f"camera-decode-{self.camera_id}"
            )
            self._runner = asyncio.create_task(self._run(), name=f"camera-media-{self.camera_id}")
        await asyncio.wait_for(self._ready.wait(), self.settings.task_startup_seconds)
        if self._unsupported_codec:
            raise UnsupportedTimelineCodec(
                "摄像头视频编码不是 H.264，请将主、子码流均设置为 H.264"
            )
        if self._error is not None:
            raise RuntimeError("camera shared media source unavailable")

    async def close(self) -> None:
        self._closing = True
        if self._runner is not None:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
        if self._decode_worker is not None:
            self._decode_worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._decode_worker
        self._reset_decode_queue()
        for track in tuple(self.packet_tracks):
            track.stop()

    async def _run(self) -> None:
        delay = 0.5
        while not self._closing:
            try:
                opening = asyncio.create_task(
                    asyncio.to_thread(
                        PacketReader,
                        self.url.get_secret_value(),
                        self.settings.preview_startup_seconds,
                    )
                )
                try:
                    self._player = await asyncio.shield(opening)
                except asyncio.CancelledError:
                    # A source may disappear while cancellation waits for av.open.
                    # Preserve cancellation even if that outstanding open fails.
                    with contextlib.suppress(OSError, ValueError, av.FFmpegError):
                        self._player = await opening  # finally closes a late-opened source.
                    raise
                if self._player.video is None:
                    raise UnsupportedTimelineCodec("shared video timeline has no video track")
                self._stream_id = str(uuid4())
                self._codec_name = None
                self._reset_decode_queue()
                self._transport_offset = None
                for track in tuple(self.packet_tracks):
                    track.reset()
                while not self._closing:
                    packet = await self._player.video.recv()
                    if not isinstance(packet, av.Packet) or packet.pts is None:
                        continue
                    codec_name = packet.stream.codec_context.name
                    if codec_name != "h264":
                        raise UnsupportedTimelineCodec(
                            "shared video timeline requires H.264"
                        )
                    self._codec_name = codec_name
                    self._error = None
                    self._ready.set()
                    self._ingress_packets += 1
                    self._report_ingress_if_due()
                    source_pts = int(packet.pts * packet.time_base / TIME_BASE)
                    if source_pts < 0:
                        continue
                    timestamp_millis = time.time_ns() // 1_000_000
                    outbound = av.Packet(
                        stamp_h264(
                            bytes(packet),
                            self._stream_id,
                            source_pts,
                            h264_frame_key(bytes(packet)),
                        )
                    )
                    # Preserve source PTS in the SEI; keep RTP monotonic across reconnects.
                    outbound.pts = self._transport_timestamp(source_pts, time.monotonic())
                    outbound.time_base = TIME_BASE
                    for track in tuple(self.packet_tracks):
                        track.offer(outbound, packet.is_keyframe)
                    if self.capture_callbacks:
                        self._offer_decode(packet, source_pts, timestamp_millis)
                    delay = 0.5
            except asyncio.CancelledError:
                raise
            except UnsupportedTimelineCodec:
                self._unsupported_codec = True
                self._ready.set()
                return
            except (OSError, ValueError, MediaStreamError, av.FFmpegError) as error:
                self._error = type(error).__name__
                self._ready.set()
                self.reconnects += 1
            finally:
                if self._player is not None:
                    await asyncio.to_thread(self._player.stop)
                    self._player = None
            if not self._closing:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8)

    def _report_ingress_if_due(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_ingress_report
        if elapsed < 30:
            return
        packets = self._ingress_packets - self._last_reported_packets
        LOGGER.warning(
            "Camera ingress cameraId=%s packetFps=%.2f previewTracks=%s "
            "trackOverruns=%s trackDelivered=%s",
            self.camera_id,
            packets / elapsed,
            len(self.packet_tracks),
            [track.overruns for track in self.packet_tracks],
            [track.delivered for track in self.packet_tracks],
        )
        self._last_ingress_report = now
        self._last_reported_packets = self._ingress_packets

    def _transport_timestamp(self, source_pts: int, arrival: float) -> int:
        if self._transport_offset is None:
            gap = (
                3600
                if self._last_packet_monotonic is None
                else max(3600, round((arrival - self._last_packet_monotonic) * 90_000))
            )
            self._transport_offset = self._last_transport_pts + gap - source_pts
        result = source_pts + self._transport_offset
        self._last_transport_pts = max(self._last_transport_pts, result)
        self._last_packet_monotonic = arrival
        return result

    def _reset_decode_queue(self) -> None:
        controls = []
        while not self._decode_queue.empty():
            item = self._decode_queue.get_nowait()
            if isinstance(item, StopDecode):
                controls.append(item)
        for item in controls:
            self._decode_queue.put_nowait(item)
        self._decode_wait_keyframe = True
        self._decode_epoch += 1

    async def deactivate_capture(self, callback: Callable[[CapturedFrame], None]) -> None:
        self.capture_callbacks.discard(callback)
        if (
            self.capture_callbacks
            or self._decode_worker is None
            or self._decode_worker.done()
        ):
            return
        self.capture_generation += 1
        self._reset_decode_queue()
        completed = asyncio.get_running_loop().create_future()
        self._decode_queue.put_nowait(StopDecode(completed))
        await asyncio.wait_for(asyncio.shield(completed), 6)

    def _offer_decode(self, packet: av.Packet, pts: int, timestamp_millis: int) -> None:
        if self._decode_queue.full():
            # Preserve H.264 prediction chains after overload; catch up on a keyframe
            # without ever delaying the independent encoded preview subscribers.
            self.decode_queue_overruns += 1
            if self.decode_queue_overruns == 1 or self.decode_queue_overruns % 10 == 0:
                LOGGER.warning(
                    "Camera decode queue overrun cameraId=%s count=%s; "
                    "waiting for next keyframe",
                    self.camera_id,
                    self.decode_queue_overruns,
                )
            self._reset_decode_queue()
        if self._decode_wait_keyframe and not packet.is_keyframe:
            return
        self._decode_wait_keyframe = False
        self._decode_queue.put_nowait(
            DecodePacket(
                bytes(packet),
                pts,
                int(packet.dts * packet.time_base / TIME_BASE) if packet.dts is not None else -1,
                timestamp_millis,
                self._stream_id,
                (self.capture_generation, self._decode_epoch),
                packet.is_keyframe,
                packet.stream.codec_context.extradata,
                packet.stream.codec_context.width,
                packet.stream.codec_context.height,
                packet.stream.codec_context.name,
                None
                if packet.stream.average_rate
                else packet.stream.base_rate or packet.stream.guessed_rate,
            )
        )

    async def _decode_loop(self) -> None:
        hardware_allowed = await asyncio.to_thread(probe_rockchip, self.settings)
        hardware_retry_at = 0.0
        hardware: RockchipMppDecoder | None = None
        hardware_generation: tuple[str, int, int] | None = None
        try:
            while True:
                packet = await self._decode_queue.get()
                if isinstance(packet, StopDecode):
                    if hardware is not None:
                        await hardware.close()
                        hardware = None
                        hardware_generation = None
                    self._decoder = None
                    self._hevc_encoder = None
                    self._decoder_generation = None
                    self._next_sample_pts = None
                    self._next_preview_pts = None
                    self.decode_backend = "PENDING"
                    self.capture_ready.clear()
                    if not packet.completed.done():
                        packet.completed.set_result(None)
                    continue
                if (
                    not (
                        self.capture_callbacks
                        or (packet.codec_name == "hevc" and self.packet_tracks)
                    )
                    or packet.stream_id != self._stream_id
                    or packet.generation != (self.capture_generation, self._decode_epoch)
                ):
                    continue
                if packet.codec_name == "hevc":
                    # One packet decoder feeds both sampled analysis and bounded
                    # H.264 preview, so enabling preview never opens a second RTSP pull.
                    self.decode_backend = "SOFTWARE_PYAV_HEVC"
                    fresh = self._decode_queue.qsize() <= 2 and (
                        time.time_ns() // 1_000_000 - packet.timestamp_millis <= 250
                    )
                    decoding = asyncio.create_task(
                        asyncio.to_thread(
                            self._decode_hevc,
                            packet,
                            fresh and bool(self.packet_tracks),
                            fresh and bool(self.capture_callbacks),
                        )
                    )
                    try:
                        encoded, captures = await asyncio.shield(decoding)
                    except asyncio.CancelledError:
                        with contextlib.suppress(Exception):
                            await decoding
                        raise
                    except (OSError, ValueError, av.error.FFmpegError) as error:
                        self.hevc_transcode_failures += 1
                        if (
                            self.hevc_transcode_failures == 1
                            or (self.hevc_transcode_failures & (self.hevc_transcode_failures - 1))
                            == 0
                        ):
                            LOGGER.warning(
                                "HEVC preview processing failed cameraId=%s errorType=%s "
                                "failures=%s",
                                self.camera_id,
                                type(error).__name__,
                                self.hevc_transcode_failures,
                            )
                        self._reset_decode_queue()
                        continue
                    if packet.stream_id != self._stream_id or packet.generation != (
                        self.capture_generation,
                        self._decode_epoch,
                    ):
                        continue
                    for data, pts, keyframe, frame_key in encoded:
                        outbound = av.Packet(stamp_h264(data, packet.stream_id, pts, frame_key))
                        outbound.pts = self._transport_timestamp(pts, time.monotonic())
                        outbound.time_base = TIME_BASE
                        for track in tuple(self.packet_tracks):
                            track.offer(outbound, keyframe)
                    for frame in captures:
                        for callback in tuple(self.capture_callbacks):
                            callback(frame)
                        self.capture_ready.set()
                    continue
                generation = (packet.stream_id, *packet.generation)
                if hardware is not None and hardware_generation != generation:
                    await hardware.close()
                    hardware = None
                # A decoder helper can fail during a camera/driver interruption.
                # PyAV keeps the stream alive while a later keyframe gives MPP a
                # clean restart point; do not strand this camera on CPU forever.
                if (
                    not hardware_allowed
                    and packet.keyframe
                    and time.monotonic() >= hardware_retry_at
                ):
                    hardware_allowed = await asyncio.to_thread(probe_rockchip, self.settings)
                    hardware_retry_at = time.monotonic() + _HARDWARE_RETRY_SECONDS
                    if hardware_allowed:
                        self._decoder = None
                        self._decoder_generation = None
                        self._next_sample_pts = None
                if hardware_allowed:
                    if hardware is None:
                        if not packet.keyframe:
                            continue
                        hardware = RockchipMppDecoder(
                            self.settings,
                            HardwarePacket(
                                packet.data,
                                packet.pts,
                                packet.dts,
                                packet.timestamp_millis,
                                packet.keyframe,
                                packet.extradata,
                                packet.width,
                                packet.height,
                                packet.source_fps,
                            ),
                            packet.stream_id,
                            self._publish_hardware_frame,
                        )
                        try:
                            await hardware.start()
                        except (OSError, ValueError) as error:
                            self.hardware_decode_failures += 1
                            hardware_allowed = False
                            hardware_retry_at = time.monotonic() + _HARDWARE_RETRY_SECONDS
                            self.decode_backend = "SOFTWARE_PYAV_FALLBACK"
                            LOGGER.warning(
                                "Rockchip decode unavailable cameraId=%s errorType=%s; "
                                "falling back to PyAV",
                                self.camera_id,
                                type(error).__name__,
                            )
                            await hardware.close()
                            hardware = None
                            self._reset_decode_queue()
                            continue
                        hardware_generation = generation
                    try:
                        await hardware.offer(
                            HardwarePacket(
                                packet.data,
                                packet.pts,
                                packet.dts,
                                packet.timestamp_millis,
                                packet.keyframe,
                                packet.extradata,
                                packet.width,
                                packet.height,
                                packet.source_fps,
                            )
                        )
                        self.decode_backend = ROCKCHIP_BACKEND
                        continue
                    except (OSError, ValueError, RockchipDecodeError) as error:
                        self.hardware_decode_failures += 1
                        hardware_allowed = False
                        hardware_retry_at = time.monotonic() + _HARDWARE_RETRY_SECONDS
                        self.decode_backend = "SOFTWARE_PYAV_FALLBACK"
                        LOGGER.warning(
                            "Rockchip decode failed cameraId=%s errorType=%s diagnostic=%s; "
                            "falling back to PyAV",
                            self.camera_id,
                            type(error).__name__,
                            hardware.stderr_tail[-1] if hardware.stderr_tail else "none",
                        )
                        await hardware.close()
                        hardware = None
                        self._reset_decode_queue()
                        continue
                # Preserve a small fresh tail when packets arrive in bursts.
                # Requiring a completely empty queue needlessly skips useful
                # observations; processing an old backlog instead adds latency.
                self.decode_backend = (
                    "SOFTWARE_PYAV_FALLBACK" if self.hardware_decode_failures else "SOFTWARE_PYAV"
                )
                sample = self._decode_queue.qsize() <= 2 and (
                    time.time_ns() // 1_000_000 - packet.timestamp_millis <= 80
                )
                decoding = asyncio.create_task(asyncio.to_thread(self._decode, packet, sample))
                try:
                    frames = await asyncio.shield(decoding)
                except asyncio.CancelledError:
                    # Do not destroy a native codec while a thread still uses it.
                    with contextlib.suppress(Exception):
                        await decoding
                    raise
                except (OSError, ValueError, av.error.FFmpegError):
                    self._reset_decode_queue()
                    continue
                if packet.stream_id != self._stream_id or packet.generation != (
                    self.capture_generation,
                    self._decode_epoch,
                ):
                    continue
                for frame in frames:
                    for callback in tuple(self.capture_callbacks):
                        callback(frame)
                    self.capture_ready.set()
        finally:
            if hardware is not None:
                await hardware.close()
            self._decoder = None

    def _publish_hardware_frame(self, frame: CapturedFrame) -> None:
        if not self.capture_callbacks or frame.stream_id != self._stream_id:
            return
        for callback in tuple(self.capture_callbacks):
            callback(frame)
        self.capture_ready.set()

    def _decode(self, packet: DecodePacket, sample: bool = True) -> list[CapturedFrame]:
        started = time.perf_counter()
        generation = (packet.stream_id, *packet.generation)
        if generation != self._decoder_generation:
            self._decoder = None
            self._next_sample_pts = None
            self._decoder_generation = generation
            self._decode_frame_keys = {}
        if self._decoder is None:
            if not packet.keyframe:
                return []
            self._decoder = av.CodecContext.create("h264", "r")
            self._decoder.extradata = packet.extradata
            self._decoder.thread_count = 1
        plain = av.Packet(packet.data)
        plain.pts = packet.pts
        plain.dts = packet.dts if packet.dts >= 0 else None
        plain.time_base = TIME_BASE
        self._decode_frame_keys[packet.pts] = h264_frame_key(packet.data)
        if len(self._decode_frame_keys) > 128:
            self._decode_frame_keys.pop(next(iter(self._decode_frame_keys)))
        result = []
        for frame in self._decoder.decode(plain):
            if frame.pts is None or not sample:
                continue
            pts = int(frame.pts * frame.time_base / TIME_BASE)
            if self._next_sample_pts is not None and pts < self._next_sample_pts:
                continue
            self._next_sample_pts = max(
                (self._next_sample_pts or pts) + 90_000 / self.settings.task_capture_fps,
                pts + 1,
            )
            output = io.BytesIO()
            # Stable quality, unlike bitrate-targeted MJPEG rate control.
            source_image = frame.to_image()
            source_image.save(output, format="JPEG", quality=95)
            result.append(
                CapturedFrame(
                    output.getvalue(),
                    packet.timestamp_millis,
                    packet.stream_id,
                    pts,
                    (time.perf_counter() - started) * 1000,
                    source_image,
                    self._decode_frame_keys.get(pts),
                )
            )
        return result

    def _decode_hevc(
        self, packet: DecodePacket, preview: bool, capture: bool
    ) -> tuple[list[tuple[bytes, int, bool, str | None]], list[CapturedFrame]]:
        """Decode HEVC once, then encode only bounded preview frames as H.264."""
        started = time.perf_counter()
        generation = (packet.stream_id, *packet.generation)
        if generation != self._decoder_generation:
            self._decoder = None
            self._hevc_encoder = None
            self._next_preview_pts = None
            self._next_sample_pts = None
            self._decoder_generation = generation
        if self._decoder is None:
            if not packet.keyframe:
                return [], []
            self._decoder = av.CodecContext.create("hevc", "r")
            self._decoder.extradata = packet.extradata
            self._decoder.thread_count = 2
        plain = av.Packet(packet.data)
        plain.pts = packet.pts
        plain.dts = packet.dts if packet.dts >= 0 else None
        plain.time_base = TIME_BASE
        encoded: list[tuple[bytes, int, bool, str | None]] = []
        captures: list[CapturedFrame] = []
        for frame in self._decoder.decode(plain):
            if frame.pts is None:
                continue
            pts = int(frame.pts * frame.time_base / TIME_BASE)
            want_preview = preview and (
                self._next_preview_pts is None or pts >= self._next_preview_pts
            )
            want_capture = (
                capture
                and (not preview or want_preview)
                and (self._next_sample_pts is None or pts >= self._next_sample_pts)
            )
            frame_key = None
            if want_preview:
                if self._hevc_encoder is None:
                    scale = min(
                        1.0,
                        self.settings.preview_hevc_max_width / frame.width,
                        self.settings.preview_hevc_max_height / frame.height,
                    )
                    width = max(2, int(frame.width * scale) // 2 * 2)
                    height = max(2, int(frame.height * scale) // 2 * 2)
                    self._hevc_encoder = av.CodecContext.create("libx264", "w")
                    self._hevc_encoder.width = width
                    self._hevc_encoder.height = height
                    self._hevc_encoder.pix_fmt = "yuv420p"
                    self._hevc_encoder.time_base = TIME_BASE
                    self._hevc_encoder.framerate = Fraction(
                        round(self.settings.preview_hevc_fps), 1
                    )
                    self._hevc_encoder.gop_size = max(1, round(self.settings.preview_hevc_fps * 2))
                    self._hevc_encoder.options = {
                        "preset": "ultrafast",
                        "tune": "zerolatency",
                        "crf": "28",
                        "bf": "0",
                    }
                outbound_frame = frame.reformat(
                    width=self._hevc_encoder.width,
                    height=self._hevc_encoder.height,
                    format="yuv420p",
                )
                outbound_frame.pts = pts
                outbound_frame.time_base = TIME_BASE
                for h264_packet in self._hevc_encoder.encode(outbound_frame):
                    data = bytes(h264_packet)
                    key = h264_frame_key(data)
                    encoded.append((data, pts, h264_packet.is_keyframe, key))
                    frame_key = key
                self._next_preview_pts = max(
                    (self._next_preview_pts or pts) + 90_000 / self.settings.preview_hevc_fps,
                    pts + 1,
                )
            if want_capture:
                self._next_sample_pts = max(
                    (self._next_sample_pts or pts) + 90_000 / self.settings.task_capture_fps,
                    pts + 1,
                )
                output = io.BytesIO()
                image = frame.to_image()
                image.save(output, format="JPEG", quality=95)
                captures.append(
                    CapturedFrame(
                        output.getvalue(),
                        packet.timestamp_millis,
                        packet.stream_id,
                        pts,
                        (time.perf_counter() - started) * 1000,
                        image,
                        frame_key,
                    )
                )
        return encoded, captures


class SharedCaptureStream:
    def __init__(self, hub: "CameraMediaHub", camera_id: int, source_url: SecretStr) -> None:
        self.hub = hub
        self.camera_id = camera_id
        self.source_url = source_url
        self.subscribers: dict[int, asyncio.Queue[CapturedFrame]] = {}
        self._frames = 0
        self._dropped_frames = 0
        self.started_monotonic = time.monotonic()
        self._source: CameraSource | None = None
        self._lock = asyncio.Lock()

    @property
    def frames(self) -> int:
        return self._frames

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    @property
    def reconnects(self) -> int:
        return self._source.reconnects if self._source is not None else 0

    @property
    def decode_backend(self) -> str:
        return self._source.decode_backend if self._source is not None else "PENDING"

    @property
    def hardware_decode_failures(self) -> int:
        return self._source.hardware_decode_failures if self._source is not None else 0

    async def start(self) -> None:
        async with self._lock:
            if self._source is not None:
                return
            self._source = await self.hub.acquire(
                self.camera_id, self.source_url, for_capture=True
            )
            try:
                self._source.capture_ready.clear()
                self._source.capture_generation += 1
                self._source.capture_callbacks.add(self._publish)
            finally:
                self._source.capture_reservations -= 1
        await asyncio.wait_for(
            self._source.capture_ready.wait(), self.hub.settings.task_startup_seconds
        )

    def _publish(self, frame: CapturedFrame) -> None:
        self._frames += 1
        for queue in tuple(self.subscribers.values()):
            if queue.full():
                queue.get_nowait()
                self._dropped_frames += 1
            queue.put_nowait(frame)

    async def stop(self) -> None:
        if self._source is not None:
            await self._source.deactivate_capture(self._publish)
            await self.hub.release(self._source)
            self._source = None


class CameraMediaHub:
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings
        self.sources: dict[int, CameraSource] = {}
        self._lock = asyncio.Lock()
        self._releases: set[asyncio.Task] = set()

    async def acquire(
        self, camera_id: int, source_url: SecretStr, *, for_capture: bool = False
    ) -> CameraSource:
        async with self._lock:
            source = self.sources.get(camera_id)
            if (
                source is not None
                and source.url.get_secret_value() != source_url.get_secret_value()
            ):
                if source.capture_callbacks or source.capture_reservations:
                    raise ValueError("camera source differs from the active media timeline")
                # A stale preview must not prevent a task from changing streams.
                # End its tracks before opening the replacement, preserving one
                # camera connection and letting preview clients reconnect.
                await source.close()
                self.sources.pop(camera_id, None)
                source = None
            if source is None:
                source = CameraSource(camera_id, source_url, self.settings)
                self.sources[camera_id] = source
            if for_capture:
                source.capture_reservations += 1
        try:
            await source.start()
            return source
        except BaseException:
            if for_capture:
                source.capture_reservations -= 1
            await self.release(source)
            raise

    async def preview_player(self, camera_id: int, source_url: SecretStr) -> SharedPreviewPlayer:
        return SharedPreviewPlayer(self, await self.acquire(camera_id, source_url))

    def capture_stream(self, camera_id: int, url: SecretStr, _settings) -> SharedCaptureStream:
        return SharedCaptureStream(self, camera_id, url)

    def schedule_release(self, source: CameraSource) -> None:
        task = asyncio.create_task(self.release(source))
        self._releases.add(task)
        task.add_done_callback(self._releases.discard)

    async def release(self, source: CameraSource) -> None:
        async with self._lock:
            if source.preview_owners or source.capture_callbacks or source.capture_reservations:
                return
            if self.sources.get(source.camera_id) is source:
                self.sources.pop(source.camera_id)
        await source.close()

    async def close(self) -> None:
        await asyncio.gather(*(source.close() for source in tuple(self.sources.values())))
        self.sources.clear()
        await asyncio.gather(*self._releases)
