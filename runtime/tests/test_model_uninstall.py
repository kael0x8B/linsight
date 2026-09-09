import asyncio
import hashlib
from uuid import uuid4

import pytest
from test_gateway_autonomy import settings_for
from test_model_pool import _write_contract_model
from test_task_manager import FakeSharedStream

from ai_runtime.app.gateway.service import GatewayService
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.model.deployed import DeployedModelRegistry
from ai_runtime.app.model.pool import ModelCapacityError, ModelPool
from ai_runtime.app.task.manager import TaskManager


def test_uninstall_rejects_active_lease_and_replay_does_not_remove_reinstallation(tmp_path):
    async def scenario():
        root = tmp_path / "models"
        root.mkdir()
        artifact = root / "detector.onnx"
        _write_contract_model(artifact)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        registry = DeployedModelRegistry(tmp_path)
        pool = ModelPool(registry=registry)
        request = DeployModelRequest(
            modelVersionId=101,
            artifactPath=artifact,
            sha256=digest,
            adapter="person_detection_v1",
            device="CPU",
        )
        await pool.deploy(request)
        registry.record(request.model_dump(by_alias=True))
        lease = await pool.acquire([101])
        request_id = str(uuid4())
        with pytest.raises(ModelCapacityError):
            await pool.uninstall(101, digest, request_id, registry)
        assert artifact.exists() and registry.summaries()
        await pool.release(lease)
        with pytest.raises(ValueError):
            await pool.uninstall(101, "f" * 64, request_id, registry)
        assert artifact.exists()
        await pool.uninstall(101, digest, request_id, registry)
        assert not registry.summaries() and not artifact.exists() and pool.size == 0
        _write_contract_model(artifact)
        await pool.deploy(request)
        registry.record(request.model_dump(by_alias=True))
        await pool.uninstall(101, digest, request_id, registry)
        assert artifact.exists() and registry.summaries() and pool.size == 1
        with pytest.raises(ValueError):
            await pool.uninstall(102, digest, request_id, registry)
        await pool.close()

    asyncio.run(scenario())


def test_enabled_configuration_and_entrance_block_model_removal(tmp_path):
    async def scenario():
        settings = settings_for(tmp_path)
        pool = ModelPool()
        manager = TaskManager(settings, pool, FakeSharedStream)
        gateway = GatewayService(settings, pool, manager)
        gateway.store.save(
            {
                "config": {
                    "taskId": 1,
                    "modelVersionId": 10,
                    "modelBindings": {"person": 10, "ppe": 20},
                },
                "revision": 1,
                "enabled": True,
            },
            str(uuid4()),
            "test",
        )
        with pytest.raises(ValueError, match="先停止"):
            await gateway.uninstall_model(20, "f" * 64, str(uuid4()))
        gateway.external_model_in_use = lambda model_id: model_id == 30
        with pytest.raises(ValueError, match="入口识别"):
            await gateway.uninstall_model(30, "f" * 64, str(uuid4()))
        await gateway.close()
        await manager.close()
        await pool.close()

    asyncio.run(scenario())
