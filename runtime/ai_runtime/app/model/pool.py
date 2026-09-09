import asyncio
import hashlib
import sys
from collections import Counter, OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import onnxruntime as ort
from PIL import Image

from ai_runtime.app.model.backends import (
    ExecutableAdapter,
    LicensePlateYuNetAdapter,
    LprNetAdapter,
    MergedAdapter,
    TorchScriptAdapter,
    extract_archive,
    load_pytorch_checkpoint,
)
from ai_runtime.app.model.contracts import (
    DeployModelRequest,
    DeployModelResponse,
    ModelTestRequest,
    ModelTestResult,
)
from ai_runtime.app.model.dependencies import DependencyManager
from ai_runtime.app.model.deployed import DeployedModelRegistry
from ai_runtime.app.model.face_pair import FacePairAdapter, FaceQualityError, RknnFacePairAdapter
from ai_runtime.app.model.generic import GenericOnnxAdapter
from ai_runtime.app.model.isolated import IsolatedAdapter
from ai_runtime.app.model.person import DetectionAdapter
from ai_runtime.app.model.registry import require_adapter
from ai_runtime.app.model.rknn import RknnAdapter

ModelLease = tuple[tuple[int, str], ...]


class ModelCapacityError(ValueError):
    """The bounded pool cannot admit a request without disrupting an active user."""


class ModelUnavailableError(ValueError):
    """A task references a model that cannot be restored from verified local storage."""


@dataclass(frozen=True)
class PoolEntry:
    sha256: str
    execution_contract: str
    artifact_format: str
    backend: str
    adapter: ExecutableAdapter


class ModelPool:
    def __init__(
        self,
        max_models: int = 4,
        dependencies: DependencyManager | None = None,
        onnx_intra_op_threads: int = 2,
        isolate_rknn: bool = True,
        registry: DeployedModelRegistry | None = None,
    ) -> None:
        if max_models < 1:
            raise ValueError("max_models must be positive")
        self._max_models = max_models
        self._registry = registry
        self._entries: OrderedDict[tuple[int, str], PoolEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._pins: Counter[tuple[int, str]] = Counter()
        self._load_failures = 0
        self._inference_errors = 0
        self.dependencies = dependencies
        if not 1 <= onnx_intra_op_threads <= 32:
            raise ValueError("onnx_intra_op_threads must be between 1 and 32")
        self._onnx_intra_op_threads = onnx_intra_op_threads
        self._isolate_rknn = isolate_rknn

    async def uninstall(
        self, model_id: int, sha256: str, request_id: str, registry: DeployedModelRegistry
    ):
        async with self._lock:
            if registry.removal_completed(request_id, model_id, sha256):
                return
            keys = [key for key in self._entries if key[0] == model_id]
            if any(self._pins[key] for key in keys):
                raise ModelCapacityError("模型正在被任务或识别请求使用，请先停止后重试")
            # Persist the removal before evicting memory: a crash cannot restore the removed model.
            registry.remove(model_id, sha256, request_id)
            for key in keys:
                entry = self._entries.pop(key)
                await self._close_adapter(entry.adapter)

    async def deploy(self, request: DeployModelRequest) -> DeployModelResponse:
        async with self._lock:
            return await self._deploy_locked(request)

    async def _deploy_locked(self, request: DeployModelRequest) -> DeployModelResponse:
        digest = await asyncio.to_thread(_sha256, request.artifact_path)
        if digest != request.sha256:
            self._load_failures += 1
            raise ValueError("model artifact SHA256 mismatch")
        python = None
        if request.artifact_format == "RKNN" and self._isolate_rknn:
            python = Path(sys.executable)
        if (
            self.dependencies is not None
            and request.artifact_format not in {"ONNX", "RKNN"}
            and not (
                request.runtime_manifest is not None
                and request.runtime_manifest.decoder.type
                in {"FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN"}
            )
        ):
            python = await self.dependencies.ensure(request.artifact_format)
        key = (request.model_version_id, request.device)
        existing = self._entries.get(key)
        if (
            existing is not None
            and (not isinstance(existing.adapter, IsolatedAdapter) or existing.adapter.alive)
            and existing.sha256 == digest
            and existing.execution_contract == _execution_contract(request)
            and existing.artifact_format == request.artifact_format
        ):
            self._entries.move_to_end(key)
            return _deploy_response(request, existing.backend, reused=True)
        if existing is not None and self._pins[key]:
            raise ModelCapacityError(
                f"模型 {request.model_version_id} 正被使用，无法替换；请先停止关联任务"
            )
        if existing is None and len(self._entries) >= self._max_models:
            victim = next((item for item in self._entries if not self._pins[item]), None)
            if victim is None:
                raise ModelCapacityError(
                    f"模型缓存已满（{self._max_models} 个槽位均被占用）；请先停止其他任务或稍后重试"
                )
            evicted = self._entries.pop(victim)
            await self._close_adapter(evicted.adapter)
            del evicted
        try:
            adapter, backend = await self._new_adapter(request, python, digest)
        except (OSError, ValueError):
            self._load_failures += 1
            raise
        if existing is not None:
            await self._close_adapter(existing.adapter)
        self._entries[key] = PoolEntry(
            digest,
            _execution_contract(request),
            request.artifact_format,
            backend,
            adapter,
        )
        self._entries.move_to_end(key)
        return _deploy_response(request, backend, reused=False)

    def _construct_adapter(self, request, python, digest):
        if python is not None:
            adapter = IsolatedAdapter(python, request)
            return adapter, adapter.backend
        return _load_adapter(
            request.artifact_path,
            request.artifact_format,
            request.device,
            request.adapter,
            request.runtime_manifest,
            request.trusted_artifact,
            digest,
            self._onnx_intra_op_threads,
        )

    async def _new_adapter(self, request, python, digest):
        worker = asyncio.create_task(
            asyncio.to_thread(self._construct_adapter, request, python, digest)
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                adapter, _ = await worker
                await self._close_adapter(adapter)
            finally:
                raise

    async def acquire(
        self,
        model_ids: Iterable[int],
        registry: DeployedModelRegistry | None = None,
        device: str | None = None,
    ) -> ModelLease:
        """Load and reserve a complete model set before any caller starts using it."""
        ids = sorted(set(model_ids))
        registry = registry or self._registry
        async with self._lock:
            keys = []
            missing = set()
            for model_id in ids:
                matches = [
                    key
                    for key in self._entries
                    if key[0] == model_id and (device is None or key[1] == device)
                ]
                if len(matches) > 1:
                    raise ModelUnavailableError(
                        f"模型 {model_id} 存在多个执行设备，无法确定任务绑定"
                    )
                if matches and self.is_loaded(model_id, device):
                    keys.append(matches[0])
                else:
                    if matches:
                        key = matches[0]
                        if self._pins[key]:
                            raise ModelUnavailableError(
                                f"模型 {model_id} 的执行进程已退出，请先停止关联任务再启动"
                            )
                        stale = self._entries.pop(key)
                        await self._close_adapter(stale.adapter)
                    missing.add(model_id)
            requests = []
            if missing and registry is not None:
                try:
                    payloads = await asyncio.to_thread(registry.load_payloads, missing)
                    requests = [
                        DeployModelRequest.model_validate(value)
                        for value in payloads
                        if device is None or value["device"] == device
                    ]
                except (OSError, RuntimeError, ValueError) as error:
                    raise ModelUnavailableError(
                        f"模型 {', '.join(map(str, sorted(missing)))} "
                        "的本地文件校验失败，请重新部署模型"
                    ) from error
            absent = missing - {value.model_version_id for value in requests}
            if absent:
                raise ModelUnavailableError(
                    f"模型 {', '.join(map(str, sorted(absent)))} 未部署到当前节点，请先部署模型"
                )
            keys.extend((value.model_version_id, value.device) for value in requests)
            lease = tuple(keys)
            required = set(keys) | {key for key, count in self._pins.items() if count}
            if len(required) > self._max_models:
                raise ModelCapacityError(
                    f"任务与当前占用共需 {len(required)} 个模型槽位，"
                    f"节点上限为 {self._max_models}；"
                    "请先停止其他任务或选择其他节点"
                )
            self._pins.update(lease)
            try:
                for value in requests:
                    await self._deploy_locked(value)
                for key in lease:
                    self._entries.move_to_end(key)
                return lease
            except BaseException:
                self._release_locked(lease)
                raise

    def _release_locked(self, lease: ModelLease) -> None:
        for key in lease:
            self._pins[key] -= 1
            if self._pins[key] <= 0:
                del self._pins[key]

    async def release(self, lease: ModelLease) -> None:
        async with self._lock:
            self._release_locked(lease)

    async def _inference(self, key, function, *args):
        # Cancelling an asyncio waiter does not stop its worker thread. Keep the
        # adapter pinned until the native call has actually returned.
        worker = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await worker
            finally:
                raise
        finally:
            await self.release((key,))

    async def test(
        self, request: ModelTestRequest, image: Image.Image | None = None
    ) -> ModelTestResult:
        key, entry = await self._borrow(request.model_version_id, request.device)
        try:
            if image is not None and (
                isinstance(entry.adapter, (GenericOnnxAdapter, RknnAdapter, FacePairAdapter))
                or (isinstance(entry.adapter, IsolatedAdapter) and entry.artifact_format == "RKNN")
            ):
                return await self._inference(
                    key, entry.adapter.infer_image, image, request.parameters
                )
            return await self._inference(
                key, entry.adapter.infer, str(request.image_path), request.parameters
            )
        except (OSError, ValueError):
            self._inference_errors += 1
            raise

    async def compare_faces(
        self, version_id: int, reference: Image.Image, candidate: Image.Image
    ) -> dict:
        key, entry = await self._borrow(version_id)
        if not isinstance(entry.adapter, FacePairAdapter):
            await self.release((key,))
            raise ModelUnavailableError("该模型不支持人脸比对")
        return await self._inference(key, entry.adapter.compare, reference, candidate)

    async def extract_face(self, version_id: int, image: Image.Image):
        key, entry = await self._borrow(version_id)
        adapter = entry.adapter
        if not isinstance(adapter, FacePairAdapter):
            await self.release((key,))
            raise ModelUnavailableError("该模型不支持人脸特征提取")
        try:
            feature, location = await self._inference(key, adapter.extract, image)
        except FaceQualityError as error:
            error.backend, error.device = adapter.backend, adapter.device
            raise
        return feature, location, adapter.backend, adapter.device

    async def locate_faces(self, version_id: int, image: Image.Image):
        key, entry = await self._borrow(version_id)
        if not isinstance(entry.adapter, FacePairAdapter):
            await self.release((key,))
            raise ModelUnavailableError("该模型不支持入口人脸定位")
        return await self._inference(key, entry.adapter.locate, image)

    async def _borrow(self, model_id: int, device: str | None = None):
        lease = await self.acquire([model_id], device=device)
        key = lease[0]
        return key, self._entries[key]

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def capacity(self) -> int:
        return self._max_models

    @property
    def load_failures(self) -> int:
        return self._load_failures

    @property
    def inference_errors(self) -> int:
        return self._inference_errors

    def is_loaded(self, model_version_id: int, device: str | None = None) -> bool:
        return any(
            key[0] == model_version_id
            and (device is None or key[1] == device)
            and (not isinstance(entry.adapter, IsolatedAdapter) or entry.adapter.alive)
            for key, entry in self._entries.items()
        )

    @staticmethod
    async def _close_adapter(adapter: ExecutableAdapter) -> None:
        if isinstance(adapter, (IsolatedAdapter, RknnAdapter, RknnFacePairAdapter)):
            await asyncio.to_thread(adapter.close)

    async def close(self) -> None:
        for entry in self._entries.values():
            await self._close_adapter(entry.adapter)
        self._entries.clear()
        self._pins.clear()
        if self.dependencies is not None:
            await self.dependencies.close()


def _deploy_response(
    request: DeployModelRequest, backend: str, reused: bool
) -> DeployModelResponse:
    return DeployModelResponse(
        modelVersionId=request.model_version_id,
        backend=backend,
        device=request.device,
        reused=reused,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_adapter(
    path: Path,
    artifact_format: str,
    device: str,
    adapter_name: str,
    runtime_manifest,
    trusted_artifact: bool,
    digest: str,
    onnx_intra_op_threads: int = 2,
) -> tuple[ExecutableAdapter, str]:
    if runtime_manifest is not None and runtime_manifest.decoder.type in {
        "FACE_PAIR_SFACE",
        "FACE_PAIR_SFACE_RKNN",
    }:
        npu_pair = runtime_manifest.decoder.type == "FACE_PAIR_SFACE_RKNN"
        if artifact_format != "ARCHIVE" or device != ("RKNPU" if npu_pair else "CPU"):
            raise ValueError("face pair artifact/device mismatch")
        directory, members = extract_archive(path, digest)
        if npu_pair:
            if members or {item.name for item in directory.glob("*.rknn")} != {
                "detector.rknn",
                "recognizer.rknn",
            }:
                raise ValueError("RKNN face archive must contain only the fixed pair")
            adapter = RknnFacePairAdapter(directory)
            return adapter, adapter.backend
        if {member.relative_to(directory).as_posix() for member in members} != {
            "detector.onnx",
            "recognizer.onnx",
        }:
            raise ValueError("face pair archive must contain detector.onnx and recognizer.onnx")
        adapter = FacePairAdapter(directory, onnx_intra_op_threads)
        return adapter, adapter.backend
    definition = require_adapter(adapter_name) if adapter_name else None
    if artifact_format == "RKNN":
        if device != "RKNPU" or runtime_manifest is None:
            raise ValueError("RKNN requires RKNPU and a runtime manifest")
        return RknnAdapter(path, runtime_manifest), "RKNN_RUNTIME_MANIFEST"
    if artifact_format == "ONNX":
        try:
            options = ort.SessionOptions()
            options.intra_op_num_threads = onnx_intra_op_threads
            options.inter_op_num_threads = 1
            # Multiple model sessions share edge CPUs with decode, WebRTC and the Agent.
            # Idle worker spinning competes with the next model in a PPE pipeline.
            options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            options.add_session_config_entry("session.inter_op.allow_spinning", "0")
            session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as error:
            raise ValueError(f"invalid or unsupported ONNX artifact: {error}") from error
        if runtime_manifest is not None:
            if runtime_manifest.decoder.type == "LPRNET":
                return LprNetAdapter(session, device), "ONNX_RUNTIME_MANIFEST_LPRNET"
            if runtime_manifest.decoder.type == "LPD_YUNET":
                return LicensePlateYuNetAdapter(session, device), "ONNX_RUNTIME_MANIFEST_LPD_YUNET"
            return GenericOnnxAdapter(session, device, runtime_manifest), "ONNX_RUNTIME_MANIFEST"
        if adapter_name == "license_plate_ocr_v1":
            return LprNetAdapter(session, device), "ONNX_RUNTIME_LPRNET"
        if adapter_name == "license_plate_v1":
            return LicensePlateYuNetAdapter(session, device), "ONNX_RUNTIME_LPD_YUNET"
        return (
            DetectionAdapter(session, device, definition.name, definition.class_labels),
            "ONNX_RUNTIME",
        )
    if artifact_format == "TORCHSCRIPT":
        if definition is None:
            raise ValueError("TorchScript manifest execution is not implemented")
        return TorchScriptAdapter(path, device, definition), "TORCHSCRIPT_CPU"
    if artifact_format == "PYTORCH":
        if definition is None:
            if runtime_manifest is None or runtime_manifest.decoder.type != "AUTO_DETECTION":
                raise ValueError("PyTorch manifest requires AUTO_DETECTION")
            from ai_runtime.app.model.registry import AdapterDefinition

            definition = AdapterDefinition("manifest", runtime_manifest.decoder.labels)
        return load_pytorch_checkpoint(path, device, definition, trusted_artifact)
    if artifact_format != "ARCHIVE":
        raise ValueError(f"unsupported model artifact format: {artifact_format}")
    _, executable = extract_archive(path, digest)
    if not executable:
        raise ValueError(
            "archive contains no directly executable ONNX/PT/TorchScript member; "
            "a model-family pipeline adapter is required"
        )
    if len(executable) == 1:
        nested_format = _format_from_path(executable[0])
        return _load_adapter(
            executable[0],
            nested_format,
            device,
            adapter_name,
            runtime_manifest,
            trusted_artifact,
            digest,
            onnx_intra_op_threads,
        )
    if adapter_name == "smoking_phone_detection_v1":
        loaded = [
            _load_adapter(
                member,
                _format_from_path(member),
                device,
                adapter_name,
                runtime_manifest,
                trusted_artifact,
                digest,
                onnx_intra_op_threads,
            )[0]
            for member in executable
        ]
        return MergedAdapter(loaded, "ARCHIVE_MULTI_MODEL_CPU"), "ARCHIVE_MULTI_MODEL_CPU"
    raise ValueError(
        f"archive contains {len(executable)} executable members; adapter {adapter_name} "
        "requires an explicit multi-stage pipeline instead of arbitrary member selection"
    )


def _execution_contract(request: DeployModelRequest) -> str:
    if request.runtime_manifest is not None:
        return request.runtime_manifest.model_dump_json(by_alias=True)
    return f"legacy:{request.adapter}"


def _format_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".onnx":
        return "ONNX"
    if suffix in {".jit", ".torchscript"}:
        return "TORCHSCRIPT"
    if suffix in {".pt", ".pth"}:
        return "PYTORCH"
    raise ValueError(f"unsupported executable member: {path.name}")
