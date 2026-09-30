"""One mutation boundary for platform commands and the two management entrances."""

import asyncio
import hashlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ai_runtime.app.capability.package_runner import RUNTIME_CAPABILITIES
from ai_runtime.app.gateway.event_stream import GatewayEventStream
from ai_runtime.app.gateway.store import GatewayStore
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.model.deployed import DeployedModelRegistry
from ai_runtime.app.model.pool import ModelCapacityError, ModelUnavailableError
from ai_runtime.app.rule.confirmation_latency import (
    EVENT_VISIBILITY_TARGET_SECONDS,
    conflicts_with_visibility_target,
    minimum_confirmation_seconds,
)
from ai_runtime.app.stream.shared import UnsupportedTimelineCodec
from ai_runtime.app.task.contracts import TaskSettingsApplyRequest, TaskStartRequest, TaskStatus
from ai_runtime.app.task.image_recognition import TaskImageRecognizer, TaskImageRequest
from ai_runtime.app.task.manager import _validate_pipeline

LOGGER = logging.getLogger("linsight.gateway")


class GatewayConflict(ValueError):
    pass


class GatewayCapacityExceeded(ModelCapacityError):
    def __init__(self, report: dict):
        super().__init__(report["message"])
        self.report = report


class ConfirmationLatencyConflict(ValueError):
    pass


class GatewayChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: int = Field(alias="taskId", gt=0)
    expected_revision: int = Field(alias="expectedRevision", ge=0)
    request_id: UUID = Field(alias="requestId")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    configuration: dict | None = None


class GatewayCapacityPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: int = Field(alias="taskId", gt=0)
    model_version_ids: list[int] | None = Field(
        default=None, alias="modelVersionIds", max_length=20
    )
    configuration: dict | None = None


class GatewayService:
    def __init__(self, settings, pool, tasks):
        self.settings, self.pool, self.tasks = settings, pool, tasks
        self.store = GatewayStore(settings.runtime_data_root / "gateway")
        self.event_stream = GatewayEventStream(
            tasks.event_store, self.store, settings.runtime_data_root / "events",
            settings.gateway_event_tcp_host, settings.gateway_event_tcp_port,
            settings.gateway_console_port, settings.gateway_console_enabled,
        )
        self.models = DeployedModelRegistry(settings.runtime_data_root)
        self.image_recognizer = TaskImageRecognizer(settings.runtime_data_root, pool, self.models)
        from ai_runtime.app.task.validation import ImageValidationService

        self.image_validation = ImageValidationService(self)
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
        } | {
            removal["taskId"] for removal in self.store.removals() if not removal["platformManaged"]
        }

    async def start(self):
        await self.event_stream.start()
        self._worker = asyncio.create_task(self._recover_loop(), name="gateway-recovery")

    async def close(self):
        await self.event_stream.close()
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
                self.event_stream.prune(self.settings.gateway_history_days)
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
        if descriptor := config.pipeline.get("algorithmPackage"):
            from ai_runtime.app.capability.packages import (
                AlgorithmPackageStore,
                validate_bindings,
                validate_parameters,
            )

            _, manifest = AlgorithmPackageStore(self.settings.runtime_data_root).resolve(
                descriptor["sha256"]
            )
            if manifest != descriptor["manifest"]:
                raise ValueError("算法包描述不一致")
            validate_parameters(manifest.get("parameterSchema", {}), config.parameters.algorithm)
            validate_bindings(manifest, config.model_bindings, self.models.summaries())
            for resource in manifest.get("resources", []):
                if not config.algorithm_resources.get(resource["key"]):
                    raise ValueError("算法需要的人员库资源尚未同步到本机")
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

    async def capacity_preflight(self, request: GatewayCapacityPreflight) -> dict:
        """Project one task into this node without changing pool or task state."""
        previous = self.store.get(request.task_id)
        if request.configuration is not None:
            raw = _merge_stream_configuration(
                previous["config"] if previous else {}, request.configuration
            )
            if raw.get("taskId") != request.task_id:
                raise ValueError("taskId must match configuration")
            candidate_ids = set(self._validate(raw).model_bindings.values())
        elif request.model_version_ids:
            candidate_ids = set(request.model_version_ids)
        elif previous:
            candidate_ids = _model_ids(previous["config"])
        else:
            raise ValueError("capacity preflight requires a configuration or modelVersionIds")

        stored = {document["config"]["taskId"]: document for document in self.store.all()}
        current_tasks = {}
        for config in self.tasks.running_requests():
            document = stored.get(config.task_id)
            current_tasks[config.task_id] = document or {
                "name": f"任务 {config.task_id}",
                "config": _config_dict(config),
            }
        current_models = {
            model_id
            for document in current_tasks.values()
            for model_id in _model_ids(document["config"])
        }
        # Keep the active task's old models in the admission set. _apply deliberately
        # loads the replacement before stopping production, so those slots/memory are
        # not releasable during a safe handover.
        projected_task_models = {
            task_id: _model_ids(document["config"]) for task_id, document in current_tasks.items()
        }
        projected_task_models[request.task_id] = (
            projected_task_models.get(request.task_id, set()) | candidate_ids
        )
        projected_models = {model_id for ids in projected_task_models.values() for model_id in ids}
        plan = await self.pool.capacity_preflight(
            current_models,
            projected_models,
            self.models,
            memory_safety_ratio=self.settings.model_memory_safety_ratio,
            memory_min_reserve_bytes=self.settings.model_memory_min_reserve_mib * 1024 * 1024,
        )
        conflicts = [
            {
                "taskId": task_id,
                "name": document.get("name", f"任务 {task_id}"),
                "modelVersionIds": sorted(_model_ids(document["config"])),
            }
            for task_id, document in sorted(current_tasks.items())
        ]
        models = []
        for model_id in plan.projected_model_ids:
            users = sorted(
                task_id for task_id, ids in projected_task_models.items() if model_id in ids
            )
            models.append(
                {
                    "modelVersionId": model_id,
                    "artifactBytes": plan.artifact_bytes[model_id],
                    "memoryBudgetBytes": plan.memory_budget_bytes[model_id],
                    "taskIds": users,
                    "shared": len(users) > 1,
                    "requested": model_id in candidate_ids,
                }
            )
        reasons = []
        if not plan.slot_allowed:
            reasons.append(
                f"共享模型去重后需要 {len(plan.projected_model_ids)}/{plan.slot_limit} 个模型槽位"
            )
        if not plan.memory_allowed:
            reasons.append(
                "预计启动后可用内存 "
                f"{_mib(plan.memory_available_after_bytes)} MiB，"
                f"低于安全保留 {_mib(plan.memory_safety_reserve_bytes)} MiB"
            )
        occupied = (
            "、".join(
                f"{item['name']}(#{item['taskId']}："
                + "/".join(f"模型#{value}" for value in item["modelVersionIds"])
                + ")"
                for item in conflicts
            )
            or "无其他运行中任务"
        )
        requested = "/".join(f"模型#{value}" for value in sorted(candidate_ids)) or "无模型"
        message = (
            "容量预检通过：共享模型去重后"
            f"占用 {len(plan.projected_model_ids)}/{plan.slot_limit} 个槽位，"
            f"模型内存预算 {_mib(plan.projected_memory_budget_bytes)} MiB"
            if plan.allowed
            else "；".join(reasons)
            + f"。本次任务/模型：任务 #{request.task_id}（{requested}）；"
            + f"当前冲突任务/模型：{occupied}"
        )
        return {
            "schemaVersion": "1.0",
            "allowed": plan.allowed,
            "code": None if plan.allowed else "MODEL_CAPACITY_EXCEEDED",
            "message": message,
            "taskId": request.task_id,
            "slotLimit": plan.slot_limit,
            "currentSlotCount": len(plan.current_model_ids),
            "projectedSlotCount": len(plan.projected_model_ids),
            "sharedModelCount": sum(1 for model in models if model["shared"]),
            "currentMemoryBudgetBytes": plan.current_memory_budget_bytes,
            "projectedMemoryBudgetBytes": plan.projected_memory_budget_bytes,
            "memoryTotalBytes": plan.memory_total_bytes,
            "memoryAvailableBytes": plan.memory_available_bytes,
            "memoryAvailableAfterBytes": plan.memory_available_after_bytes,
            "memorySafetyReserveBytes": plan.memory_safety_reserve_bytes,
            "memoryBudgetBasis": "VERIFIED_ARTIFACT_X2_MIN_64_MIB",
            "conflictTasks": conflicts,
            "models": models,
        }

    async def _require_capacity(self, task_id: int, model_ids: set[int]) -> None:
        report = await self.capacity_preflight(
            GatewayCapacityPreflight(taskId=task_id, modelVersionIds=sorted(model_ids))
        )
        if not report["allowed"]:
            raise GatewayCapacityExceeded(report)

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
                else ("UNSUPPORTED_VIDEO_CODEC", str(error))
                if isinstance(error, UnsupportedTimelineCodec)
                else ("GATEWAY_APPLY_PENDING", "配置已保存，运行恢复中，请检查模型与摄像头连接")
            )
            LOGGER.warning(
                "Gateway task apply deferred taskId=%s errorType=%s", task_id, type(error).__name__
            )

    async def remove(self, change: GatewayChange) -> dict:
        fingerprint = hashlib.sha256(
            f"remove:{change.task_id}:{change.expected_revision}".encode()
        ).hexdigest()
        async with self._lock:
            receipt = self.store.receipt(str(change.request_id))
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise GatewayConflict("request identity changed")
                return {"removed": True}
            previous = self.store.get(change.task_id)
            if previous is None:
                return {"removed": True}
            if previous["revision"] != change.expected_revision:
                raise GatewayConflict("configuration changed")
            if previous["enabled"] or self.status(change.task_id).status == "RUNNING":
                raise ValueError("请先停止识别再移除配置")
            self.store.remove(
                change.task_id, previous["revision"], str(change.request_id), fingerprint
            )
            self._applied.pop(change.task_id, None)
            self._errors.pop(change.task_id, None)
            self._set_local_tasks()
            return {"removed": True}

    async def change(self, change: GatewayChange, origin: str = "LOCAL") -> dict:
        fingerprint = hashlib.sha256(change.model_dump_json(by_alias=True).encode()).hexdigest()
        async with self._lock:
            if self.store.is_removed(change.task_id):
                raise GatewayConflict("任务已移除，请重新添加识别算法")
            receipt = self.store.receipt(str(change.request_id))
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise GatewayConflict("requestId has already been used for another change")
                return self.task(change.task_id)
            previous = self.store.get(change.task_id)
            revision = previous["revision"] if previous else 0
            if change.expected_revision != revision:
                raise GatewayConflict("configuration changed; refresh before saving")
            raw = _merge_stream_configuration(
                previous["config"] if previous else {}, change.configuration or {}
            )
            if not previous and not raw.get("sourceUrl"):
                source = next(
                    (
                        item["config"]["sourceUrl"]
                        for item in self.store.all()
                        if item["config"]["cameraId"] == raw.get("cameraId")
                    ),
                    None,
                )
                if source:
                    raw["sourceUrl"] = source
            if previous and raw.get("pipeline", {}).get("algorithmPackage"):
                manifest = raw["pipeline"]["algorithmPackage"]["manifest"]
                config_values = raw.get("parameters", {}).get("algorithm", {})
                for resource in manifest.get("resources", []):
                    old_library = (
                        previous["config"]
                        .get("parameters", {})
                        .get("algorithm", {})
                        .get(resource["parameter"])
                    )
                    if config_values.get(resource["parameter"]) != old_library:
                        raise ValueError("请先同步所选人员库资源")
                    selected_ids = config_values.get(resource.get("selectionParameter"), [])
                    available = raw.get("algorithmResources", {}).get(resource["key"], [])
                    if set(selected_ids) - {r["id"] for r in available}:
                        raise ValueError("所选人员尚未同步到网关")
            if raw.get("taskId") != change.task_id:
                raise ValueError("taskId must match configuration")
            if previous and any(
                raw.get(key) != previous["config"].get(key)
                for key in ("cameraId", "algorithmId", "pipelineVersionId", "runId")
            ):
                raise ValueError("deployed task identity cannot be changed")
            config = self._validate(raw)
            # Existing stored tasks and platform replays remain startable.  A
            # newly saved PHONE_CALL configuration must meet the product target.
            confirmation_changed = (
                previous is None
                or previous["config"].get("ruleId") != raw.get("ruleId")
                or previous["config"].get("ruleVersionId") != raw.get("ruleVersionId")
                or previous["config"].get("rule") != raw.get("rule")
                or previous["config"].get("parameters", {}).get("sampleFps")
                != raw.get("parameters", {}).get("sampleFps")
            )
            if (
                change.configuration is not None
                and confirmation_changed
                and config.rule is not None
            ):
                ast = config.rule.model_dump(mode="json", by_alias=True)
                if config.rule.event_type == "PHONE_CALL" and conflicts_with_visibility_target(
                    ast, config.parameters.sample_fps
                ):
                    estimate = minimum_confirmation_seconds(ast, config.parameters.sample_fps)
                    raise ConfirmationLatencyConflict(
                        f"预计最短确认时延 {estimate:g} 秒，超过 "
                        f"{EVENT_VISIBILITY_TARGET_SECONDS:g} 秒目标；"
                        "请提高分析帧率或降低规则连续帧/持续时间"
                    )
            will_enable = (
                change.enabled
                if change.enabled is not None
                else bool((previous or {}).get("enabled", False))
            )
            if will_enable:
                report = await self.capacity_preflight(
                    GatewayCapacityPreflight(
                        taskId=change.task_id, configuration=_config_dict(config)
                    )
                )
                if not report["allowed"]:
                    raise GatewayCapacityExceeded(report)
            for other in self.store.all():
                if (
                    other["config"]["taskId"] != change.task_id
                    and other["config"]["cameraId"] == config.camera_id
                    and other["config"]["sourceUrl"] != config.source_url.get_secret_value()
                ):
                    raise ValueError(
                        "同一摄像头还有其他任务使用不同的码流地址，"
                        "请先统一这些任务的码流配置"
                    )
            document = {
                "schemaVersion": "1.0",
                "platformManaged": (previous or {}).get("platformManaged", False),
                "revision": revision + 1,
                "name": change.name or (previous or {}).get("name", f"任务 {change.task_id}"),
                "displayNames": raw.get("displayNames") or (previous or {}).get("displayNames"),
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
            if self.store.is_removed(config.task_id):
                raise GatewayConflict("任务已移除，请重新添加识别算法")
            previous = self.store.get(config.task_id)
            request_id = f"platform-start:{config.run_id}:{config.config_version}"
            fingerprint_config = _config_dict(config)
            fingerprint_config.pop("displayNames", None)
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_config, sort_keys=True).encode()
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
                    display_names = raw.get("displayNames")
                    incoming_streams = raw.get("streamUrls", {})
                    raw = {**previous["config"], "runId": config.run_id}
                    # Seed older gateways without replacing locally edited sources.
                    raw["streamUrls"] = {
                        **incoming_streams, **raw.get("streamUrls", {}),
                        raw.get("parameters", {}).get("streamType", "SUB"): raw["sourceUrl"],
                    }
                    if display_names:
                        raw["displayNames"] = display_names
            validated = self._validate(raw)
            await self._require_capacity(config.task_id, set(validated.model_bindings.values()))
            document = {
                "schemaVersion": "1.0",
                "revision": (previous or {}).get("revision", 0) + 1,
                "platformManaged": True,
                "config": _config_dict(validated),
                "enabled": True,
                "name": (
                    (raw.get("displayNames") or {}).get("task")
                    or (previous or {}).get("name", f"任务 {config.task_id}")
                ),
                "displayNames": raw.get("displayNames") or (previous or {}).get("displayNames"),
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
        removed_ids = {removal["taskId"] for removal in self.store.removals()}
        result = {s.task_id: s for s in self.tasks.statuses() if s.task_id not in removed_ids}
        for document in self.store.all():
            task_id = document["config"]["taskId"]
            result[task_id] = self.status(task_id)
        return list(result.values())

    async def recognize_image(self, request: TaskImageRequest) -> dict:
        document = self.store.get(request.task_id)
        if document is None:
            raise KeyError(request.task_id)
        return await self.image_recognizer.recognize(request, document)

    def task(self, task_id: int) -> dict:
        document = self.store.get(task_id)
        if document is None:
            raise KeyError(task_id)
        return {
            **document,
            "config": _public_config(document["config"]),
            "status": self.status(task_id).model_dump(by_alias=True),
            "appliedRevision": self._applied.get(task_id, 0),
            "resourceOptions": _resource_options(document["config"]),
            "availableStreamTypes": sorted(document["config"].get("streamUrls", {})),
        }

    def snapshot(self):
        documents = self.store.all()
        models = self.models.summaries()
        return {
            "schemaVersion": "1.0",
            "capabilities": [
                "model.uninstall.v1",
                "preview.webrtc.v1",
                "algorithm.packages.v1",
                "event.tcp.v3",
                "task.removal.sync.v1",
                "vehicle.plate.front.v1",
                "task.image-recognition.v1",
                "task.image-validation.v1",
                "task.stream-switch.v1",
                *RUNTIME_CAPABILITIES,
            ],
            "names": _snapshot_names(documents, models),
            "tasks": [self.task(d["config"]["taskId"]) for d in documents],
            "models": models,
            "historyDays": self.settings.gateway_history_days,
        }


def _config_dict(config: TaskStartRequest) -> dict:
    source = config.source_url.get_secret_value()
    streams = {key: value.get_secret_value() for key, value in config.stream_urls.items()}
    if source.startswith(("rtsp://", "rtsps://")):
        streams[config.parameters.stream_type] = source
    return {
        **config.model_dump(mode="json", by_alias=True, exclude_none=True),
        "sourceUrl": source,
        "streamUrls": streams,
    }


def _public_config(config: dict) -> dict:
    return {
        key: value
        for key, value in config.items()
        if key not in {"sourceUrl", "streamUrls", "algorithmResources"}
    }


def _merge_stream_configuration(previous: dict, supplied: dict) -> dict:
    """Resolve a selector against encrypted device sources before validation/apply."""
    raw = {**previous, **supplied}
    current = previous.get("parameters", {}).get("streamType", "SUB")
    if previous and "streamType" not in raw.get("parameters", {}):
        raw["parameters"] = {**raw.get("parameters", {}), "streamType": current}
    selected = raw.get("parameters", {}).get("streamType", "SUB")
    defaults = raw.pop("streamUrlDefaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("主/子码流地址格式无效")
    # Catalog backfill must not replace a local custom address or current selection.
    sources = {**defaults, **previous.get("streamUrls", {})}
    if previous.get("sourceUrl", "").startswith(("rtsp://", "rtsps://")):
        sources[current] = previous["sourceUrl"]
    incoming = supplied.get("streamUrls", {})
    if not isinstance(incoming, dict):
        raise ValueError("主/子码流地址格式无效")
    sources.update(incoming)
    source = supplied.get("sourceUrl")
    if source:
        if not isinstance(source, str):
            raise ValueError("摄像头地址格式无效")
        # Existing platform clients already resolve the requested stream server-side.
        if source.startswith(("rtsp://", "rtsps://")):
            sources[selected] = source
        raw["sourceUrl"] = source
    elif selected != current or selected in incoming:
        if not sources.get(selected):
            raise ValueError(
                "该码流地址尚未保存，请在高级设置填写主/子码流地址，或在平台保存一次配置"
            )
        raw["sourceUrl"] = sources[selected]
    elif previous.get("sourceUrl"):
        raw["sourceUrl"] = previous["sourceUrl"]
    elif sources.get(selected):
        raw["sourceUrl"] = sources[selected]
    raw["streamUrls"] = sources
    return raw


def _resource_options(config: dict) -> dict:
    options = {}
    manifest = config.get("pipeline", {}).get("algorithmPackage", {}).get("manifest", {})
    parameters = config.get("parameters", {}).get("algorithm", {})
    for resource in manifest.get("resources", []):
        library = parameters.get(resource["parameter"])
        options[resource["parameter"]] = (
            [{"label": f"已同步人员库 #{library}", "value": library}] if library else []
        )
        if resource.get("selectionParameter"):
            options[resource["selectionParameter"]] = [
                {"label": entry["name"], "value": entry["id"]}
                for entry in config.get("algorithmResources", {}).get(resource["key"], [])
            ]
    return options


def _snapshot_names(documents: list[dict], models: list[dict]) -> dict:
    tasks, cameras, algorithms = {}, {}, {}
    for document in documents:
        config = document["config"]
        display = document.get("displayNames") or config.get("displayNames") or {}
        descriptor = config.get("pipeline", {}).get("algorithmPackage", {}).get("manifest", {})
        tasks[str(config["taskId"])] = display.get("task") or document.get("name")
        if display.get("camera"):
            cameras[str(config["cameraId"])] = display["camera"]
        algorithm = display.get("algorithm") or descriptor.get("name")
        if algorithm:
            algorithms[str(config["algorithmId"])] = algorithm
    return {
        "tasks": {key: value for key, value in tasks.items() if value},
        "cameras": cameras,
        "algorithms": algorithms,
        "models": {
            str(model["modelVersionId"]): {
                "name": model["displayName"],
                "version": model.get("version", ""),
            }
            for model in models
            if model.get("displayName")
        },
    }


def _model_ids(config: dict) -> set[int]:
    values = set(config.get("modelBindings", {}).values())
    if config.get("modelVersionId"):
        values.add(config["modelVersionId"])
    return {int(value) for value in values if int(value) > 0}


def _mib(value: int) -> int:
    return round(value / 1024 / 1024)
