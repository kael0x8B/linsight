import asyncio
import json

from pydantic import SecretStr

from ai_runtime.app.stream.contracts import ProbeStageStatus, StreamProbeRequest
from ai_runtime.app.stream.probe import ProcessResult, StreamProbeService


async def successful_network(_host: str, _port: int) -> None:
    return None


def request() -> StreamProbeRequest:
    return StreamProbeRequest(
        camera_id=7,
        protocol="RTSP",
        host="192.0.2.10",
        port=554,
        stream_uri=SecretStr("/Streaming/Channels/101?token=stream-secret"),
        username=SecretStr("operator"),
        password=SecretStr("password-secret"),
    )


def test_probe_success_requires_video_and_keyframe() -> None:
    async def runner(_args: list[str], _timeout: float) -> ProcessResult:
        payload = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "25/1",
                }
            ],
            "frames": [{"key_frame": 0}, {"key_frame": 1}],
        }
        return ProcessResult(0, json.dumps(payload).encode(), b"")

    service = StreamProbeService(
        resolver=successful_network,
        connector=successful_network,
        process_runner=runner,
    )
    result = asyncio.run(service.probe(request()))

    assert result.online is True
    assert result.stream is not None
    assert result.stream.codec == "h264"
    assert all(stage.status is ProbeStageStatus.SUCCESS for stage in result.stages)
    serialized = result.model_dump_json()
    assert "password-secret" not in serialized
    assert "stream-secret" not in serialized
    assert "operator" not in serialized


def test_auth_failure_is_sanitized_and_later_stages_are_skipped() -> None:
    async def runner(_args: list[str], _timeout: float) -> ProcessResult:
        return ProcessResult(
            1,
            b"",
            b"401 Unauthorized rtsp://operator:password-secret@192.0.2.10/private",
        )

    service = StreamProbeService(
        resolver=successful_network,
        connector=successful_network,
        process_runner=runner,
    )
    result = asyncio.run(service.probe(request()))

    assert result.online is False
    assert result.error_code == "AUTH_FAILED"
    assert result.error_message == "设备认证失败"
    assert result.stages[2].status is ProbeStageStatus.FAILED
    assert result.stages[3].status is ProbeStageStatus.SKIPPED
    serialized = result.model_dump_json()
    assert "password-secret" not in serialized
    assert "/private" not in serialized


def test_dns_failure_does_not_attempt_tcp_or_ffprobe() -> None:
    calls = {"connector": 0, "runner": 0}

    async def failing_resolver(_host: str, _port: int) -> None:
        raise OSError("not resolvable")

    async def connector(_host: str, _port: int) -> None:
        calls["connector"] += 1

    async def runner(_args: list[str], _timeout: float) -> ProcessResult:
        calls["runner"] += 1
        return ProcessResult(0, b"{}", b"")

    service = StreamProbeService(
        resolver=failing_resolver,
        connector=connector,
        process_runner=runner,
    )
    result = asyncio.run(service.probe(request()))

    assert result.error_code == "DNS_RESOLUTION_FAILED"
    assert calls == {"connector": 0, "runner": 0}
    assert len(result.stages) == 5


def test_ffprobe_arguments_encode_credentials_without_changing_response_contract() -> None:
    captured: list[str] = []

    async def runner(args: list[str], _timeout: float) -> ProcessResult:
        captured.extend(args)
        payload = {"streams": [{"codec_type": "video"}], "frames": [{"key_frame": 1}]}
        return ProcessResult(0, json.dumps(payload).encode(), b"")

    probe_request = request().model_copy(
        update={
            "username": SecretStr("user@example.com"),
            "password": SecretStr("p@ss:word"),
        }
    )
    service = StreamProbeService(
        resolver=successful_network,
        connector=successful_network,
        process_runner=runner,
    )
    result = asyncio.run(service.probe(probe_request))

    assert result.online is True
    assert captured[-1].startswith("rtsp://user%40example.com:p%40ss%3Aword@192.0.2.10:554/")
    assert captured[-1].endswith("/Streaming/Channels/101?token=stream-secret")
