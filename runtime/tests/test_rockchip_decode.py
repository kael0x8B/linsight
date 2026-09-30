import asyncio
import sys
from fractions import Fraction
from types import SimpleNamespace

import pytest

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.stream import rockchip
from ai_runtime.app.stream.rockchip import HardwarePacket, RockchipMppDecoder, annex_b, scaled_size


def settings(tmp_path, **values):
    return RuntimeSettings(
        api_key="a-secure-runtime-key-for-tests",
        runtime_data_root=tmp_path,
        rockchip_gstreamer_python=sys.executable,
        **values,
    )


def test_rga_target_preserves_aspect_ratio_and_even_dimensions():
    assert scaled_size(3840, 2160, 1920, 1080) == (1920, 1080)
    assert scaled_size(2688, 1520, 1920, 1080) == (1908, 1080)
    assert scaled_size(1280, 720, 1920, 1080) == (1280, 720)
    assert scaled_size(0, 0, 1920, 1080) == (0, 0)


@pytest.mark.parametrize(
    ("targets", "expected"),
    [
        (["rk3588"], (3840, 2160)),
        (["rk3588s"], (3840, 2160)),
        (["rk3566"], (1920, 1080)),
        (["rk3568"], (1920, 1080)),
        ([], (1920, 1080)),
        (["unverified-arm64"], (1920, 1080)),
    ],
)
def test_capture_budget_uses_verified_board_and_never_upscales(
    tmp_path, monkeypatch, targets, expected
):
    monkeypatch.setattr(
        rockchip, "model_environment", lambda: SimpleNamespace(rknn_targets=targets)
    )
    config = settings(tmp_path)
    assert rockchip.capture_size(config, 3840, 2160) == expected
    assert rockchip.capture_size(config, 7680, 4320) == expected
    assert rockchip.capture_size(config, 640, 360) == (640, 360)


def test_capture_budget_honors_explicit_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LINSIGHT_RUNTIME_ROCKCHIP_CAPTURE_MAX_WIDTH", "1280")
    monkeypatch.setenv("LINSIGHT_RUNTIME_ROCKCHIP_CAPTURE_MAX_HEIGHT", "720")
    monkeypatch.setattr(
        rockchip, "model_environment", lambda: SimpleNamespace(rknn_targets=["rk3588"])
    )
    assert rockchip.capture_size(settings(tmp_path), 3840, 2160) == (1280, 720)


def test_capture_budget_preserves_an_explicit_single_dimension(tmp_path, monkeypatch):
    monkeypatch.setattr(
        rockchip, "model_environment", lambda: SimpleNamespace(rknn_targets=["rk3588"])
    )
    config = settings(tmp_path, rockchip_capture_max_height=1080)
    assert rockchip.capture_size(config, 3840, 2160) == (1920, 1080)


def test_avcc_access_unit_is_converted_to_annex_b_with_parameter_sets():
    extradata = (
        b"\x01\x64\x00\x1f\xff\xe1"
        b"\x00\x04\x67\x64\x00\x1f"
        b"\x01\x00\x03\x68\xee\x3c"
    )
    packet = b"\x00\x00\x00\x03\x65\xaa\xbb"
    converted = annex_b(packet, extradata, True)
    assert converted == (
        b"\x00\x00\x00\x01\x67\x64\x00\x1f"
        b"\x00\x00\x00\x01\x68\xee\x3c"
        b"\x00\x00\x00\x01\x65\xaa\xbb"
    )


def test_probe_requires_linux_arm64_and_exact_helper_result(tmp_path, monkeypatch):
    helper = tmp_path / "helper.py"
    helper.write_text("")
    monkeypatch.setattr(rockchip, "helper_path", lambda: helper)
    monkeypatch.setattr(rockchip.platform, "system", lambda: "Linux")
    monkeypatch.setattr(rockchip.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(
        rockchip.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ROCKCHIP_MPP_RGA\n"),
    )
    assert rockchip.probe(settings(tmp_path)) is True
    monkeypatch.setattr(rockchip.platform, "machine", lambda: "x86_64")
    assert rockchip.probe(settings(tmp_path)) is False


@pytest.mark.parametrize(
    ("targets", "expected"), [(["rk3588"], (3840, 2160)), (["rk3566"], (1920, 1080))]
)
@pytest.mark.parametrize(
    ("source_fps", "expected_source_fps"),
    [(None, None), (Fraction(301, 12), "25/1")],
)
def test_decoder_protocol_returns_source_timestamp_without_camera_credentials(
    tmp_path, monkeypatch, targets, expected, source_fps, expected_source_fps
):
    helper = tmp_path / "fake_helper.py"
    helper.write_text(
        """
import struct, sys
"""
        + "actual = sys.argv[sys.argv.index('--source-fps') + 1] "
        + "if '--source-fps' in sys.argv else None\n"
        + f"assert actual == {expected_source_fps!r}\n"
        + """
packet = struct.Struct('>4sIqqqB')
frame = struct.Struct('>4sIq')
header = sys.stdin.buffer.read(packet.size)
magic, length, pts, dts, timestamp, keyframe = packet.unpack(header)
payload = sys.stdin.buffer.read(length)
assert magic == b'LPKT' and payload.endswith(b'frame')
image = b'jpeg-frame'
sys.stdout.buffer.write(frame.pack(b'LFRM', len(image), pts) + image)
sys.stdout.buffer.flush()
sys.stdin.buffer.read()
"""
    )
    monkeypatch.setattr(rockchip, "helper_path", lambda: helper)
    monkeypatch.setattr(
        rockchip, "model_environment", lambda: SimpleNamespace(rknn_targets=targets)
    )

    async def scenario():
        frames = []
        received = asyncio.Event()

        def publish(frame):
            frames.append(frame)
            received.set()

        packet = HardwarePacket(
            data=b"\x00\x00\x00\x01\x65frame",
            pts=90_000,
            dts=90_000,
            timestamp_millis=1_789_000_000_123,
            keyframe=True,
            extradata=None,
            width=3840,
            height=2160,
            source_fps=source_fps,
        )
        decoder = RockchipMppDecoder(settings(tmp_path), packet, "stream-1", publish)
        assert (decoder.width, decoder.height) == expected
        await decoder.start()
        try:
            await decoder.offer(packet)
            await asyncio.wait_for(received.wait(), 2)
            assert len(frames) == 1
            assert frames[0].data == b"jpeg-frame"
            assert frames[0].timestamp_millis == packet.timestamp_millis
            assert frames[0].source_pts == packet.pts
            assert frames[0].stream_id == "stream-1"
            assert frames[0].frame_key is not None
            assert frames[0].decode_millis is not None
        finally:
            await decoder.close()

    asyncio.run(scenario())
