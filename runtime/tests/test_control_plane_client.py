from unittest.mock import patch

import httpx
import pytest

from edge_agent.app.client.control_plane import ControlPlaneClient, ControlPlaneRejectedError


def test_control_plane_client_does_not_inherit_host_proxy() -> None:
    with patch("edge_agent.app.client.control_plane.httpx.AsyncClient") as async_client:
        ControlPlaneClient("http://127.0.0.1:48888/", 10.0)

    async_client.assert_called_once_with(
        base_url="http://127.0.0.1:48888",
        timeout=10.0,
        trust_env=False,
    )


def test_control_plane_client_exposes_rejection_code() -> None:
    response = httpx.Response(
        200,
        json={"code": 1_020_005_000, "msg": "事件不存在", "data": None},
        request=httpx.Request("POST", "http://control-plane.invalid/event/transition"),
    )

    with pytest.raises(ControlPlaneRejectedError) as captured:
        ControlPlaneClient._checked_envelope(response)

    assert captured.value.code == 1_020_005_000
