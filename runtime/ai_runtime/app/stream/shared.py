"""One encoded camera source and one optional decoder shared by preview and AI."""

import asyncio
import contextlib
import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4
from weakref import WeakSet

import av
from aiortc.contrib.media import MediaPlayer
from aiortc.mediastreams import MediaStreamError, VideoStreamTrack
from pydantic import SecretStr

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.stream.frame_stamp import h264_frame_key, stamp_h264
from ai_runtime.app.stream.frames import CapturedFrame

TIME_BASE = Fraction(1, 90_000)


@dataclass(frozen=True)
class DecodePacket:
    data: bytes
    pts: int
    timestamp_millis: int
    stream_id: str
    generation: tuple[int, int]
    keyframe: bool
    extradata: bytes | None


class UnsupportedTimelineCodec(ValueError):
    pass


class PacketTrack(VideoStreamTrack):
    def __init__(self, source: "CameraSource") -> None:
        super().__init__()
        self.source = source
        self.queue: asyncio.Queue[av.Packet | None] = asyncio.Queue(maxsize=30)
        self.wait_keyframe = True
        self.source.packet_tracks.add(self)

    def offer(self, packet: av.Packet, keyframe: bool) -> None:
        if self.queue.full():
            # Dropping arbitrary inter frames leaves a broken prediction chain.
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
        self.preview_owners = 0
        self.reconnects = 0
        self._ready = asyncio.Event()
        self.capture_ready = asyncio.Event()
        self._closing = False
        self._runner: asyncio.Task | None = None
        self._decode_worker: asyncio.Task | None = None
        self._decode_queue: asyncio.Queue[DecodePacket] = asyncio.Queue(maxsize=30)
        self._decode_wait_keyframe = True
        self._decode_epoch = 0
        self._player: MediaPlayer | None = None
        self._decoder = None
        self._next_sample_pts: float | None = None
        self._stream_id = str(uuid4())
        self._last_transport_pts = -3600
        self._transport_offset: int | None = None
        self._last_packet_monotonic: float | None = None
        self._error: str | None = None
        self._unsupported_codec = False
        self.capture_generation = 0
        self._decoder_generation: tuple[str, int, int] | None = None

    async def start(self) -> None:
        if self._runner is None:
            self._decode_worker = asyncio.create_task(
                self._decode_loop(), name=f"camera-decode-{self.camera_id}"
            )
            self._runner = asyncio.create_task(self._run(), name=f"camera-media-{self.camera_id}")
        await asyncio.wait_for(self._ready.wait(), self.settings.task_startup_seconds)
        if self._unsupported_codec:
            raise UnsupportedTimelineCodec("H.264 is required for the shared preview timeline")
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
                opening = asyncio.create_task(asyncio.to_thread(
                    MediaPlayer, self.url.get_secret_value(),
                    options={"rtsp_transport": "tcp", "fflags": "nobuffer", "flags": "low_delay"},
                    timeout=self.settings.preview_startup_seconds, decode=False,
                ))
                try:
                    self._player = await asyncio.shield(opening)
                except asyncio.CancelledError:
                    # A source may disappear while cancellation waits for av.open.
                    # Preserve cancellation even if that outstanding open fails.
                    with contextlib.suppress(OSError, ValueError, av.FFmpegError):
                        self._player = await opening  # finally closes a late-opened source.
                    raise
                if self._player.video is None:
                    raise UnsupportedTimelineCodec("shared video timeline requires H.264")
                self._stream_id = str(uuid4())
                self._reset_decode_queue()
                self._transport_offset = None
                for track in tuple(self.packet_tracks):
                    track.reset()
                while not self._closing:
                    packet = await self._player.video.recv()
                    if not isinstance(packet, av.Packet) or packet.pts is None:
                        continue
                    if packet.stream.codec_context.name != "h264":
                        raise UnsupportedTimelineCodec("shared video timeline requires H.264")
                    self._error = None
                    self._ready.set()
                    source_pts = int(packet.pts * packet.time_base / TIME_BASE)
                    if source_pts < 0:
                        continue
                    timestamp_millis = time.time_ns() // 1_000_000
                    # Both branches use this exact packet PTS. No camera/host wall-clock alignment.
                    outbound = av.Packet(stamp_h264(bytes(packet), self._stream_id, source_pts, h264_frame_key(bytes(packet))))
                    # Keep ongoing RTP sessions monotonic when the camera restarts
                    # its PTS. The SEI still carries the original epoch + source PTS.
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
                    if self._player.video is not None:
                        await asyncio.to_thread(self._player.video.stop)
                    if self._player.audio is not None:
                        await asyncio.to_thread(self._player.audio.stop)
                    self._player = None
            if not self._closing:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8)

    def _transport_timestamp(self, source_pts: int, arrival: float) -> int:
        if self._transport_offset is None:
            gap = 3600 if self._last_packet_monotonic is None else max(
                3600, round((arrival - self._last_packet_monotonic) * 90_000)
            )
            self._transport_offset = self._last_transport_pts + gap - source_pts
        result = source_pts + self._transport_offset
        self._last_transport_pts = max(self._last_transport_pts, result)
        self._last_packet_monotonic = arrival
        return result

    def _reset_decode_queue(self) -> None:
        while not self._decode_queue.empty():
            self._decode_queue.get_nowait()
        self._decode_wait_keyframe = True
        self._decode_epoch += 1

    def _offer_decode(self, packet: av.Packet, pts: int, timestamp_millis: int) -> None:
        if self._decode_queue.full():
            # Preserve H.264 prediction chains after overload; catch up on a keyframe
            # without ever delaying the independent encoded preview subscribers.
            self._reset_decode_queue()
        if self._decode_wait_keyframe and not packet.is_keyframe:
            return
        self._decode_wait_keyframe = False
        self._decode_queue.put_nowait(DecodePacket(
            bytes(packet), pts, timestamp_millis, self._stream_id,
            (self.capture_generation, self._decode_epoch), packet.is_keyframe,
            packet.stream.codec_context.extradata,
        ))

    async def _decode_loop(self) -> None:
        try:
            while True:
                packet = await self._decode_queue.get()
                if (not self.capture_callbacks or packet.stream_id != self._stream_id
                        or packet.generation != (self.capture_generation, self._decode_epoch)):
                    continue
                # Preserve a small fresh tail when packets arrive in bursts.
                # Requiring a completely empty queue needlessly skips useful
                # observations; processing an old backlog instead adds latency.
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
                if (packet.stream_id != self._stream_id
                        or packet.generation != (self.capture_generation, self._decode_epoch)):
                    continue
                for frame in frames:
                    for callback in tuple(self.capture_callbacks):
                        callback(frame)
                    self.capture_ready.set()
        finally:
            self._decoder = None

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
            result.append(CapturedFrame(
                output.getvalue(), packet.timestamp_millis, packet.stream_id, pts,
                (time.perf_counter() - started) * 1000,
                source_image,
                self._decode_frame_keys.get(pts),
            ))
        return result


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
        self._fallback = None
        self._lock = asyncio.Lock()

    @property
    def frames(self) -> int:
        return self._fallback.frames if self._fallback is not None else self._frames

    @property
    def dropped_frames(self) -> int:
        return self._fallback.dropped_frames if self._fallback is not None else self._dropped_frames

    @property
    def reconnects(self) -> int:
        if self._fallback is not None:
            return self._fallback.reconnects
        return self._source.reconnects if self._source is not None else 0

    async def start(self) -> None:
        async with self._lock:
            if self._source is not None or self._fallback is not None:
                return
            try:
                self._source = await self.hub.acquire(self.camera_id, self.source_url)
            except UnsupportedTimelineCodec:
                # Preserve analysis for codecs the H.264 WebRTC path cannot forward.
                from ai_runtime.app.task.manager import SharedCameraStream

                self._fallback = SharedCameraStream(
                    self.camera_id, self.source_url, self.hub.settings
                )
                self._fallback.subscribers = self.subscribers
                await self._fallback.start()
                return
            self._source.capture_ready.clear()
            self._source.capture_generation += 1
            self._source.capture_callbacks.add(self._publish)
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
        if self._fallback is not None:
            await self._fallback.stop()
            self._fallback = None
        if self._source is not None:
            self._source.capture_callbacks.discard(self._publish)
            await self.hub.release(self._source)
            self._source = None


class CameraMediaHub:
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings
        self.sources: dict[int, CameraSource] = {}
        self._lock = asyncio.Lock()
        self._releases: set[asyncio.Task] = set()

    async def acquire(self, camera_id: int, source_url: SecretStr) -> CameraSource:
        async with self._lock:
            source = self.sources.get(camera_id)
            if source is None:
                source = CameraSource(camera_id, source_url, self.settings)
                self.sources[camera_id] = source
            elif source.url.get_secret_value() != source_url.get_secret_value():
                raise ValueError("camera source differs from the active media timeline")
        try:
            await source.start()
            return source
        except BaseException:
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
            if source.preview_owners or source.capture_callbacks:
                return
            if self.sources.get(source.camera_id) is source:
                self.sources.pop(source.camera_id)
        await source.close()

    async def close(self) -> None:
        await asyncio.gather(*(source.close() for source in tuple(self.sources.values())))
        self.sources.clear()
        await asyncio.gather(*self._releases)
