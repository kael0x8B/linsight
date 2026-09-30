import asyncio
from types import SimpleNamespace
from typing import Any, cast

from aiortc import RTCPeerConnection
from aiortc.mediastreams import VideoStreamTrack
from pydantic import SecretStr

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.stream.webrtc import WebRtcManager, WebRtcOfferRequest


class FakePlayer:
    def __init__(self) -> None:
        self.video = VideoStreamTrack()
        self.audio = None


def test_answer_negotiates_h264_before_applying_browser_offer() -> None:
    async def create_player(_source_url: SecretStr) -> FakePlayer:
        return FakePlayer()

    async def scenario() -> None:
        browser = RTCPeerConnection()
        browser.addTransceiver("video", direction="recvonly")
        offer = await browser.createOffer()

        settings = RuntimeSettings(api_key="a-secure-runtime-key-for-tests")
        manager = WebRtcManager(settings, player_factory=create_player)
        response = await manager.create_session(
            WebRtcOfferRequest(
                cameraId=7,
                sourceUrl=SecretStr("rtsp://operator:secret@192.0.2.10/sub"),
                offerSdp=offer.sdp,
                offerType="offer",
            )
        )

        assert response.answer_sdp is not None
        answer_lines = response.answer_sdp.splitlines()
        assert any(line == "a=rtpmap:99 H264/90000" for line in answer_lines)
        assert not any(" VP8/90000" in line for line in answer_lines)

        await manager.release_session(response.session_id)
        await browser.close()

    asyncio.run(scenario())


def test_connected_session_is_not_expired_by_throttled_browser_polling() -> None:
    connected = cast(
        Any,
        SimpleNamespace(
            last_access_monotonic=10.0,
            peer=SimpleNamespace(connectionState="connected"),
        ),
    )
    disconnected = cast(
        Any,
        SimpleNamespace(
            last_access_monotonic=10.0,
            peer=SimpleNamespace(connectionState="disconnected"),
        ),
    )

    assert not WebRtcManager._session_should_expire(connected, deadline=20.0)
    assert WebRtcManager._session_should_expire(disconnected, deadline=20.0)


def test_new_stream_retires_old_preview_sessions() -> None:
    players: list[FakePlayer] = []

    async def create_player(_source_url: SecretStr) -> FakePlayer:
        player = FakePlayer()
        players.append(player)
        return player

    async def offer(browser: RTCPeerConnection) -> str:
        browser.addTransceiver("video", direction="recvonly")
        return (await browser.createOffer()).sdp

    async def scenario() -> None:
        settings = RuntimeSettings(api_key="a-secure-runtime-key-for-tests")
        manager = WebRtcManager(settings, player_factory=create_player)
        sub_browser, main_browser = RTCPeerConnection(), RTCPeerConnection()
        try:
            sub = await manager.create_session(
                WebRtcOfferRequest(
                    cameraId=7,
                    sourceUrl=SecretStr("rtsp://camera/sub"),
                    offerSdp=await offer(sub_browser),
                )
            )
            main = await manager.create_session(
                WebRtcOfferRequest(
                    cameraId=7,
                    sourceUrl=SecretStr("rtsp://camera/main"),
                    offerSdp=await offer(main_browser),
                )
            )
            assert not manager.has_session(sub.session_id)
            assert manager.has_session(main.session_id)
            assert manager.active_stream_count == 1
            assert players[0].video.readyState == "ended"
            await manager.release_session(sub.session_id)
            assert manager.has_session(main.session_id)
        finally:
            await manager.close()
            await sub_browser.close()
            await main_browser.close()

    asyncio.run(scenario())
