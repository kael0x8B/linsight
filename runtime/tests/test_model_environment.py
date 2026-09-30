import asyncio
from unittest.mock import AsyncMock, patch

from ai_runtime.app.model.environment import model_environment
from edge_agent.app.main import collect_runtime_health


def test_cpu_environment_does_not_advertise_accelerator(tmp_path):
    with (
        patch(
            "ai_runtime.app.model.environment._version",
            side_effect=lambda name: "1" if name == "onnxruntime" else None,
        ),
        patch("ai_runtime.app.model.environment.platform.system", return_value="Darwin"),
    ):
        result = model_environment(tmp_path / "compatible", tmp_path, tmp_path)
    assert result.formats == ["ONNX"]
    assert result.rknn_targets == []
    assert [provider.code for provider in result.providers] == ["onnxruntime"]
    assert result.providers[0].device_type == "CPU"


def test_linux_can_prepare_cpu_dependencies_without_torch_in_the_base_environment(tmp_path):
    with (
        patch("ai_runtime.app.model.environment._version", return_value=None),
        patch("ai_runtime.app.model.environment.platform.system", return_value="Linux"),
        patch("ai_runtime.app.model.environment.platform.machine", return_value="x86_64"),
    ):
        result = model_environment(tmp_path / "compatible", tmp_path, tmp_path)
    assert result.formats == ["ARCHIVE", "TORCHSCRIPT", "PYTORCH"]
    assert result.rknn_targets == []
    assert [provider.code for provider in result.providers] == ["python-cpu"]


def test_rknn_requires_matching_sdk_real_driver_and_explicit_soc(tmp_path):
    compatible = tmp_path / "compatible"
    compatible.write_bytes(b"vendor,board\x00rockchip,rk3566\x00")
    with (
        patch(
            "ai_runtime.app.model.environment._version",
            side_effect=lambda name: "2.3.2" if name == "rknn-toolkit-lite2" else None,
        ),
        patch("ai_runtime.app.model.environment.platform.system", return_value="Linux"),
        patch("ai_runtime.app.model.environment.platform.machine", return_value="aarch64"),
    ):
        assert "RKNN" not in model_environment(compatible, tmp_path, tmp_path).formats
        (tmp_path / "rknpu").touch()
        profile = model_environment(compatible, tmp_path, tmp_path)
        assert "RKNN" in profile.formats
        assert profile.rknn_targets == ["rk3566"]
        rknpu = next(provider for provider in profile.providers if provider.code == "rknpu2")
        assert rknpu.targets == ["rk3566"]
        assert rknpu.formats == ["RKNN", "ARCHIVE"]
        assert rknpu.runtime_version == "2.3.2"
        assert profile.model_dump(by_alias=True)["providers"][1]["deviceType"] == "NPU"
        compatible.write_bytes(b"vendor,board\x00")
        assert "RKNN" not in model_environment(compatible, tmp_path, tmp_path).formats


def test_agent_forwards_runtime_environment_and_drops_it_when_runtime_is_down():
    client = AsyncMock()
    profile = {
        "schemaVersion": "1.0",
        "formats": ["ONNX"],
        "rknnTargets": [],
        "providers": [
            {
                "code": "onnxruntime",
                "deviceType": "CPU",
                "vendor": "generic",
                "targets": ["aarch64"],
                "formats": ["ONNX"],
                "runtime": "onnxruntime",
                "runtimeVersion": "1.24.0",
            }
        ],
    }
    client.observability_snapshot.return_value = {"modelEnvironment": profile}
    assert asyncio.run(collect_runtime_health(client))["modelEnvironment"] == profile
    client.observability_snapshot.side_effect = RuntimeError("unavailable")
    assert asyncio.run(collect_runtime_health(client)) == {
        "runtimeStatus": "DOWN",
        "runtimeDiagnosticId": None,
    }
