import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from aiortc import RTCPeerConnection, RTCRtpSender, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.stream.shared import (
    CameraMediaHub,
    SharedPreviewPlayer,
    UnsupportedTimelineCodec,
)

LOGGER = logging.getLogger("linsight.runtime.webrtc")


class WebRtcState(StrEnum):
    CONNECTING = "CONNECTING"
    READY = "READY"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class WebRtcOfferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: int = Field(alias="cameraId", gt=0)
    source_url: SecretStr = Field(alias="sourceUrl")
    offer_sdp: str = Field(alias="offerSdp", min_length=1, max_length=1_000_000)
    offer_type: str = Field(default="offer", alias="offerType", pattern="^offer$")


class WebRtcSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    camera_id: int = Field(alias="cameraId")
    protocol: str = "WEBRTC"
    state: WebRtcState
    subscriber_count: int = Field(alias="subscriberCount", ge=0)
    diagnostic_id: str = Field(alias="diagnosticId")
    answer_sdp: str | None = Field(default=None, alias="answerSdp")
    answer_type: str | None = Field(default=None, alias="answerType")


class WebRtcUnavailableError(RuntimeError):
    def __init__(self, error_code: str, diagnostic_id: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.diagnostic_id = diagnostic_id


class Player(Protocol):
    video: Any
    audio: Any


PlayerFactory = Callable[[SecretStr], Awaitable[Player]]
PeerFactory = Callable[[], RTCPeerConnection]


@dataclass
class WebRtcSource:
    camera_id: int
    source_url: SecretStr
    player: Player
    relay: MediaRelay
    subscribers: set[str] = field(default_factory=set)

    def subscribe(self) -> Any:
        if isinstance(self.player, SharedPreviewPlayer):
            return self.player.subscribe()
        if self.player.video is None:
            raise RuntimeError("RTSP source has no video track")
        return self.relay.subscribe(self.player.video)

    def stop(self) -> None:
        if self.player.video is not None:
            self.player.video.stop()
        if self.player.audio is not None:
            self.player.audio.stop()


@dataclass
class WebRtcSession:
    session_id: str
    camera_id: int
    source: WebRtcSource
    peer: RTCPeerConnection
    outbound_track: Any
    diagnostic_id: str
    state: WebRtcState = WebRtcState.CONNECTING
    created_monotonic: float = field(default_factory=time.monotonic)
    last_access_monotonic: float = field(default_factory=time.monotonic)
    stalled_logged: bool = False


class WebRtcManager:
    """Owns browser peer sessions while sharing one encoded RTSP pull per camera."""

    def __init__(
        self,
        settings: RuntimeSettings,
        player_factory: PlayerFactory | None = None,
        peer_factory: PeerFactory | None = None,
        media_hub: CameraMediaHub | None = None,
    ) -> None:
        self.settings = settings
        self._media_hub = media_hub
        self._player_factory = player_factory or self._create_player
        self._peer_factory = peer_factory or RTCPeerConnection
        self._sources: dict[int, WebRtcSource] = {}
        self._sessions: dict[str, WebRtcSession] = {}
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task[None] | None = None

    @property
    def active_stream_count(self) -> int:
        return len(self._sources)

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def start(self) -> None:
        if self._reaper is None:
            self._reaper = asyncio.create_task(self._reap_idle_sessions(), name="webrtc-reaper")

    async def close(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper
            self._reaper = None
        async with self._lock:
            session_ids = list(self._sessions)
        await asyncio.gather(
            *(self.release_session(session_id) for session_id in session_ids),
            return_exceptions=True,
        )

    async def create_session(self, request: WebRtcOfferRequest) -> WebRtcSessionResponse:
        session_id = uuid4().hex
        diagnostic_id = str(uuid4())
        peer = self._peer_factory()
        source: WebRtcSource | None = None
        outbound_track: Any = None
        try:
            source = await self._acquire_source(request, session_id)
            outbound_track = source.subscribe()
            session = WebRtcSession(
                session_id=session_id,
                camera_id=request.camera_id,
                source=source,
                peer=peer,
                outbound_track=outbound_track,
                diagnostic_id=diagnostic_id,
            )
            async with self._lock:
                if self._sources.get(request.camera_id) is not source:
                    raise RuntimeError("RTSP source changed during negotiation")
                self._sessions[session_id] = session
            self._bind_connection_lifecycle(session)

            # aiortc computes the common codec list while applying the remote
            # offer, so codec preferences must be set on the local transceiver
            # first. Applying them afterwards leaves Chrome's VP8 preference in
            # place and corrupts an encoded H.264 RTSP passthrough stream.
            peer.addTrack(outbound_track)
            self._prefer_h264(peer)
            await peer.setRemoteDescription(
                RTCSessionDescription(sdp=request.offer_sdp, type=request.offer_type)
            )
            answer = await peer.createAnswer()
            await peer.setLocalDescription(answer)
            await self._wait_for_ice_gathering(peer)
            local_description = peer.localDescription
            if local_description is None:
                raise RuntimeError("WebRTC answer was not created")
            return self._response(
                session,
                answer_sdp=local_description.sdp,
                answer_type=local_description.type,
            )
        except Exception as error:
            released = await self._release_if_registered(session_id)
            if not released:
                if outbound_track is not None:
                    outbound_track.stop()
                if source is not None:
                    await self._release_source_subscriber(source, session_id)
                await peer.close()
            error_code = (
                "UNSUPPORTED_VIDEO_CODEC"
                if isinstance(error, UnsupportedTimelineCodec)
                else "WEBRTC_NEGOTIATION_FAILED"
            )
            raise WebRtcUnavailableError(error_code, diagnostic_id) from error

    async def get_session(self, session_id: str) -> WebRtcSessionResponse:
        session = await self._require_session(session_id)
        session.last_access_monotonic = time.monotonic()
        await self._refresh_media_state(session)
        return self._response(session)

    async def release_session(self, session_id: str) -> None:
        source: WebRtcSource | None = None
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return
            session.state = WebRtcState.CLOSED
            source = session.source
            source.subscribers.discard(session_id)
            if not source.subscribers:
                if self._sources.get(source.camera_id) is source:
                    self._sources.pop(source.camera_id, None)
        session.outbound_track.stop()
        await session.peer.close()
        if source is not None and not source.subscribers:
            source.stop()

    async def _release_if_registered(self, session_id: str) -> bool:
        async with self._lock:
            registered = session_id in self._sessions
        if registered:
            await self.release_session(session_id)
        return registered

    async def _release_source_subscriber(self, source: WebRtcSource, session_id: str) -> None:
        async with self._lock:
            source.subscribers.discard(session_id)
            should_stop = not source.subscribers
            if should_stop and self._sources.get(source.camera_id) is source:
                self._sources.pop(source.camera_id, None)
        if should_stop:
            source.stop()

    async def _acquire_source(self, request: WebRtcOfferRequest, session_id: str) -> WebRtcSource:
        async with self._lock:
            source = self._sources.get(request.camera_id)
            if source is not None and (
                source.source_url.get_secret_value() != request.source_url.get_secret_value()
            ):
                # The task may have switched from SUB to MAIN while browsers still
                # hold the old preview. Retire those sessions before opening the
                # new one; the media hub will keep the camera to a single pull.
                stale_sessions = [
                    self._sessions.pop(old_id)
                    for old_id in tuple(source.subscribers)
                    if old_id in self._sessions
                ]
                for old_session in stale_sessions:
                    old_session.state = WebRtcState.CLOSED
                    old_session.outbound_track.stop()
                source.subscribers.clear()
                self._sources.pop(request.camera_id, None)
                source.stop()
                await asyncio.gather(
                    *(old_session.peer.close() for old_session in stale_sessions),
                    return_exceptions=True,
                )
                source = None
            if source is None:
                try:
                    player = await asyncio.wait_for(
                        self._media_hub.preview_player(request.camera_id, request.source_url)
                        if self._media_hub is not None
                        else self._player_factory(request.source_url),
                        timeout=self.settings.preview_startup_seconds,
                    )
                except TimeoutError as error:
                    raise RuntimeError("RTSP source open timed out") from error
                source = WebRtcSource(
                    camera_id=request.camera_id,
                    source_url=request.source_url,
                    player=player,
                    relay=MediaRelay(),
                )
                if source.player.video is None:
                    source.stop()
                    raise RuntimeError("RTSP source has no video track")
                self._sources[request.camera_id] = source
            source.subscribers.add(session_id)
            return source

    def _bind_connection_lifecycle(self, session: WebRtcSession) -> None:
        @session.peer.on("connectionstatechange")
        async def connection_state_changed() -> None:
            state = session.peer.connectionState
            if state == "failed":
                LOGGER.warning(
                    "WebRTC peer failed cameraId=%s sessionId=%s iceState=%s",
                    session.camera_id,
                    session.session_id,
                    session.peer.iceConnectionState,
                )
            if state in {"failed", "closed"}:
                session.state = WebRtcState.FAILED

    @staticmethod
    async def _refresh_media_state(session: WebRtcSession) -> None:
        if session.peer.connectionState in {"failed", "closed"}:
            session.state = WebRtcState.FAILED
            return
        stats = await session.peer.getStats()
        if any(
            getattr(report, "type", None) == "outbound-rtp"
            and getattr(report, "kind", None) == "video"
            and getattr(report, "packetsSent", 0) > 0
            for report in stats.values()
        ):
            session.state = WebRtcState.READY
        elif (
            session.peer.connectionState == "connected"
            and not session.stalled_logged
            and time.monotonic() - session.created_monotonic >= 5
        ):
            session.stalled_logged = True
            LOGGER.warning(
                "WebRTC connected without outbound media sessionId=%s cameraId=%s directions=%s",
                session.session_id,
                session.camera_id,
                [value.currentDirection for value in session.peer.getTransceivers()],
            )

    async def _require_session(self, session_id: str) -> WebRtcSession:
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
                    if self._session_should_expire(session, deadline)
                ]
            for session_id in expired:
                await self.release_session(session_id)

    @staticmethod
    def _session_should_expire(session: WebRtcSession, deadline: float) -> bool:
        # Browser background tabs can throttle JavaScript timers beyond the
        # HTTP polling interval. The DTLS/ICE peer is the authoritative liveness
        # signal for WebRTC, so a connected media session must not be reclaimed
        # merely because its status poll arrived late. Once the browser is gone,
        # ICE consent eventually moves the peer out of connected and normal idle
        # cleanup applies.
        return (
            session.last_access_monotonic < deadline and session.peer.connectionState != "connected"
        )

    async def _create_player(self, source_url: SecretStr) -> Player:
        # decode=False forwards the camera's H.264 packets instead of software transcoding them.
        return await asyncio.to_thread(
            MediaPlayer,
            source_url.get_secret_value(),
            format="rtsp",
            options={"rtsp_transport": "tcp", "fflags": "nobuffer", "flags": "low_delay"},
            decode=False,
        )

    @staticmethod
    def _prefer_h264(peer: RTCPeerConnection) -> None:
        codecs = [
            codec
            for codec in RTCRtpSender.getCapabilities("video").codecs
            if codec.mimeType.lower() == "video/h264"
        ]
        if not codecs:
            raise RuntimeError("Runtime has no H.264 WebRTC codec")
        for transceiver in peer.getTransceivers():
            if transceiver.kind == "video":
                transceiver.setCodecPreferences(codecs)

    @staticmethod
    async def _wait_for_ice_gathering(peer: RTCPeerConnection) -> None:
        if peer.iceGatheringState == "complete":
            return
        complete = asyncio.Event()

        @peer.on("icegatheringstatechange")
        def ice_gathering_state_changed() -> None:
            if peer.iceGatheringState == "complete":
                complete.set()

        await asyncio.wait_for(complete.wait(), timeout=8.0)

    @staticmethod
    def _response(
        session: WebRtcSession,
        answer_sdp: str | None = None,
        answer_type: str | None = None,
    ) -> WebRtcSessionResponse:
        return WebRtcSessionResponse(
            sessionId=session.session_id,
            cameraId=session.camera_id,
            state=session.state,
            subscriberCount=len(session.source.subscribers),
            diagnosticId=session.diagnostic_id,
            answerSdp=answer_sdp,
            answerType=answer_type,
        )
