import asyncio
import io
import struct
from fractions import Fraction
from uuid import UUID

import av
import numpy as np
import pytest
from PIL import Image
from pydantic import SecretStr

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.stream.frame_stamp import STAMP_UUID, stamp_h264
from ai_runtime.app.stream.shared import CameraMediaHub, CameraSource, DecodePacket


def parse_stamp(data):
    assert data[:5] == b'\x00\x00\x00\x01\x06'
    escaped = data[5:].split(b'\x00\x00\x00\x01', 1)[0]
    rbsp = escaped.replace(b'\x00\x00\x03', b'\x00\x00')
    assert rbsp[0] == 5 and rbsp[1] in (40,56) and rbsp[2:18] == STAMP_UUID
    return str(UUID(bytes=rbsp[18:34])), struct.unpack('>Q', rbsp[34:42])[0]


def test_source_stamp_preserves_high_pts_and_start_code_emulation():
    identity = '00000001-0000-0003-0000-000000000002'
    for pts in (0, 1, 255, 256, 90_000, 2**53 - 1):
        encoded = stamp_h264(b'\x00\x00\x00\x01\x65abc', identity, pts)
        assert parse_stamp(encoded) == (identity, pts)
        assert encoded.endswith(b'\x00\x00\x00\x01\x65abc')
    with pytest.raises(ValueError):
        stamp_h264(b'', identity, 2**53)


def test_rtp_time_stays_monotonic_across_a_source_pts_restart():
    source = CameraSource(1, SecretStr('rtsp://192.0.2.1/sub'),
                          RuntimeSettings(api_key='a-secure-runtime-test-key'))
    assert source._transport_timestamp(90_000, 1.0) == 0
    assert source._transport_timestamp(93_600, 1.04) == 3600
    source._transport_offset = None  # Reopened source restarts its PTS.
    assert source._transport_timestamp(0, 6.04) == 453_600
    assert source._transport_timestamp(3600, 6.08) == 457_200


def write_h264_camera(video):
    with av.open(str(video), 'w', format='mpegts') as output:
        stream = output.add_stream('libx264', rate=25)
        stream.width = 160
        stream.height = 120
        stream.pix_fmt = 'yuv420p'
        stream.options = {'preset': 'ultrafast', 'tune': 'zerolatency', 'bf': '0', 'g': '25'}
        for index in range(150):
            pixels = np.full((120, 160, 3), 45, dtype=np.uint8)
            pixels[30:70, index % 110:index % 110 + 35] = (200, 80, 40)
            frame = av.VideoFrame.from_ndarray(pixels, format='rgb24')
            frame.pts = index
            frame.time_base = Fraction(1, 25)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)



def test_real_h264_preview_and_analysis_share_frame_pts_and_decoder(tmp_path):
    video = tmp_path / 'camera.ts'
    write_h264_camera(video)

    async def scenario():
        settings = RuntimeSettings(api_key='a-secure-runtime-test-key', task_startup_seconds=5)
        hub = CameraMediaHub(settings)
        url = SecretStr(str(video))
        capture = hub.capture_stream(4, url, settings)
        queue = asyncio.Queue(maxsize=1)
        capture.subscribers[1] = queue
        await capture.start()
        player = await hub.preview_player(4, url)
        track = player.subscribe()
        assert len(hub.sources) == 1
        assert capture._source is player.source
        decoder = av.CodecContext.create('h264', 'r')
        decoder.thread_count = 1
        captured = {}
        decoded = {}

        async def read_captures():
            for _ in range(25):
                frame = await queue.get()
                assert frame.frame_key and len(frame.frame_key)==32
                captured[(frame.stream_id, frame.source_pts)] = frame

        async def read_video():
            for _ in range(65):
                packet = await track.recv()
                stamp = parse_stamp(bytes(packet))
                assert stamp[1] == packet.pts
                for frame in decoder.decode(packet):
                    decoded[(stamp[0], frame.pts)] = frame.to_ndarray(format='rgb24')

        try:
            await asyncio.wait_for(asyncio.gather(read_captures(), read_video()), 5)
            common = captured.keys() & decoded.keys()
            assert len(common) >= 10
            for key in common:
                # Model input is the exact RGB decoding of the stamped video
                # frame; the separate evidence encoding may be lossy.
                np.testing.assert_array_equal(np.asarray(captured[key].image), decoded[key])
                with Image.open(io.BytesIO(captured[key].data)) as image:
                    difference = np.abs(
                        np.asarray(image).astype(float) - decoded[key].astype(float)
                    )
                    assert difference.mean() < 4  # JPEG compression only, same source frame.
            await capture.stop()
            assert hub.sources[4].preview_owners == 1
            player.stop()
            await asyncio.sleep(0.05)
            assert not hub.sources
            assert track.readyState == 'ended'
        finally:
            await capture.stop()
            player.stop()
            await hub.close()
    asyncio.run(scenario())


def test_slow_analysis_decoder_does_not_stall_encoded_preview(tmp_path, monkeypatch):
    import time

    video = tmp_path / 'slow-analysis.ts'
    write_h264_camera(video)
    original = CameraSource._decode

    def slow_decode(self, packet, sample=True):
        time.sleep(.08)  # Deliberately slower than the camera's 40 ms frame interval.
        return original(self, packet, sample)

    monkeypatch.setattr(CameraSource, '_decode', slow_decode)

    async def scenario():
        settings = RuntimeSettings(api_key='a-secure-runtime-test-key', task_startup_seconds=5)
        hub = CameraMediaHub(settings)
        url = SecretStr(str(video))
        capture = hub.capture_stream(4, url, settings)
        capture.subscribers[1] = asyncio.Queue(maxsize=1)
        player = None
        try:
            await capture.start()
            player = await hub.preview_player(4, url)
            track = player.subscribe()
            await asyncio.wait_for(track.recv(), 2)  # Wait for the next keyframe.
            started = time.monotonic()
            for _ in range(40):
                await asyncio.wait_for(track.recv(), 1)
            assert time.monotonic() - started < 2.3
            assert len(hub.sources) == 1
            assert player.source._decode_queue.qsize() <= 30
        finally:
            await capture.stop()
            if player is not None:
                player.stop()
            await hub.close()
    asyncio.run(scenario())


def test_catching_up_skips_old_images_without_breaking_h264_references(tmp_path):
    video = tmp_path / 'catch-up.ts'
    write_h264_camera(video)
    source = CameraSource(4, SecretStr(str(video)),
        RuntimeSettings(api_key='a-secure-runtime-test-key'))
    reference = av.CodecContext.create('h264', 'r')
    reference.thread_count = 1
    with av.open(str(video)) as input_file:
        packets = [p for p in input_file.demux(video=0) if p.pts is not None][:12]
        for index, packet in enumerate(packets):
            expected = reference.decode(packet)
            actual = source._decode(DecodePacket(bytes(packet), packet.pts, 1000 + index * 40,
                source._stream_id, (0, 0), packet.is_keyframe,
                packet.stream.codec_context.extradata), sample=index == 11)
            if index < 11:
                assert actual == []
            else:
                assert len(actual) == 1
                assert actual[0].source_pts == expected[0].pts
                np.testing.assert_array_equal(
                    np.asarray(actual[0].image), expected[0].to_ndarray(format='rgb24'))


@pytest.mark.parametrize('queued_age,expected_indices', [(0, [9, 10, 11]), (120, [11])])
def test_bursty_camera_preserves_only_a_fresh_bounded_tail(
    tmp_path, monkeypatch, queued_age, expected_indices,
):
    video = tmp_path / 'burst.ts'
    write_h264_camera(video)
    monkeypatch.setattr('ai_runtime.app.stream.shared.time.time_ns', lambda: 2_000_000_000)

    async def scenario():
        source = CameraSource(4, SecretStr(str(video)), RuntimeSettings(
            api_key='a-secure-runtime-test-key', task_capture_fps=25,
        ))
        captured = []
        completed = asyncio.Event()
        with av.open(str(video)) as input_file:
            packets = [packet for packet in input_file.demux(video=0)
                       if packet.pts is not None][:12]
            decoder = av.CodecContext.create('h264', 'r')
            decoder.thread_count = 1
            expected = [frame for packet in packets for frame in decoder.decode(packet)]

            def received(frame):
                captured.append(frame)
                if frame.source_pts == packets[-1].pts:
                    completed.set()

            source.capture_callbacks.add(received)
            for index, packet in enumerate(packets):
                source._offer_decode(packet, packet.pts,
                                     2000 if index == 11 else 2000 - queued_age)
            source._decode_worker = asyncio.create_task(source._decode_loop())
            try:
                await asyncio.wait_for(completed.wait(), 2)
                assert [frame.source_pts for frame in captured] == [
                    packets[index].pts for index in expected_indices
                ]
                for actual, index in zip(captured, expected_indices, strict=True):
                    np.testing.assert_array_equal(
                        np.asarray(actual.image), expected[index].to_ndarray(format='rgb24'),
                    )
            finally:
                await source.close()

    asyncio.run(scenario())


def test_unavailable_rtsp_source_retries_and_stops_cleanly(monkeypatch):
    def unavailable(*args, **kwargs):
        raise av.error.HTTPNotFoundError(875574520, 'Test RTSP source ended')

    monkeypatch.setattr('ai_runtime.app.stream.shared.MediaPlayer', unavailable)

    async def scenario():
        source = CameraSource(1, SecretStr('rtsp://192.0.2.1/test'), RuntimeSettings(
            api_key='a-secure-runtime-test-key', task_startup_seconds=2,
        ))
        try:
            with pytest.raises(RuntimeError, match='shared media source unavailable'):
                await source.start()
            assert source.reconnects == 1
            assert not source._runner.done()
        finally:
            await source.close()
        assert source._decode_worker.done()
    asyncio.run(scenario())


def test_cancel_during_failed_source_open_preserves_clean_shutdown(monkeypatch):
    import threading

    async def scenario():
        opening = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def delayed_failure(*args, **kwargs):
            loop.call_soon_threadsafe(opening.set)
            assert release.wait(3)
            raise av.error.HTTPNotFoundError(875574520, 'Test source ended during shutdown')

        monkeypatch.setattr('ai_runtime.app.stream.shared.MediaPlayer', delayed_failure)
        source = CameraSource(1, SecretStr('rtsp://192.0.2.1/test'), RuntimeSettings(
            api_key='a-secure-runtime-test-key',
        ))
        source._runner = asyncio.create_task(source._run())
        await asyncio.wait_for(opening.wait(), 2)
        closing = asyncio.create_task(source.close())
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(closing, 2)
        assert source._runner.cancelled()
    asyncio.run(scenario())
