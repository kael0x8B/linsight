import asyncio
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

from edge_agent.app.artifact.download import download_file
from edge_agent.app.client.control_plane import (
    ControlPlaneClient,
    ModelCommandDetail,
    NodeCommandAssignment,
)
from edge_agent.app.client.runtime import RuntimeClient
from edge_agent.app.command.deployed_models import DeployedModelRegistry
from edge_agent.app.command.lifecycle import NodeLifecycleController
from edge_agent.app.core.identity import NodeIdentity
from edge_agent.app.upgrade.manager import ReleaseManifest, UpgradeManager


class ModelDependencyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ModelCommandExecutor:
    def __init__(
        self,
        control_plane: ControlPlaneClient,
        runtime: RuntimeClient,
        identity: NodeIdentity,
        data_root: Path,
        upgrade_manager: UpgradeManager | None = None,
        lifecycle_controller: NodeLifecycleController | None = None,
    ) -> None:
        self._control_plane = control_plane
        self._runtime = runtime
        self._identity = identity
        self._data_root = data_root
        self._deployed_models = DeployedModelRegistry(data_root)
        self._upgrade_manager = upgrade_manager
        self._lifecycle_controller = lifecycle_controller or NodeLifecycleController(
            Path("/run/linsight/node-power-request"), data_root / "lifecycle-journal"
        )

    async def rehydrate_models(self) -> int:
        # Runtime loads the task's verified local artifacts on demand. Eagerly
        # warming every historical version thrashes a bounded pool and can evict
        # the very models needed by the next START_TASK command.
        return len(await asyncio.to_thread(self._deployed_models.summaries))

    async def execute(self, command: NodeCommandAssignment) -> None:
        diagnostic_id = str(uuid.uuid4())
        receipt = self._receipt_path(command)
        if receipt.exists():
            payload = json.loads(receipt.read_text())
            await self._control_plane.report_command(self._identity, payload)
            return
        try:
            if command.command_type == "ENTRY_FACE":
                await self._execute_entry(command, diagnostic_id)
                return
            if command.command_type == "VERIFY_FACE":
                await self._execute_face_verification(command, diagnostic_id)
                return
            if command.command_type in {"START_TASK", "STOP_TASK", "APPLY_TASK_SETTINGS"}:
                await self._execute_task(command, diagnostic_id)
                return
            if command.command_type in {"UPGRADE_AGENT", "ROLLBACK_AGENT"}:
                await self._execute_upgrade(command, diagnostic_id)
                return
            if command.command_type in {"RESTART_NODE", "SHUTDOWN_NODE"}:
                await self._execute_lifecycle(command, diagnostic_id)
                return
            await self._report(
                command,
                "RUNNING",
                "REMOVING" if command.command_type == "UNINSTALL_MODEL" else "DOWNLOADING",
                diagnostic_id,
            )
            detail = await self._control_plane.get_model_command(self._identity, command.command_id)
            if command.command_type == "UNINSTALL_MODEL":
                reply = await self._runtime.gateway_rpc(
                    {
                        "action": "model.uninstall",
                        "payload": {
                            "modelVersionId": detail.model_version_id,
                            "sha256": detail.sha256,
                            "requestId": command.command_id,
                        },
                    }
                )
                if not reply.get("ok"):
                    raise ModelDependencyError(
                        "MODEL_UNINSTALL_REJECTED", reply.get("message", "模型卸载失败")
                    )
                await self._report(command, "SUCCEEDED", "REMOVED", diagnostic_id)
                return
            artifact = await self._download_artifact(detail)
            await self._report(command, "RUNNING", "VERIFYING", diagnostic_id)
            deploy_payload = {
                "modelVersionId": detail.model_version_id,
                "artifactPath": str(artifact.resolve()),
                "artifactFormat": detail.artifact_format,
                "trustedArtifact": detail.trusted_artifact,
                "sha256": detail.sha256,
                "device": "RKNPU"
                if (
                    detail.artifact_format == "RKNN"
                    or (detail.runtime_manifest or {}).get("decoder", {}).get("type")
                    == "FACE_PAIR_SFACE_RKNN"
                )
                else "CPU",
            }
            if detail.runtime_manifest is not None:
                deploy_payload["runtimeManifest"] = detail.runtime_manifest
            if detail.adapter is not None:
                deploy_payload["adapter"] = detail.adapter
            decoder = (detail.runtime_manifest or {}).get("decoder", {}).get("type")
            if decoder not in {"FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN"}:
                await self._prepare_dependencies(detail.artifact_format, command, diagnostic_id)
            await self._report(command, "RUNNING", "LOADING", diagnostic_id)
            deploy_result = await self._runtime.deploy(deploy_payload)
            self._deployed_models.record(deploy_payload)
            if command.command_type == "DEPLOY_MODEL":
                await self._report(
                    command,
                    "SUCCEEDED",
                    "READY",
                    diagnostic_id,
                    backend=deploy_result["backend"],
                    device=deploy_result["device"],
                )
                return
            await self._run_test(command, detail, diagnostic_id, deploy_result)
        except Exception as error:
            if receipt.exists():
                # A lost acknowledgement must not turn a completed host action into
                # a failure or toggle an already applied rollback on redelivery.
                raise
            await self._report(
                command,
                "FAILED",
                None,
                diagnostic_id,
                error_code=(
                    error.code
                    if isinstance(error, ModelDependencyError)
                    else "NODE_UPGRADE_FAILED"
                    if command.command_type in {"UPGRADE_AGENT", "ROLLBACK_AGENT"}
                    else "NODE_LIFECYCLE_FAILED"
                    if command.command_type in {"RESTART_NODE", "SHUTDOWN_NODE"}
                    else "MODEL_COMMAND_FAILED"
                ),
                error_message=_safe_error_message(error),
            )

    async def _execute_entry(self, command: NodeCommandAssignment, diagnostic_id: str) -> None:
        import contextlib
        import shutil

        detail = await self._control_plane.get_entry_command(self._identity, command.command_id)
        directory = self._data_root / "entry-references" / str(uuid.UUID(command.command_id))
        directory.mkdir(parents=True, exist_ok=True)
        monitor = None
        try:
            total = 0
            for index, item in enumerate(detail["references"]):
                path = directory / f"{index}.jpg"
                await download_file(item.pop("url"), path, 5 * 1024 * 1024, item["sha256"])
                total += path.stat().st_size
                if total > 100 * 1024 * 1024:
                    raise ValueError("reference download budget exceeded")
                item["path"] = str(path.resolve())

            async def watch_cancel():
                while True:
                    await asyncio.sleep(1)
                    try:
                        state = await self._control_plane.get_entry_command(
                            self._identity, command.command_id, state=True
                        )
                        if state.get("cancelled"):
                            await self._runtime.cancel_entry(command.command_id)
                            return
                    except (httpx.HTTPError, RuntimeError):
                        # Loss of control connection cancels the finite active scan.
                        await self._runtime.cancel_entry(command.command_id)
                        return

            state = await self._control_plane.get_entry_command(
                self._identity, command.command_id, state=True
            )
            if state.get("cancelled"):
                result = {"status": "CANCELLED", "reason": "SESSION_CANCELLED"}
            else:
                monitor = asyncio.create_task(watch_cancel())
                await self._report(command, "RUNNING", "INFERENCING", diagnostic_id)
                result = await self._runtime.entry_access(detail)
            evidence = {
                key: result.pop(key) for key in ("snapshotPath", "videoPath") if key in result
            }
            if evidence:
                from edge_agent.app.command.entry_evidence import save_pending

                save_pending(self._data_root, command.command_id, evidence)
            await self._report(command, "SUCCEEDED", "COMPLETED", diagnostic_id, result=result)
        finally:
            if monitor:
                monitor.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await monitor
            shutil.rmtree(directory, ignore_errors=True)

    async def _execute_face_verification(self, command, diagnostic_id):
        detail = await self._control_plane.get_face_verification(self._identity, command.command_id)
        reference = self._data_root / "face-verification" / f"{uuid.UUID(command.command_id)}.jpg"
        try:
            await download_file(
                detail.pop("referenceUrl"),
                reference,
                10 * 1024 * 1024,
                detail.pop("referenceSha256"),
            )
            detail["referencePath"] = str(reference.resolve())
            await self._report(command, "RUNNING", "INFERENCING", diagnostic_id)
            result = await self._runtime.verify_face(detail)
            await self._report(command, "SUCCEEDED", "COMPLETED", diagnostic_id, result=result)
        finally:
            reference.unlink(missing_ok=True)

    async def _prepare_dependencies(
        self,
        artifact_format: str,
        command: NodeCommandAssignment | None = None,
        diagnostic_id: str | None = None,
    ) -> None:
        if artifact_format == "ONNX":
            return
        if command is not None:
            await self._report(command, "RUNNING", "CHECKING_ENV", diagnostic_id)
        try:
            async with asyncio.timeout(1260):
                state = await self._runtime.prepare_dependencies(artifact_format)
                while state.get("status") == "RUNNING":
                    stage = state.get("stage", "CHECKING_ENV")
                    if stage not in {
                        "CHECKING_ENV",
                        "DOWNLOADING_DEPS",
                        "INSTALLING_DEPS",
                        "RETRYING_DEPS",
                        "VERIFYING_ENV",
                    }:
                        stage = "CHECKING_ENV"
                    if command is not None:
                        await self._report(command, "RUNNING", stage, diagnostic_id)
                    await asyncio.sleep(5)
                    for attempt in range(3):
                        try:
                            state = await self._runtime.dependency_status(state["profile"])
                            break
                        except httpx.TransportError:
                            if attempt == 2:
                                raise
                            await asyncio.sleep(5)
                if state.get("status") != "READY":
                    raise ModelDependencyError(
                        state.get("errorCode") or "DEPENDENCY_PREPARE_FAILED",
                        state.get("errorMessage") or "模型运行环境准备失败，请重新部署",
                    )
        except TimeoutError as error:
            raise ModelDependencyError(
                "DEPENDENCY_PREPARE_TIMEOUT", "运行环境准备超时，请检查节点网络后重新部署"
            ) from error
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                raise ModelDependencyError(
                    "DEPENDENCY_RUNTIME_UPGRADE_REQUIRED",
                    "当前 Runtime 不支持自动准备环境，请先更新节点",
                ) from error
            raise ModelDependencyError(
                "DEPENDENCY_RUNTIME_UNAVAILABLE", "运行环境准备接口异常，请检查节点服务后重新部署"
            ) from error
        except httpx.TransportError as error:
            raise ModelDependencyError(
                "DEPENDENCY_RUNTIME_UNAVAILABLE", "无法连接节点 Runtime，请检查服务状态后重新部署"
            ) from error

    async def _execute_lifecycle(self, command: NodeCommandAssignment, diagnostic_id: str) -> None:
        action = "restart" if command.command_type == "RESTART_NODE" else "shutdown"
        stage = "RESTARTING" if action == "restart" else "SHUTTING_DOWN"
        await self._report(command, "RUNNING", stage, diagnostic_id)
        result = await self._lifecycle_controller.schedule(action, command.command_id)
        await self._report(command, "SUCCEEDED", stage, diagnostic_id, result=result)

    async def _execute_upgrade(self, command: NodeCommandAssignment, diagnostic_id: str) -> None:
        if self._upgrade_manager is None:
            raise RuntimeError("upgrade manager is not configured")
        detail = await self._control_plane.get_upgrade_command(self._identity, command.command_id)
        if command.command_type == "ROLLBACK_AGENT":
            await self._report(command, "RUNNING", "ROLLING_BACK", diagnostic_id)
            release = await asyncio.to_thread(self._upgrade_manager.rollback)
            await self._report(
                command,
                "SUCCEEDED",
                "ROLLED_BACK",
                diagnostic_id,
                result={"currentVersion": release.name, "restartRequired": True},
            )
            return
        if not all(
            [
                detail.target_version,
                detail.package_url,
                detail.package_name,
                detail.sha256,
                detail.signature,
            ]
        ):
            raise ValueError("upgrade command is missing signed release metadata")
        await self._report(command, "RUNNING", "DOWNLOADING", diagnostic_id)
        suffix = ".tar.gz" if detail.package_name.endswith(".tar.gz") else ".tgz"
        package = self._data_root / "upgrades" / f"{command.command_id}{suffix}"
        await download_file(
            detail.package_url.get_secret_value(),
            package,
            64 * 1024 * 1024,
            detail.sha256,
        )
        await self._report(command, "RUNNING", "VERIFYING", diagnostic_id)
        manifest = ReleaseManifest(
            version=detail.target_version,
            sha256=detail.sha256,
            signature=detail.signature,
        )
        await self._report(command, "RUNNING", "INSTALLING", diagnostic_id)
        release = await asyncio.to_thread(self._upgrade_manager.install, package, manifest)
        await self._report(
            command,
            "SUCCEEDED",
            "ACTIVATING",
            diagnostic_id,
            result={"currentVersion": release.name, "restartRequired": True},
        )

    async def _execute_task(self, command: NodeCommandAssignment, diagnostic_id: str) -> None:
        stage = {
            "START_TASK": "STARTING",
            "STOP_TASK": "STOPPING",
            "APPLY_TASK_SETTINGS": "APPLYING_SETTINGS",
        }[command.command_type]
        await self._report(command, "RUNNING", stage, diagnostic_id)
        detail = await self._control_plane.get_task_command(self._identity, command.command_id)
        if command.command_type == "APPLY_TASK_SETTINGS":
            if detail.global_settings_version <= 0 or detail.global_settings is None:
                raise ValueError("task settings command is missing versioned settings")
            result = await self._runtime.apply_task_settings(
                {
                    "taskId": detail.task_id,
                    "globalSettingsVersion": detail.global_settings_version,
                    "settings": detail.global_settings,
                }
            )
            await self._report(
                command, "SUCCEEDED", "SETTINGS_APPLIED", diagnostic_id, result=result
            )
            return
        if command.command_type == "START_TASK":
            if detail.stream_url is None:
                raise ValueError("task start command is missing stream URL")
            result = await self._runtime.start_task(
                {
                    "taskId": detail.task_id,
                    "runId": detail.run_id,
                    "configVersion": detail.config_version,
                    "cameraId": detail.camera_id,
                    "sourceUrl": detail.stream_url.get_secret_value(),
                    "algorithmId": detail.algorithm_id,
                    "pipelineVersionId": detail.pipeline_version_id,
                    "pipeline": detail.pipeline,
                    "modelVersionId": detail.model_version_id,
                    "modelBindings": detail.model_bindings,
                    "ruleId": detail.rule_id,
                    "ruleVersionId": detail.rule_version_id,
                    "rule": detail.rule,
                    "parameters": detail.parameters,
                    **(
                        {"expectedGatewayRevision": detail.expected_gateway_revision}
                        if detail.expected_gateway_revision is not None
                        else {}
                    ),
                }
            )
            if result.get("status") != "RUNNING":
                if result.get("errorCode") in {"MODEL_CAPACITY_EXCEEDED", "MODEL_UNAVAILABLE"}:
                    raise ModelDependencyError(
                        result["errorCode"], result.get("errorMessage") or "任务模型无法加载"
                    )
                raise RuntimeError("gateway saved configuration but task is not running")
            await self._report(command, "SUCCEEDED", "RUNNING", diagnostic_id, result=result)
            return
        if detail.expected_gateway_revision is None:
            result = await self._runtime.stop_task(detail.task_id, detail.run_id)
        else:
            result = await self._runtime.stop_task(
                detail.task_id, detail.run_id, detail.expected_gateway_revision
            )
        await self._report(command, "SUCCEEDED", "STOPPED", diagnostic_id, result=result)

    async def _run_test(
        self,
        command: NodeCommandAssignment,
        detail: ModelCommandDetail,
        diagnostic_id: str,
        deploy_result: dict[str, Any],
    ) -> None:
        if detail.image_url is None or detail.parameters is None:
            raise ValueError("test command is missing image or parameters")
        image = self._data_root / "tests" / f"{command.command_id}.image"
        await download_file(detail.image_url.get_secret_value(), image, 10 * 1024 * 1024)
        await self._report(command, "RUNNING", "INFERENCING", diagnostic_id)
        result = await self._runtime.test(
            {
                "modelVersionId": detail.model_version_id,
                "imagePath": str(image.resolve()),
                "parameters": detail.parameters,
            }
        )
        report_result = {
            key: value
            for key, value in result.items()
            if key
            not in {
                "backend",
                "device",
                "preprocessMillis",
                "inferenceMillis",
                "postprocessMillis",
            }
        }
        await self._report(
            command,
            "SUCCEEDED",
            "COMPLETED",
            diagnostic_id,
            backend=result.get("backend", deploy_result["backend"]),
            device=result.get("device", deploy_result["device"]),
            result=report_result,
            preprocess_millis=result.get("preprocessMillis"),
            inference_millis=result.get("inferenceMillis"),
            postprocess_millis=result.get("postprocessMillis"),
        )

    async def _download_artifact(self, detail: ModelCommandDetail) -> Path:
        extension = Path(detail.artifact_name).suffix or ".onnx"
        target = self._data_root / "models" / str(detail.model_version_id) / f"model{extension}"
        if target.exists() and _sha256(target) == detail.sha256:
            return target
        return await download_file(
            detail.artifact_url.get_secret_value(), target, 2 * 1024 * 1024 * 1024, detail.sha256
        )

    async def _report(
        self,
        command: NodeCommandAssignment,
        status: str,
        stage: str | None,
        diagnostic_id: str,
        **values: Any,
    ) -> None:
        payload = {
            "commandId": command.command_id,
            "status": status,
            "stage": stage,
            "diagnosticId": diagnostic_id,
            **{_camel_case(key): value for key, value in values.items()},
        }
        if status == "SUCCEEDED" and command.command_type in {
            "UNINSTALL_MODEL",
            "UPGRADE_AGENT",
            "ROLLBACK_AGENT",
            "VERIFY_FACE",
            "ENTRY_FACE",
            "RESTART_NODE",
            "SHUTDOWN_NODE",
        }:
            await asyncio.to_thread(self._save_receipt, self._receipt_path(command), payload)
        await self._control_plane.report_command(self._identity, payload)

    def _receipt_path(self, command: NodeCommandAssignment) -> Path:
        name = hashlib.sha256(command.command_id.encode()).hexdigest() + ".json"
        return self._data_root / "command-receipts" / name

    @staticmethod
    def _save_receipt(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".receipt-")
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, ModelDependencyError):
        return str(error)[:500]
    if isinstance(error, httpx.HTTPStatusError):
        try:
            detail = error.response.json().get("detail")
            if isinstance(detail, str):
                return detail[:500]
        except (ValueError, AttributeError, httpx.ResponseNotRead):
            pass
        return f"HTTP 请求失败（状态码 {error.response.status_code}）"
    return type(error).__name__


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(word.title() for word in tail)
