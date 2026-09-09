from datetime import UTC, datetime

from ai_runtime.app.stream.contracts import (
    ProbeStageName,
    ProbeStageResult,
    ProbeStageStatus,
    StreamProbeResult,
)
from edge_agent.app.client.control_plane import StreamCheckAssignment
from edge_agent.app.core.config import AgentSettings
from edge_agent.app.main import build_stream_check_report, build_stream_probe_request


def test_control_plane_report_contains_only_sanitized_probe_result() -> None:
    result = StreamProbeResult(
        camera_id=1,
        online=False,
        checked_at=datetime.now(UTC),
        diagnostic_id="00000000-0000-0000-0000-000000000001",
        error_code="AUTH_FAILED",
        error_message="设备认证失败",
        stages=[
            ProbeStageResult(
                name=ProbeStageName.AUTH,
                status=ProbeStageStatus.FAILED,
                duration_ms=10,
                message="设备认证失败",
            )
        ],
    )

    payload = build_stream_check_report(20, result)

    assert payload["checkId"] == 20
    assert payload["errorCode"] == "AUTH_FAILED"
    assert "streamUri" not in payload
    assert "username" not in payload
    assert "password" not in payload


def test_stream_check_uses_field_safe_configurable_timeout() -> None:
    settings = AgentSettings(
        node_code="NODE-1", node_name="Node 1", runtime_api_key="test-runtime-key"
    )
    assignment = StreamCheckAssignment.model_validate(
        {
            "checkId": 1,
            "cameraId": 2,
            "protocol": "ONVIF",
            "host": "192.0.2.10",
            "port": 554,
            "streamUri": "/Streaming/Channels/101",
        }
    )

    request = build_stream_probe_request(settings, assignment)

    assert settings.stream_probe_timeout_seconds == 25.0
    assert request.timeout_seconds == 25.0
