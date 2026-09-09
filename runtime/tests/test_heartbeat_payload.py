from unittest.mock import patch

from edge_agent.app.core.config import AgentSettings
from edge_agent.app.main import build_heartbeat_payload


def test_heartbeat_uses_platform_epoch_millis_contract() -> None:
    settings = AgentSettings(node_code="NODE-1", node_name="Node 1", runtime_api_key="test-key")
    with (
        patch("edge_agent.app.main.time.time_ns", return_value=1_788_250_000_123_456_789),
        patch("edge_agent.app.main.collect_resources", return_value={"cpuUsage": 12.5}),
    ):
        payload = build_heartbeat_payload(7, settings)

    assert payload == {
        "sequence": 7,
        "agentTime": 1_788_250_000_123,
        "agentVersion": "0.1.0",
        "activationGuard": None,
        "modelUninstall": "v1",
        "agentRollbackAvailable": False,
        "failedAgentVersion": None,
        "hostName": settings.host_name,
        "cpuUsage": 12.5,
    }
