import asyncio
import hashlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr, ValidationError
from test_model_pool import _write_contract_model

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.main import create_app
from ai_runtime.app.model import dependencies as module
from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestParameters
from ai_runtime.app.model.dependencies import (
    PROFILE,
    DependencyFailure,
    DependencyManager,
    DependencyRequest,
)
from ai_runtime.app.model.isolated import IsolatedAdapter
from edge_agent.app.client.control_plane import NodeCommandAssignment
from edge_agent.app.command.executor import ModelCommandExecutor, ModelDependencyError
from edge_agent.app.core.identity import NodeIdentity


def test_no_model_supplied_packages_or_indexes():
    with pytest.raises(ValidationError):
        DependencyRequest(artifactFormat="PYTORCH", requirements=["attacker-package"])
    with pytest.raises(ValidationError):
        DependencyRequest(artifactFormat="EXECUTE_SCRIPT")


def test_onnx_never_installs(tmp_path):
    manager = DependencyManager(tmp_path)
    assert manager.start(DependencyRequest(artifactFormat="ONNX")).status == "READY"
    assert manager._task is None
    assert not manager.root.exists()


def test_concurrent_prepare_reuses_one_compatible_environment(tmp_path, monkeypatch):
    manager = DependencyManager(tmp_path)
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(manager, "_check", check)
    run = AsyncMock()
    monkeypatch.setattr(manager, "_run", run)

    async def exercise():
        results = await asyncio.gather(manager.ensure("PYTORCH"), manager.ensure("TORCHSCRIPT"))
        assert results == [Path(sys.executable)] * 2
        assert manager.start(DependencyRequest(artifactFormat="PYTORCH")).status == "READY"

    asyncio.run(exercise())
    check.assert_awaited_once()
    run.assert_not_awaited()


def test_missing_dependencies_only_write_profile_and_use_cached_wheels(tmp_path, monkeypatch):
    manager = DependencyManager(tmp_path)
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(manager, "_check", AsyncMock(side_effect=[False, True]))
    run = AsyncMock()
    monkeypatch.setattr(manager, "_run", run)
    python = asyncio.run(manager.ensure("PYTORCH"))
    assert python == manager.root / PROFILE / "bin" / "python"
    args = [call.args[0] for call in run.await_args_list]
    from ai_runtime.app.core import environment as environment_bootstrap

    assert args[0] == [sys.executable, "-I", str(environment_bootstrap.__file__),
                       str(manager.root / PROFILE)]
    assert "--no-index" in args[1]
    assert args[1][0] == str(python)
    assert "ultralytics==8.4.142" in args[1]
    assert "torch==2.14.0+cpu" in args[1]
    assert list((manager.root / PROFILE).rglob("linsight-runtime-base.pth"))


def test_failed_job_is_visible_and_explicit_retry_recovers(tmp_path, monkeypatch):
    manager = DependencyManager(tmp_path)
    attempts = 0

    async def install():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise DependencyFailure("DEPENDENCY_DISK_LOW", "磁盘空间不足")
        manager._python = Path(sys.executable)

    monkeypatch.setattr(manager, "_install", install)

    async def exercise():
        with pytest.raises(DependencyFailure, match="磁盘空间不足"):
            await manager.ensure("PYTORCH")
        assert manager.status(PROFILE).error_code == "DEPENDENCY_DISK_LOW"
        assert attempts == 1
        await manager.ensure("PYTORCH")
        assert manager.status(PROFILE).status == "READY"
        assert manager.status(PROFILE).error_code is None

    asyncio.run(exercise())


def test_low_disk_never_creates_or_modifies_environment(tmp_path, monkeypatch):
    manager = DependencyManager(tmp_path)
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(manager, "_check", AsyncMock(return_value=False))
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 1})())
    run = AsyncMock()
    monkeypatch.setattr(manager, "_run", run)
    with pytest.raises(DependencyFailure, match="磁盘"):
        asyncio.run(manager.ensure("PYTORCH"))
    run.assert_not_awaited()


def test_prepare_api_requires_auth_and_rejects_arbitrary_inputs(tmp_path):
    client = TestClient(
        create_app(
            RuntimeSettings(
                api_key="dependency-api-test-key-long-enough", runtime_data_root=tmp_path
            )
        )
    )
    url = "/v1/models/dependencies/prepare"
    assert client.post(url, json={"artifactFormat": "ONNX"}).status_code == 401
    headers = {"X-Runtime-Key": "dependency-api-test-key-long-enough"}
    assert (
        client.post(url, json={"artifactFormat": "ONNX"}, headers=headers).json()["status"]
        == "READY"
    )
    assert (
        client.post(
            url, json={"artifactFormat": "PYTORCH", "index": "evil"}, headers=headers
        ).status_code
        == 422
    )
    assert client.get("/v1/models/dependencies/not-a-profile", headers=headers).status_code == 404


def test_agent_reports_preparation_stages_and_waits_for_ready(tmp_path, monkeypatch):
    runtime = AsyncMock()
    runtime.prepare_dependencies.return_value = {
        "profile": PROFILE,
        "status": "RUNNING",
        "stage": "INSTALLING_DEPS",
    }
    runtime.dependency_status.side_effect = [
        {"profile": PROFILE, "status": "RUNNING", "stage": "VERIFYING_ENV"},
        {"profile": PROFILE, "status": "READY", "stage": "ENV_READY"},
    ]
    cp = AsyncMock()
    executor = ModelCommandExecutor(
        cp, runtime, NodeIdentity(node_id=1, tenant_id=1, credential=SecretStr("secret")), tmp_path
    )
    command = NodeCommandAssignment.model_validate(
        {
            "commandId": "deploy-1",
            "commandType": "DEPLOY_MODEL",
            "aggregateId": 1,
            "configVersion": 1,
            "idempotencyKey": "deploy:1:1:1",
        }
    )
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    asyncio.run(executor._prepare_dependencies("PYTORCH", command, "diagnostic"))
    assert [call.args[1]["stage"] for call in cp.report_command.await_args_list] == [
        "CHECKING_ENV",
        "INSTALLING_DEPS",
        "VERIFYING_ENV",
    ]
    runtime.prepare_dependencies.return_value = {
        "status": "FAILED",
        "errorCode": "DEPENDENCY_DISK_LOW",
        "errorMessage": "磁盘空间不足",
    }
    with pytest.raises(ModelDependencyError, match="磁盘空间不足"):
        asyncio.run(executor._prepare_dependencies("PYTORCH"))


def test_real_isolated_worker_infers_and_closes(tmp_path):
    path = tmp_path / "person.onnx"
    _write_contract_model(path)
    image = tmp_path / "input.png"
    Image.new("RGB", (320, 180)).save(image)
    adapter = IsolatedAdapter(
        Path(sys.executable),
        DeployModelRequest(
            modelVersionId=1,
            artifactPath=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            adapter="person_detection_v1",
        ),
    )
    try:
        result = adapter.infer(
            str(image),
            ModelTestParameters.model_validate(
                {
                    "schemaVersion": "1.0",
                    "confidence": 0.5,
                    "nmsThreshold": 0.5,
                    "inputWidth": 32,
                    "inputHeight": 32,
                    "outputCoordinates": "NORMALIZED_XYWH",
                }
            ),
        )
        assert result.source_width == 320
        assert result.objects[0].class_name == "person"
        assert result.objects[0].bbox.x == pytest.approx(0.1)
    finally:
        adapter.close()
    assert adapter._process.poll() is not None


def test_dead_worker_is_not_reused_as_ready(tmp_path, monkeypatch):
    from ai_runtime.app.model import pool as pool_module

    workers = []

    class Worker:
        backend = "PYTORCH_CPU"
        alive = True

        def __init__(self, *_):
            workers.append(self)

        def close(self):
            self.alive = False

    monkeypatch.setattr(pool_module, "IsolatedAdapter", Worker)
    manager = AsyncMock()
    manager.ensure.return_value = Path(sys.executable)
    pool = pool_module.ModelPool(dependencies=manager)
    artifact = tmp_path / "model.pt"
    artifact.write_bytes(b"model")
    request = DeployModelRequest(
        modelVersionId=1,
        artifactPath=artifact,
        artifactFormat="PYTORCH",
        sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        adapter="person_detection_v1",
    )

    async def exercise():
        await pool.deploy(request)
        assert (await pool.deploy(request)).reused
        workers[0].alive = False
        assert not pool.is_loaded(1)
        assert not (await pool.deploy(request)).reused
        assert len(workers) == 2
        await pool.close()

    asyncio.run(exercise())
