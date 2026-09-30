import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_model_residency import registered, settings, task_config
from test_task_manager import FakeSharedStream

from ai_runtime.app.gateway.service import (
    GatewayCapacityExceeded,
    GatewayCapacityPreflight,
    GatewayService,
)
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.task.manager import TaskManager


def memory(total_mib: int, available_mib: int):
    return SimpleNamespace(total=total_mib * 1024**2, available=available_mib * 1024**2)


def test_shared_models_are_deduplicated_by_running_task_on_one_node(tmp_path, monkeypatch):
    async def scenario():
        registered(tmp_path, [1, 2, 3])
        monkeypatch.setattr(
            "ai_runtime.app.model.pool.psutil.virtual_memory", lambda: memory(8192, 6144)
        )
        pool = ModelPool(max_models=4)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        gateway = GatewayService(settings(tmp_path), pool, manager)
        try:
            await gateway.platform_start(task_config(1, [1, 2]), 0)
            report = await gateway.capacity_preflight(
                GatewayCapacityPreflight(taskId=2, modelVersionIds=[2, 3, 2])
            )
            assert report["allowed"]
            assert report["currentSlotCount"] == 2
            assert report["projectedSlotCount"] == 3
            assert report["sharedModelCount"] == 1
            shared = next(value for value in report["models"] if value["modelVersionId"] == 2)
            assert shared["shared"] and shared["taskIds"] == [1, 2]
        finally:
            await gateway.close()
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_slot_preflight_blocks_start_before_desired_configuration_is_written(tmp_path, monkeypatch):
    async def scenario():
        registered(tmp_path, [1, 2, 3, 4, 5])
        monkeypatch.setattr(
            "ai_runtime.app.model.pool.psutil.virtual_memory", lambda: memory(8192, 6144)
        )
        pool = ModelPool(max_models=4)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        gateway = GatewayService(settings(tmp_path), pool, manager)
        first = task_config(1, [1, 2])
        try:
            await gateway.platform_start(first, 0)
            with pytest.raises(GatewayCapacityExceeded) as rejected:
                await gateway.platform_start(task_config(2, [3, 4, 5]), 0)
            report = rejected.value.report
            assert report["projectedSlotCount"] == 5
            assert report["slotLimit"] == 4
            assert "任务 1" in report["message"] and "模型#1" in report["message"]
            assert "任务 #2" in report["message"] and "模型#5" in report["message"]
            assert gateway.store.get(2) is None
            assert manager.statuses()[0].task_id == 1
            assert manager.statuses()[0].status == "RUNNING"
        finally:
            await gateway.close()
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_memory_preflight_uses_safe_reserve_and_does_not_stop_running_task(tmp_path, monkeypatch):
    async def scenario():
        registered(tmp_path, [1, 2])
        samples = iter((memory(1024, 620), memory(1024, 550)))
        monkeypatch.setattr(
            "ai_runtime.app.model.pool.psutil.virtual_memory", lambda: next(samples)
        )
        pool = ModelPool(max_models=4)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        gateway = GatewayService(settings(tmp_path), pool, manager)
        first = task_config(1, [1])
        try:
            await gateway.platform_start(first, 0)
            before = gateway.task(1)
            with pytest.raises(GatewayCapacityExceeded) as rejected:
                await gateway.platform_start(task_config(2, [2]), 0)
            report = rejected.value.report
            assert report["projectedSlotCount"] == 2
            assert report["memoryAvailableAfterBytes"] < report["memorySafetyReserveBytes"]
            assert "安全保留" in report["message"]
            assert gateway.task(1)["revision"] == before["revision"]
            assert gateway.status(1).status == "RUNNING"
            assert gateway.store.get(2) is None
        finally:
            await gateway.close()
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_running_task_replacement_budgets_old_and_new_models_before_handover(tmp_path, monkeypatch):
    async def scenario():
        registered(tmp_path, [1, 2, 3, 4, 5])
        monkeypatch.setattr(
            "ai_runtime.app.model.pool.psutil.virtual_memory", lambda: memory(8192, 6144)
        )
        pool = ModelPool(max_models=4)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        gateway = GatewayService(settings(tmp_path), pool, manager)
        first = task_config(1, [1, 2, 3, 4])
        replacement = task_config(1, [5]).model_copy(
            update={"config_version": 2, "run_id": str(uuid4())}
        )
        try:
            await gateway.platform_start(first, 0)
            before = gateway.task(1)
            with pytest.raises(GatewayCapacityExceeded) as rejected:
                await gateway.platform_start(replacement, 1)
            assert rejected.value.report["projectedSlotCount"] == 5
            assert rejected.value.report["conflictTasks"][0]["taskId"] == 1
            assert gateway.task(1)["revision"] == before["revision"]
            assert gateway.status(1).status == "RUNNING"
            assert manager.running_requests()[0].run_id == first.run_id
        finally:
            await gateway.close()
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_stop_restart_reuses_resident_models_without_double_charging_memory(tmp_path, monkeypatch):
    async def scenario():
        registered(tmp_path, [1, 2, 3, 4])
        available_mib = 850
        monkeypatch.setattr(
            "ai_runtime.app.model.pool.psutil.virtual_memory",
            lambda: memory(2048, available_mib),
        )
        pool = ModelPool(max_models=4)
        manager = TaskManager(settings(tmp_path), pool, FakeSharedStream)
        gateway = GatewayService(settings(tmp_path), pool, manager)
        first = task_config(1, [1, 2, 3])
        try:
            await gateway.platform_start(first, 0)
            await gateway.platform_stop(1, first.run_id, 1)
            assert all(pool.is_loaded(model) for model in [1, 2, 3])
            # The three warm adapters are already counted in used system memory.
            available_mib = 550
            report = await gateway.capacity_preflight(GatewayCapacityPreflight(taskId=1))
            assert report["allowed"]
            assert report["currentSlotCount"] == 0
            assert report["projectedSlotCount"] == 3
            assert report["memoryAvailableAfterBytes"] == 550 * 1024**2
            assert report["memorySafetyReserveBytes"] == 512 * 1024**2
            # An additional cold model still requires its own memory budget.
            cold = await gateway.capacity_preflight(
                GatewayCapacityPreflight(taskId=2, modelVersionIds=[4])
            )
            assert not cold["allowed"]
            assert cold["memoryAvailableAfterBytes"] == (550 - 64) * 1024**2
            restarted = first.model_copy(update={"run_id": str(uuid4())})
            result = await gateway.platform_start(restarted, 2)
            assert result.status == "RUNNING"
            assert gateway.task(1)["revision"] == 3
            assert pool.size == 3
            # Reuse does not permit starting when actual free memory is too low.
            available_mib = 500
            low = await gateway.capacity_preflight(GatewayCapacityPreflight(taskId=1))
            assert not low["allowed"]
            assert gateway.status(1).status == "RUNNING"
        finally:
            await gateway.close()
            await manager.close()
            await pool.close()

    asyncio.run(scenario())


def test_preflight_does_not_credit_memory_for_models_that_remain_cached(tmp_path, monkeypatch):
    async def scenario():
        registry, _ = registered(tmp_path, [1, 2])
        pool = ModelPool(max_models=4)
        monkeypatch.setattr(
            "ai_runtime.app.model.pool.psutil.virtual_memory", lambda: memory(2048, 550)
        )
        try:
            lease = await pool.acquire([1], registry)
            await pool.release(lease)
            report = await pool.capacity_preflight([1], [2], registry)
            assert not report.allowed
            assert report.memory_available_after_bytes == (550 - 64) * 1024**2
            assert pool.is_loaded(1)
        finally:
            await pool.close()

    asyncio.run(scenario())
