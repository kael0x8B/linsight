"""Regression coverage for bounded model residency across task and inference lifetimes."""

import asyncio
import hashlib
import threading
from uuid import uuid4

import pytest
from PIL import Image
from test_model_pool import _write_contract_model
from test_task_manager import FakeSharedStream, request

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.gateway.service import GatewayCapacityExceeded, GatewayService
from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestRequest
from ai_runtime.app.model.deployed import DeployedModelRegistry
from ai_runtime.app.model.pool import ModelCapacityError, ModelPool, ModelUnavailableError
from ai_runtime.app.task.manager import CapturedFrame, TaskManager


def registered(root, ids):
    path = root / "models" / "person.onnx"
    path.parent.mkdir(exist_ok=True)
    _write_contract_model(path)
    registry = DeployedModelRegistry(root)
    values = {}
    for model_id in ids:
        value = DeployModelRequest(
            modelVersionId=model_id,
            artifactPath=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            adapter="person_detection_v1",
        )
        registry.record(value.model_dump(mode="json", by_alias=True, exclude_none=True))
        values[model_id] = value
    return registry, values


def task_config(task_id, ids):
    return request(task_id, str(uuid4())).model_copy(
        update={
            "model_version_id": ids[0],
            "model_bindings": {f"detector-{index}": value for index, value in enumerate(ids)},
        }
    )


def settings(root):
    return RuntimeSettings(
        api_key="test-runtime-key-at-least-24-characters", runtime_data_root=root
    )


def test_thirteen_registered_models_start_two_tasks_in_four_slots(tmp_path):
    async def scenario():
        registry, values = registered(tmp_path, range(121, 134))
        pool = ModelPool(max_models=4)
        # Reproduce the old restart order: the last four versions evicted both PPE tasks.
        for value in values.values():
            await pool.deploy(value)
        assert not pool.is_loaded(121) and not pool.is_loaded(125)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        helmet, vest = task_config(2, [121, 122]), task_config(6, [125])
        try:
            await manager.start_task(helmet)
            await manager.start_task(vest)
            # Replayed commands must not take an extra lease.
            await manager.start_task(helmet)
            for model_id in (126, 127, 128, 129, 130):
                await pool.deploy(values[model_id])
            assert all(pool.is_loaded(i) for i in (121, 122, 125))
            assert pool.size == 4
            assert len(manager._streams) == 1
            await manager.stop_task(2, helmet.run_id)
            await pool.deploy(values[131])
            await pool.deploy(values[132])
            assert not pool.is_loaded(121) and not pool.is_loaded(122)
            assert pool.is_loaded(125)
            assert len(registry.summaries()) == 13
        finally:
            await manager.close()
            assert not pool._pins
            await pool.close()

    asyncio.run(scenario())


def test_partial_cache_batch_protects_the_already_loaded_dependency(tmp_path):
    async def scenario():
        registry, values = registered(tmp_path, [1, 2, 3])
        pool = ModelPool(max_models=2)
        try:
            await pool.deploy(values[1])
            await pool.deploy(values[3])
            lease = await pool.acquire([1, 2, 1], registry)
            assert pool.is_loaded(1) and pool.is_loaded(2)
            with pytest.raises(ModelCapacityError):
                await pool.deploy(values[3])
            await pool.release(lease)
            await pool.deploy(values[3])
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_capacity_rejection_keeps_other_tasks_running_and_reports_actionable_reason(tmp_path):
    async def scenario():
        _, values = registered(tmp_path, [1, 2, 3])
        pool = ModelPool(max_models=2)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        gateway = GatewayService(settings(tmp_path), pool, manager)
        first = task_config(1, [1, 2])
        try:
            await manager.start_task(first)
            with pytest.raises(GatewayCapacityExceeded, match="2") as rejected:
                await gateway.platform_start(task_config(2, [3]), 0)
            assert rejected.value.report["code"] == "MODEL_CAPACITY_EXCEEDED"
            assert rejected.value.report["conflictTasks"][0]["taskId"] == 1
            assert gateway.store.get(2) is None
            assert manager.statuses()[0].status == "RUNNING"
            assert pool.is_loaded(1) and pool.is_loaded(2)
            await manager.stop_task(1, first.run_id)
            await gateway.platform_start(task_config(2, [3]), 0)
            assert gateway.status(2).status == "RUNNING"
            assert pool.is_loaded(3)
        finally:
            await gateway.close()
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_shared_model_is_pinned_until_last_task_stops(tmp_path):
    async def scenario():
        _, values = registered(tmp_path, [1, 2])
        pool = ModelPool(max_models=1)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        a, b = task_config(1, [1]), task_config(2, [1])
        try:
            await manager.start_task(a)
            await manager.start_task(b)
            await manager.stop_task(1, a.run_id)
            with pytest.raises(ModelCapacityError):
                await pool.deploy(values[2])
            await manager.stop_task(2, b.run_id)
            await pool.deploy(values[2])
        finally:
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_failed_start_and_failed_inference_release_task_models(tmp_path):
    class FailedStream(FakeSharedStream):
        async def start(self):
            raise OSError("stream unavailable")

    async def scenario():
        _, values = registered(tmp_path, [1, 2])
        pool = ModelPool(max_models=1)
        failed = TaskManager(settings(tmp_path), pool, FailedStream)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        try:
            with pytest.raises(OSError):
                await failed.start_task(task_config(1, [1]))
            assert not pool._pins and not failed._streams
            await manager.start_task(task_config(2, [1]))
            runner = manager._tasks[2]
            runner.queue.put_nowait(CapturedFrame(b"invalid-image", 1788830000000))
            await asyncio.wait_for(runner._task, 2)
            assert runner.status == "FAILED"
            await pool.deploy(values[2])
            assert not pool._pins
        finally:
            await failed.close()
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_missing_and_corrupt_artifacts_do_not_leak_reservations(tmp_path):
    async def scenario():
        registry, values = registered(tmp_path, [1, 2])
        pool = ModelPool(max_models=2)
        try:
            with pytest.raises(ModelUnavailableError, match="未部署"):
                await pool.acquire([1, 99], registry)
            assert not pool._pins and pool.size == 0
            values[1].artifact_path.write_bytes(b"corrupted")
            with pytest.raises(ModelUnavailableError, match="校验失败"):
                await pool.acquire([1], registry)
            assert not pool._pins and pool.size == 0
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_cancelled_native_inference_cannot_be_evicted_until_worker_finishes(tmp_path, monkeypatch):
    async def scenario():
        _, values = registered(tmp_path, [1, 2])
        pool = ModelPool(max_models=1)
        entered, finish = threading.Event(), threading.Event()
        try:
            await pool.deploy(values[1])
            adapter = pool._entries[(1, "CPU")].adapter

            def slow_infer(*args):
                entered.set()
                assert finish.wait(3)
                return "done"

            monkeypatch.setattr(adapter, "infer", slow_infer)
            image = tmp_path / "input.png"
            Image.new("RGB", (32, 32)).save(image)
            call = asyncio.create_task(
                pool.test(
                    ModelTestRequest.model_validate(
                        {
                            "modelVersionId": 1,
                            "imagePath": str(image),
                            "parameters": {
                                "schemaVersion": "1.0",
                                "inputWidth": 32,
                                "inputHeight": 32,
                                "confidence": 0.5,
                                "nmsThreshold": 0.5,
                                "outputCoordinates": "NORMALIZED_XYWH",
                            },
                        }
                    )
                )
            )
            assert await asyncio.to_thread(entered.wait, 2)
            call.cancel()
            await asyncio.sleep(0)
            with pytest.raises(ModelCapacityError):
                await pool.deploy(values[2])
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await call
            await pool.deploy(values[2])
            assert not pool._pins
        finally:
            finish.set()
            await pool.close()

    asyncio.run(scenario())


def test_model_test_loads_from_cold_registry(tmp_path):
    async def scenario():
        registry, _ = registered(tmp_path, [1])
        pool = ModelPool(max_models=1, registry=registry)
        image = tmp_path / "input.png"
        Image.new("RGB", (32, 32)).save(image)
        try:
            result = await pool.test(
                ModelTestRequest.model_validate(
                    {
                        "modelVersionId": 1,
                        "imagePath": str(image),
                        "parameters": {
                            "schemaVersion": "1.0",
                            "inputWidth": 32,
                            "inputHeight": 32,
                            "confidence": 0.5,
                            "nmsThreshold": 0.5,
                            "outputCoordinates": "NORMALIZED_XYWH",
                        },
                    }
                )
            )
            assert result.objects[0].class_name == "person"
            assert pool.is_loaded(1) and not pool._pins
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_failed_batch_load_preserves_other_leases(tmp_path, monkeypatch):
    async def scenario():
        registry, _ = registered(tmp_path, [1, 2, 3])
        pool = ModelPool(max_models=3)
        construct = pool._construct_adapter

        def fail_third(value, python, digest):
            if value.model_version_id == 3:
                raise ValueError("unsupported artifact")
            return construct(value, python, digest)

        monkeypatch.setattr(pool, "_construct_adapter", fail_third)
        try:
            lease = await pool.acquire([1], registry)
            with pytest.raises(ValueError, match="unsupported artifact"):
                await pool.acquire([2, 3], registry)
            assert dict(pool._pins) == {(1, "CPU"): 1}
            assert pool.is_loaded(1)
            await pool.release(lease)
            assert not pool._pins
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_cancelled_loader_closes_new_adapter_and_releases_reservations(tmp_path, monkeypatch):
    async def scenario():
        registry, _ = registered(tmp_path, [1])
        pool = ModelPool(max_models=1)
        entered, finish = threading.Event(), threading.Event()
        adapter = object()
        closed = []

        def slow_load(*args):
            entered.set()
            assert finish.wait(3)
            return adapter, "test"

        async def close(value):
            closed.append(value)

        monkeypatch.setattr(pool, "_construct_adapter", slow_load)
        monkeypatch.setattr(pool, "_close_adapter", close)
        call = asyncio.create_task(pool.acquire([1], registry))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            call.cancel()
            await asyncio.sleep(0)
            assert not call.done()
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await call
            assert closed == [adapter]
            assert not pool._pins and pool.size == 0
        finally:
            finish.set()
            await pool.close()

    asyncio.run(scenario())
