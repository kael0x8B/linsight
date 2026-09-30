import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import SecretStr

from edge_agent.app.client.control_plane import (
    ModelCommandDetail,
    NodeCommandAssignment,
    TaskCommandDetail,
    UpgradeCommandDetail,
)
from edge_agent.app.command import executor as executor_module
from edge_agent.app.command.executor import ModelCommandExecutor
from edge_agent.app.core.identity import NodeIdentity


@pytest.mark.parametrize("status", [403, 404, 500])
def test_stream_download_http_failure_is_reported_without_reading_body_or_exposing_url(
    tmp_path, monkeypatch, status
):
    async def failed_download(*args):
        response = httpx.Response(
            status,
            request=httpx.Request("GET", "https://objects.invalid/model?secret=hidden"),
            stream=httpx.ByteStream(b"private storage error"),
        )
        response.raise_for_status()

    control_plane = AsyncMock()
    control_plane.get_model_command.return_value = ModelCommandDetail.model_validate(
        {
            "commandId": "download-failure",
            "commandType": "DEPLOY_MODEL",
            "configVersion": 1,
            "modelVersionId": 122,
            "artifactUrl": "https://objects.invalid/model?secret=hidden",
            "artifactName": "helmet.rknn",
            "artifactFormat": "RKNN",
            "trustedArtifact": True,
            "sha256": "a" * 64,
        }
    )
    runtime = AsyncMock()
    executor = ModelCommandExecutor(
        control_plane,
        runtime,
        NodeIdentity(node_id=5, tenant_id=1, credential=SecretStr("node-secret")),
        tmp_path,
    )
    monkeypatch.setattr(executor_module, "download_file", failed_download)
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "download-failure",
            "commandType": "DEPLOY_MODEL",
            "aggregateId": 27,
            "configVersion": 1,
            "idempotencyKey": "model-deploy:122:5:1",
        }
    )
    asyncio.run(executor.execute(command))
    result = control_plane.report_command.await_args.args[1]
    assert result["status"] == "FAILED"
    assert str(status) in result["errorMessage"]
    assert "hidden" not in str(result) and "private storage" not in str(result)
    runtime.deploy.assert_not_awaited()


@pytest.mark.parametrize("code", ["MODEL_CAPACITY_EXCEEDED", "MODEL_UNAVAILABLE", "UNKNOWN"])
def test_task_start_reports_safe_model_failure_reason(tmp_path, code):
    control_plane = AsyncMock()
    control_plane.get_task_command.return_value = TaskCommandDetail.model_validate(
        {
            "commandId": "task-start",
            "commandType": "START_TASK",
            "configVersion": 1,
            "taskId": 7,
            "runId": "11111111-1111-1111-1111-111111111111",
            "cameraId": 10,
            "algorithmId": 20,
            "pipelineVersionId": 30,
            "pipeline": {"schemaVersion": "1.0", "nodes": [], "edges": []},
            "modelVersionId": 40,
            "modelBindings": {"detector": 40},
            "parameters": {"schemaVersion": "1.0"},
            "streamUrl": "rtsp://camera.invalid/live",
            "streamUrls": {
                "MAIN": "rtsp://user:main-secret@camera.invalid/main",
                "SUB": "rtsp://camera.invalid/live",
            },
        }
    )
    runtime = AsyncMock()
    message = "请先停止其他任务或重新部署模型" if code != "UNKNOWN" else "private-details"
    runtime.start_task.return_value = {
        "taskId": 7,
        "status": "FAILED",
        "errorCode": code,
        "errorMessage": message,
    }
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(control_plane, runtime, identity, tmp_path)
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "task-start",
            "commandType": "START_TASK",
            "aggregateId": 7,
            "configVersion": 1,
            "idempotencyKey": "task:7:1",
        }
    )
    asyncio.run(executor.execute(command))
    assert runtime.start_task.await_args.args[0]["streamUrls"] == {
        "MAIN": "rtsp://user:main-secret@camera.invalid/main",
        "SUB": "rtsp://camera.invalid/live",
    }
    assert "main-secret" not in str(control_plane.get_task_command.return_value)
    report = control_plane.report_command.await_args.args[1]
    assert report["status"] == "FAILED"
    if code == "UNKNOWN":
        assert report["errorCode"] == "MODEL_COMMAND_FAILED"
        assert "private-details" not in str(report)
    else:
        assert report["errorCode"] == code
        assert report["errorMessage"] == message


def test_deploy_command_reports_stages_and_runtime_result(tmp_path, monkeypatch) -> None:
    artifact = tmp_path / "models" / "10" / "model.onnx"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"verified-model")

    async def fake_download(
        _url: str,
        target: Path,
        _max_bytes: int,
        _expected_sha256: str | None = None,
    ) -> Path:
        return artifact if target.name == "model.onnx" else target

    monkeypatch.setattr(executor_module, "download_file", fake_download)
    control_plane = AsyncMock()
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    control_plane.get_model_command.return_value = ModelCommandDetail.model_validate(
        {
            "commandId": "command-1",
            "commandType": "DEPLOY_MODEL",
            "configVersion": 1,
            "modelVersionId": 10,
            "artifactUrl": "https://objects.invalid/signed-model",
            "artifactName": "person.onnx",
            "artifactFormat": "ONNX",
            "trustedArtifact": True,
            "sha256": artifact_sha256,
            "runtimeManifest": {
                "schemaVersion": "1.0",
                "taskType": "OBJECT_DETECTION",
                "preprocess": {"color": "RGB", "layout": "NCHW", "dtype": "FLOAT32"},
                "decoder": {"type": "AUTO_DETECTION", "labels": ["person"]},
            },
        }
    )
    runtime = AsyncMock()
    runtime.deploy.return_value = {
        "modelVersionId": 10,
        "backend": "ONNX_RUNTIME",
        "device": "CPU",
        "reused": False,
    }
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(control_plane, runtime, identity, tmp_path)
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "command-1",
            "commandType": "DEPLOY_MODEL",
            "aggregateId": 30,
            "configVersion": 1,
            "idempotencyKey": "deploy:10:20:1",
        }
    )

    asyncio.run(executor.execute(command))

    reports = [call.args[1] for call in control_plane.report_command.await_args_list]
    assert [(item["status"], item["stage"]) for item in reports] == [
        ("RUNNING", "DOWNLOADING"),
        ("RUNNING", "VERIFYING"),
        ("RUNNING", "LOADING"),
        ("SUCCEEDED", "READY"),
    ]
    assert reports[-1]["backend"] == "ONNX_RUNTIME"
    assert reports[-1]["device"] == "CPU"
    assert runtime.deploy.await_args.args[0]["artifactFormat"] == "ONNX"
    assert runtime.deploy.await_args.args[0]["trustedArtifact"] is True
    assert runtime.deploy.await_args.args[0]["runtimeManifest"]["schemaVersion"] == "1.0"
    assert "adapter" not in runtime.deploy.await_args.args[0]
    assert "signed-model" not in str(reports)
    registry = json.loads((tmp_path / "models" / "deployed-models.json").read_text())
    assert registry == {
        "schemaVersion": 1,
        "models": [
            {
                "modelVersionId": 10,
                "artifactRelativePath": "models/10/model.onnx",
                "artifactFormat": "ONNX",
                "trustedArtifact": True,
                "sha256": artifact_sha256,
                "runtimeManifest": {
                    "schemaVersion": "1.0",
                    "taskType": "OBJECT_DETECTION",
                    "preprocess": {
                        "color": "RGB",
                        "layout": "NCHW",
                        "dtype": "FLOAT32",
                    },
                    "decoder": {"type": "AUTO_DETECTION", "labels": ["person"]},
                },
                "device": "CPU",
            }
        ],
    }
    assert "signed-model" not in json.dumps(registry)


def test_registry_ready_does_not_eagerly_load_models_before_commands(tmp_path) -> None:
    artifact = tmp_path / "models" / "10" / "model.onnx"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"verified-model")
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    registry = {
        "schemaVersion": 1,
        "models": [
            {
                "modelVersionId": 10,
                "artifactRelativePath": "models/10/model.onnx",
                "artifactFormat": "ONNX",
                "trustedArtifact": True,
                "sha256": sha256,
                "adapter": "person_detection_v1",
                "device": "CPU",
            }
        ],
    }
    (tmp_path / "models" / "deployed-models.json").write_text(json.dumps(registry))
    runtime = AsyncMock()
    runtime.deploy.return_value = {
        "modelVersionId": 10,
        "backend": "ONNX_RUNTIME",
        "device": "CPU",
        "reused": False,
    }
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(AsyncMock(), runtime, identity, tmp_path)

    restored = asyncio.run(executor.rehydrate_models())

    assert restored == 1
    runtime.deploy.assert_not_awaited()
    runtime.prepare_dependencies.assert_not_awaited()


def test_upgrade_command_downloads_verifies_and_activates_release(tmp_path, monkeypatch) -> None:
    package = tmp_path / "upgrades" / "command-upgrade.tar.gz"

    async def fake_download(
        _url: str,
        target: Path,
        max_bytes: int,
        expected_sha256: str | None = None,
    ) -> Path:
        assert max_bytes == 64 * 1024 * 1024
        assert expected_sha256 == "b" * 64
        return target

    monkeypatch.setattr(executor_module, "download_file", fake_download)
    control_plane = AsyncMock()
    control_plane.get_upgrade_command.return_value = UpgradeCommandDetail.model_validate(
        {
            "commandId": "command-upgrade",
            "commandType": "UPGRADE_AGENT",
            "configVersion": 2,
            "targetVersion": "1.1.0",
            "packageUrl": "https://objects.invalid/signed-release",
            "packageName": "edge-agent.tar.gz",
            "sha256": "b" * 64,
            "signature": "c" * 64,
        }
    )
    upgrade_manager = MagicMock()
    upgrade_manager.install.return_value = tmp_path / "releases" / "1.1.0"
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(control_plane, AsyncMock(), identity, tmp_path, upgrade_manager)
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "command-upgrade",
            "commandType": "UPGRADE_AGENT",
            "aggregateId": 40,
            "configVersion": 2,
            "idempotencyKey": "node-upgrade:20:2",
        }
    )

    asyncio.run(executor.execute(command))

    reports = [call.args[1] for call in control_plane.report_command.await_args_list]
    assert [(item["status"], item["stage"]) for item in reports] == [
        ("RUNNING", "DOWNLOADING"),
        ("RUNNING", "VERIFYING"),
        ("RUNNING", "INSTALLING"),
        ("SUCCEEDED", "ACTIVATING"),
    ]
    assert reports[-1]["result"] == {
        "currentVersion": "1.1.0",
        "restartRequired": True,
    }
    manifest = upgrade_manager.install.call_args.args[1]
    assert upgrade_manager.install.call_args.args[0] == package
    assert manifest.version == "1.1.0"
    assert manifest.signature == "c" * 64
    assert "signed-release" not in str(reports)


def test_rollback_command_switches_to_verified_previous_release(tmp_path) -> None:
    control_plane = AsyncMock()
    control_plane.get_upgrade_command.return_value = UpgradeCommandDetail.model_validate(
        {
            "commandId": "command-rollback",
            "commandType": "ROLLBACK_AGENT",
            "configVersion": 3,
        }
    )
    upgrade_manager = MagicMock()
    upgrade_manager.rollback.return_value = tmp_path / "releases" / "1.0.0"
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(control_plane, AsyncMock(), identity, tmp_path, upgrade_manager)
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "command-rollback",
            "commandType": "ROLLBACK_AGENT",
            "aggregateId": 41,
            "configVersion": 3,
            "idempotencyKey": "node-upgrade:20:3",
        }
    )

    asyncio.run(executor.execute(command))

    reports = [call.args[1] for call in control_plane.report_command.await_args_list]
    assert [(item["status"], item["stage"]) for item in reports] == [
        ("RUNNING", "ROLLING_BACK"),
        ("SUCCEEDED", "ROLLED_BACK"),
    ]
    assert reports[-1]["result"]["currentVersion"] == "1.0.0"
    upgrade_manager.rollback.assert_called_once_with()


def test_restart_node_command_is_acknowledged_before_host_action(tmp_path) -> None:
    control_plane = AsyncMock()
    lifecycle = MagicMock()
    lifecycle.schedule = AsyncMock(return_value={"accepted": True, "action": "restart"})
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(
        control_plane,
        AsyncMock(),
        identity,
        tmp_path,
        lifecycle_controller=lifecycle,
    )
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "command-restart",
            "commandType": "RESTART_NODE",
            "aggregateId": 20,
            "configVersion": 1,
            "idempotencyKey": "node-lifecycle:20:1",
        }
    )

    asyncio.run(executor.execute(command))

    reports = [call.args[1] for call in control_plane.report_command.await_args_list]
    assert [(item["status"], item["stage"]) for item in reports] == [
        ("RUNNING", "RESTARTING"),
        ("SUCCEEDED", "RESTARTING"),
    ]
    assert reports[-1]["result"] == {"accepted": True, "action": "restart"}
    lifecycle.schedule.assert_awaited_once_with("restart", "command-restart")


def test_shutdown_node_command_uses_fixed_request_file(tmp_path) -> None:
    from edge_agent.app.command.lifecycle import NodeLifecycleController

    request_file = tmp_path / "node-power-request"
    result = asyncio.run(
        NodeLifecycleController(request_file).schedule("shutdown", "command-shutdown")
    )

    assert request_file.read_text() == "shutdown\n"
    assert result == {"accepted": True, "action": "shutdown", "executionConfirmed": False}


def test_apply_task_settings_command_calls_runtime_and_reports_success(tmp_path) -> None:
    control_plane = AsyncMock()
    control_plane.get_task_command.return_value = TaskCommandDetail.model_validate(
        {
            "commandId": "settings-command",
            "commandType": "APPLY_TASK_SETTINGS",
            "configVersion": 3,
            "taskId": 7,
            "runId": "11111111-1111-1111-1111-111111111111",
            "cameraId": 10,
            "algorithmId": 20,
            "pipelineVersionId": 30,
            "pipeline": {"schemaVersion": "1.0", "nodes": [], "edges": []},
            "modelVersionId": 40,
            "parameters": {"schemaVersion": "1.0"},
            "globalSettingsVersion": 4,
            "globalSettings": {
                "schemaVersion": "1.0",
                "recordBeforeSeconds": 10,
                "recordAfterSeconds": 20,
                "defaultConfidence": 0.65,
                "defaultFps": 2.0,
                "evidenceStorageMode": "OBJECT_STORAGE",
                "evidenceRetentionDays": 30,
                "notificationsEnabled": True,
                "nodeOfflineThresholdSeconds": 60,
            },
        }
    )
    runtime = AsyncMock()
    runtime.apply_task_settings.return_value = {"taskId": 7, "status": "RUNNING"}
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(control_plane, runtime, identity, tmp_path)
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "settings-command",
            "commandType": "APPLY_TASK_SETTINGS",
            "aggregateId": 7,
            "configVersion": 3,
            "idempotencyKey": "global-settings:4:task:7",
        }
    )

    asyncio.run(executor.execute(command))

    runtime.apply_task_settings.assert_awaited_once()
    payload = runtime.apply_task_settings.await_args.args[0]
    assert payload["globalSettingsVersion"] == 4
    reports = [call.args[1] for call in control_plane.report_command.await_args_list]
    assert [(item["status"], item["stage"]) for item in reports] == [
        ("RUNNING", "APPLYING_SETTINGS"),
        ("SUCCEEDED", "SETTINGS_APPLIED"),
    ]


def test_rollback_redelivery_after_lost_ack_replays_result_without_second_switch(tmp_path):
    import httpx
    import pytest

    control_plane = AsyncMock()
    control_plane.get_upgrade_command.return_value = UpgradeCommandDetail.model_validate(
        {
            "commandId": "rollback-retry",
            "commandType": "ROLLBACK_AGENT",
            "configVersion": 2,
        }
    )
    manager = MagicMock()
    manager.rollback.return_value = tmp_path / "releases" / "1.0.0"
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "rollback-retry",
            "commandType": "ROLLBACK_AGENT",
            "aggregateId": 20,
            "configVersion": 2,
            "idempotencyKey": "rollback:20:2",
        }
    )
    control_plane.report_command.side_effect = [None, httpx.ConnectError("lost ack")]
    executor = ModelCommandExecutor(control_plane, AsyncMock(), identity, tmp_path, manager)
    with pytest.raises(httpx.ConnectError):
        asyncio.run(executor.execute(command))
    control_plane.report_command.side_effect = None
    recovered = ModelCommandExecutor(control_plane, AsyncMock(), identity, tmp_path, manager)
    asyncio.run(recovered.execute(command))
    manager.rollback.assert_called_once()
    assert control_plane.report_command.await_args.args[1]["status"] == "SUCCEEDED"


def test_face_session_redelivery_uses_receipt_and_cleans_reference(tmp_path, monkeypatch):
    from uuid import uuid4

    command_id = str(uuid4())
    control_plane = AsyncMock()
    control_plane.get_face_verification.return_value = {
        "sessionId": command_id,
        "referenceUrl": "https://objects.invalid/private-photo",
        "referenceSha256": "a" * 64,
        "modelVersionId": 130,
    }

    async def download(_url, target, _maximum, digest):
        assert digest == "a" * 64
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"photo")
        return target

    monkeypatch.setattr(executor_module, "download_file", download)
    runtime = AsyncMock()
    runtime.verify_face.return_value = {"status": "REFERENCE_INVALID", "reason": "NO_FACE"}
    identity = NodeIdentity(node_id=1, tenant_id=1, credential=SecretStr("test-only"))
    executor = ModelCommandExecutor(control_plane, runtime, identity, tmp_path)
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": command_id,
            "commandType": "VERIFY_FACE",
            "aggregateId": 1,
            "configVersion": 1,
            "idempotencyKey": "face:1",
        }
    )
    asyncio.run(executor.execute(command))
    asyncio.run(executor.execute(command))
    assert runtime.verify_face.await_count == 1
    assert not list((tmp_path / "face-verification").glob("*.jpg"))
    reports = [call.args[1] for call in control_plane.report_command.await_args_list]
    assert reports[-1]["status"] == "SUCCEEDED"
    assert "private-photo" not in str(reports)
    assert "referenceUrl" not in runtime.verify_face.await_args.args[0]


def test_uninstall_does_not_download_or_reload_model_and_replays_receipt(tmp_path):
    control = AsyncMock()
    runtime = AsyncMock()
    control.get_model_command.return_value = ModelCommandDetail.model_validate(
        {
            "commandId": "remove-1",
            "commandType": "UNINSTALL_MODEL",
            "configVersion": 2,
            "modelVersionId": 10,
            "artifactUrl": "",
            "artifactName": "model.onnx",
            "artifactFormat": "ONNX",
            "sha256": "f" * 64,
        }
    )
    runtime.gateway_rpc.return_value = {"ok": True, "data": {"removed": True}}
    identity = NodeIdentity(node_id=20, tenant_id=1, credential=SecretStr("node-secret"))
    executor = ModelCommandExecutor(control, runtime, identity, tmp_path)
    command = NodeCommandAssignment(
        commandId="remove-1",
        commandType="UNINSTALL_MODEL",
        aggregateId=30,
        configVersion=2,
        idempotencyKey="remove:10:20:2",
    )
    asyncio.run(executor.execute(command))
    asyncio.run(executor.execute(command))
    runtime.gateway_rpc.assert_awaited_once()
    runtime.deploy.assert_not_awaited()
    assert control.report_command.await_args.args[1]["stage"] == "REMOVED"
