from fastapi.testclient import TestClient

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.main import create_app


def test_health_is_public_but_runtime_operations_require_runtime_key(tmp_path) -> None:
    app = create_app(
        RuntimeSettings(api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path)
    )
    client = TestClient(app)

    assert client.get("/v1/health").json() == {"status": "UP", "version": "v1"}
    response = client.post("/v1/stream/probe", json={})
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}

    assert client.get("/v1/observability/snapshot").status_code == 401
    snapshot = client.get(
        "/v1/observability/snapshot",
        headers={"X-Runtime-Key": "a-secure-runtime-key-for-tests"},
    )
    assert snapshot.status_code == 200
    value = snapshot.json()
    assert value["schemaVersion"] == "1.0"
    assert value["system"]["memoryTotalBytes"] > 0
    assert value["tasks"]["total"] == 0
    assert value["streams"]["active"] == 0
    assert value["models"] == {
        "loaded": 0,
        "capacity": 4,
        "loadFailures": 0,
        "inferenceErrors": 0,
    }
    assert value["delivery"]["pendingEvents"] == 0

    metrics = client.get(
        "/v1/observability/prometheus",
        headers={"Authorization": "Bearer a-secure-runtime-key-for-tests"},
    )
    assert metrics.status_code == 200
    assert "linsight_ai_analysis_fps" in metrics.text
    assert "linsight_offline_queue_events" in metrics.text

    assert client.get("/v1/overlays/pending").status_code == 401
    overlays = client.get(
        "/v1/overlays/pending",
        headers={"X-Runtime-Key": "a-secure-runtime-key-for-tests"},
    )
    assert overlays.status_code == 200
    assert overlays.json() == []
