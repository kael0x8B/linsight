"""One mutation boundary for platform commands and the two management entrances."""

import asyncio
import hashlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ai_runtime.app.gateway.store import GatewayStore
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.model.deployed import DeployedModelRegistry
from ai_runtime.app.model.pool import ModelCapacityError, ModelUnavailableError
from ai_runtime.app.task.contracts import TaskSettingsApplyRequest, TaskStartRequest, TaskStatus
from ai_runtime.app.task.manager import _validate_pipeline

LOGGER = logging.getLogger("linsight.gateway")


class GatewayConflict(ValueError):
    pass


class GatewayChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: int = Field(alias="taskId", gt=0)
    expected_revision: int = Field(alias="expectedRevision", ge=0)
    request_id: UUID = Field(alias="requestId")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    configuration: dict | None = None


class GatewayService:
    def __init__(self, settings, pool, tasks):
        self.settings, self.pool, self.tasks = settings, pool, tasks
        self.store = GatewayStore(settings.runtime_data_root / "gateway")
        self.models = DeployedModelRegistry(settings.runtime_data_root)
        self._set_local_tasks()
        self._lock = asyncio.Lock()
        self._model_lock = asyncio.Lock()
        self._errors: dict[int, tuple[str, str]] = {}
        self._applied: dict[int, int] = {}
        self._worker: asyncio.Task | None = None

    def _set_local_tasks(self):
        self.tasks.event_store.local_task_ids = {
            document["config"]["taskId"]
            for document in self.store.all()
            if not document.get("platformManaged", True)
        }

    async def start(self):
        self._worker = asyncio.create_task(self._recover_loop(), name="gateway-recovery")

    async def close(self):
        if self._worker:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
        self.store.close()

    async def _recover_loop(self):
        while True:
            try:
                await self.reconcile()
                self.tasks.event_store.prune_history(self.settings.gateway_history_days)
            except Exception as error:
                LOGGER.warning("Gateway recovery deferred errorType=%s", type(error).__name__)
            await asyncio.sleep(5)

    async def reconcile(self):
        async with self._lock:
            for document in self.store.all():
                task_id = document["config"]["taskId"]
                states = {item.task_id: item.status for item in self.tasks.statuses()}
                if self._applied.get(task_id) == document["revision"] and (
                    not document["enabled"] or states.get(task_id) == "RUNNING"
                ):
                    continue
                await self._apply(document)

    def _validate(self, raw: dict) -> TaskStartRequest:
        config = TaskStartRequest.model_validate(raw)
        _validate_pipeline(config.pipeline, config.rule is not None, config.parameters)
        # Validate the complete graph before stopping any currently working task.
        return config

    async def uninstall_model(self, model_id: int, sha256: str, request_id: str):
        async with self._lock, self._model_lock:
            if self.models.removal_completed(request_id, model_id, sha256):
                return {"removed": True}
            for document in self.store.all():
                config = document["config"]
                if document["enabled"] and model_id in {
                    config.get("modelVersionId"),
                    *config.get("modelBindings", {}).values(),
                }:
                    raise ValueError("模型被已启用的识别任务使用，请先停止关联任务")
            if getattr(self, "external_model_in_use", lambda _: False)(model_id):
                raise ValueError("模型被入口识别使用，请先停止入口识别")
            await self.pool.uninstall(model_id, sha256, request_id, self.models)
            return {"removed": True}

    async def deploy_model(self, request: DeployModelRequest, require_new: bool = False):
        async with self._model_lock:
            existing = next(
                (
                    item
                    for item in self.models.summaries()
                    if item["modelVersionId"] == request.model_version_id
                ),
                None,
            )
            if existing and (require_new or existing["sha256"] != request.sha256):
                raise GatewayConflict("model version is immutable")
            result = await self.pool.deploy(request)
            if request.artifact_path.resolve().is_relative_to(
                (self.settings.runtime_data_root / "models").resolve()
            ):
                self.models.record(
                    request.model_dump(mode="json", by_alias=True, exclude_none=True)
                )
            return result

    async def _load_models(self, config: TaskStartRequest):
        # Admission must consider the complete model set, not only cache misses.
        # TaskManager takes a lifetime lease again when the runner is created.
        lease = await self.pool.acquire(config.model_bindings.values(), self.models)
        await self.pool.release(lease)

    async def _apply(self, document: dict):
        config = self._validate(document["config"])
        task_id = config.task_id
        try:
            if document["enabled"]:
                await self._load_models(config)
            current = next((s for s in self.tasks.statuses() if s.task_id == task_id), None)
            if current:
                await self.tasks.stop_task(task_id, current.run_id)
            if document["enabled"]:
                await self.tasks.start_task(config)
                if document.get("globalSettings"):
                    request = TaskSettingsApplyRequest.model_validate(document["globalSettings"])
                    await self.tasks.apply_task_settings(task_id, request.settings)
            self._applied[task_id] = document["revision"]
            self._errors.pop(task_id, None)
        except Exception as error:
            self._errors[task_id] = (
                ("MODEL_CAPACITY_EXCEEDED", str(error))
                if isinstance(error, ModelCapacityError)
                else ("MODEL_UNAVAILABLE", str(error))
                if isinstance(error, ModelUnavailableError)
                else ("GATEWAY_APPLY_PENDING", "配置已保存，运行恢复中，请检查模型与摄像头连接")
            )
            LOGGER.warning(
                "Gateway task apply deferred taskId=%s errorType=%s", task_id, type(error).__name__
            )

    async def change(self, change: GatewayChange, origin: str = "LOCAL") -> dict:
        fingerprint = hashlib.sha256(change.model_dump_json(by_alias=True).encode()).hexdigest()
        async with self._lock:
            receipt = self.store.receipt(str(change.request_id))
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise GatewayConflict("requestId has already been used for another change")
                return self.task(change.task_id)
            previous = self.store.get(change.task_id)
            revision = previous["revision"] if previous else 0
            if change.expected_revision != revision:
                raise GatewayConflict("configuration changed; refresh before saving")
            raw = dict(previous["config"]) if previous else {}
            if change.configuration is not None:
                supplied = dict(change.configuration)
                if previous and not supplied.get("sourceUrl"):
                    supplied.pop("sourceUrl", None)
                raw.update(supplied)
            if raw.get("taskId") != change.task_id:
                raise ValueError("taskId must match configuration")
            if previous and any(
                raw.get(key) != previous["config"].get(key)
                for key in ("cameraId", "algorithmId", "pipelineVersionId", "runId")
            ):
                raise ValueError("deployed task identity cannot be changed")
            config = self._validate(raw)
            if change.enabled is not False:
                await self._load_models(config)
            for other in self.store.all():
                if (
                    other["config"]["taskId"] != change.task_id
                    and other["config"]["cameraId"] == config.camera_id
                    and other["config"]["sourceUrl"] != config.source_url.get_secret_value()
                ):
                    raise ValueError("shared camera source must agree across tasks")
            document = {
                "schemaVersion": "1.0",
                "platformManaged": (previous or {}).get("platformManaged", False),
                "revision": revision + 1,
                "name": change.name or (previous or {}).get("name", f"任务 {change.task_id}"),
                "enabled": change.enabled
                if change.enabled is not None
                else (previous or {}).get("enabled", False),
                "origin": origin,
                "updatedAt": datetime.now(UTC).isoformat(),
                "config": _config_dict(config),
                "globalSettings": (previous or {}).get("globalSettings"),
            }
            self.store.save(document, str(change.request_id), fingerprint)
            self._set_local_tasks()
            await self._apply(document)
            return self.task(change.task_id)

    async def platform_start(self, config: TaskStartRequest, expected: int | None) -> TaskStatus:
        async with self._lock:
            previous = self.store.get(config.task_id)
            request_id = f"platform-start:{config.run_id}:{config.config_version}"
            fingerprint = hashlib.sha256(
                json.dumps(_config_dict(config), sort_keys=True).encode()
            ).hexdigest()
            receipt = self.store.receipt(request_id)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise GatewayConflict("start command payload changed")
                return self.status(config.task_id)
            self._check_platform_revision(previous, expected)
            raw = _config_dict(config)
            if previous:
                old_version = previous["config"]["configVersion"]
                if config.config_version < old_version:
                    raise GatewayConflict("stale platform configuration")
                if config.config_version == old_version:
                    raw = {**previous["config"], "runId": config.run_id}
            self._validate(raw)
            document = {
                "schemaVersion": "1.0",
                "revision": (previous or {}).get("revision", 0) + 1,
                "platformManaged": True,
                "config": raw,
                "enabled": True,
                "name": (previous or {}).get("name", f"任务 {config.task_id}"),
                "origin": "PLATFORM",
                "updatedAt": datetime.now(UTC).isoformat(),
                "globalSettings": (previous or {}).get("globalSettings"),
            }
            self.store.save(document, request_id, fingerprint)
            await self._apply(document)
            return self.status(config.task_id)

    def _check_platform_revision(self, previous, expected):
        actual = (previous or {}).get("revision", 0)
        # Legacy agents may seed a device, but cannot overwrite existing autonomous state.
        if (expected is None and previous is not None) or (
            expected is not None and expected != actual
        ):
            raise GatewayConflict("gateway configuration changed since command was queued")

    async def platform_stop(self, task_id: int, run_id: str, expected: int | None):
        async with self._lock:
            previous = self.store.get(task_id)
            if previous is None:
                return await self.tasks.stop_task(task_id, run_id)
            receipt_id = f"platform-stop:{run_id}:{expected}"
            if self.store.receipt(receipt_id):
                return self.status(task_id)
            self._check_platform_revision(previous, expected)
            if previous["config"]["runId"] != run_id:
                raise GatewayConflict("run changed before stop")
            document = {
                **previous,
                "revision": previous["revision"] + 1,
                "enabled": False,
                "origin": "PLATFORM",
                "updatedAt": datetime.now(UTC).isoformat(),
            }
            self.store.save(document, receipt_id, receipt_id)
            await self._apply(document)
            return self.status(task_id)

    async def apply_settings(self, request: TaskSettingsApplyRequest):
        async with self._lock:
            previous = self.store.get(request.task_id)
            if previous is None:
                return await self.tasks.apply_task_settings(request.task_id, request.settings)
            receipt_id = f"settings:{request.task_id}:{request.global_settings_version}"
            if not self.store.receipt(receipt_id):
                current = previous.get("globalSettings") or {}
                if request.global_settings_version < current.get("globalSettingsVersion", 0):
                    raise GatewayConflict("stale global settings")
                document = {
                    **previous,
                    "globalSettings": request.model_dump(by_alias=True),
                    "revision": previous["revision"] + 1,
                }
                self.store.save(document, receipt_id, receipt_id)
                await self._apply(document)
            return self.status(request.task_id)

    def status(self, task_id: int) -> TaskStatus:
        document = self.store.get(task_id)
        if document is None:
            raise KeyError(task_id)
        config = document["config"]
        current = next(
            (s.model_copy(deep=True) for s in self.tasks.statuses() if s.task_id == task_id), None
        )
        if current is None:
            current = TaskStatus(
                taskId=task_id,
                runId=config["runId"],
                configVersion=config["configVersion"],
                status="FAILED" if document["enabled"] else "STOPPED",
                diagnosticId=str(uuid4()),
                metrics={"schemaVersion": "1.0"},
            )
        if task_id in self._errors:
            current.error_code, current.error_message = self._errors[task_id]
        current.metrics.update(
            {
                "gatewayRevision": document["revision"],
                "gatewayPlatformManaged": document.get("platformManaged", True),
                "gatewayAppliedRevision": self._applied.get(task_id, 0),
                "gatewayConfiguration": _public_config(config),
                "gatewayEnabled": document["enabled"],
            }
        )
        return current

    def statuses(self):
        result = {s.task_id: s for s in self.tasks.statuses()}
        for document in self.store.all():
            task_id = document["config"]["taskId"]
            result[task_id] = self.status(task_id)
        return list(result.values())

    def task(self, task_id: int) -> dict:
        document = self.store.get(task_id)
        if document is None:
            raise KeyError(task_id)
        return {
            **document,
            "config": _public_config(document["config"]),
            "status": self.status(task_id).model_dump(by_alias=True),
            "appliedRevision": self._applied.get(task_id, 0),
        }

    def snapshot(self):
        return {
            "schemaVersion": "1.0",
            "capabilities": ["model.uninstall.v1", "preview.webrtc.v1"],
            "tasks": [self.task(d["config"]["taskId"]) for d in self.store.all()],
            "models": self.models.summaries(),
            "historyDays": self.settings.gateway_history_days,
        }


def _config_dict(config: TaskStartRequest) -> dict:
    return {
        **config.model_dump(mode="json", by_alias=True),
        "sourceUrl": config.source_url.get_secret_value(),
    }


def _public_config(config: dict) -> dict:
    return {key: value for key, value in config.items() if key != "sourceUrl"}
