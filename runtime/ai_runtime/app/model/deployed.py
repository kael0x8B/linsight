import fcntl
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

LOGGER = logging.getLogger("linsight.edge_agent.models")


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(item.capitalize() for item in tail)


class DeployedModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        populate_by_name=True,
    )

    model_version_id: int = Field(gt=0)
    artifact_relative_path: str = Field(min_length=1)
    artifact_format: Literal["ONNX", "TORCHSCRIPT", "PYTORCH", "ARCHIVE", "RKNN"]
    trusted_artifact: bool
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    adapter: str | None = Field(default=None, min_length=1)
    runtime_manifest: dict[str, Any] | None = None
    device: Literal["CPU", "RKNPU"] = "CPU"

    @model_validator(mode="after")
    def validate_device(self):
        npu_pair = (
            self.artifact_format == "ARCHIVE"
            and (self.runtime_manifest or {}).get("decoder", {}).get("type")
            == "FACE_PAIR_SFACE_RKNN"
        )
        if (self.artifact_format == "RKNN" or npu_pair) != (self.device == "RKNPU"):
            raise ValueError("Model format and execution device disagree")
        return self


class DeployedModelDocument(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        populate_by_name=True,
    )

    schema_version: Literal[1] = 1
    models: list[DeployedModel] = Field(default_factory=list)
    removals: dict[str, str] = Field(default_factory=dict)


class DeployedModelRegistry:
    """Persist only verified local model metadata required to warm a restarted Runtime."""

    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root.resolve()
        self._models_root = (self._data_root / "models").resolve()
        self._path = self._models_root / "deployed-models.json"

    def record(self, deploy_payload: dict[str, Any]) -> None:
        self._models_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Agent compatibility writes and local uploads may occur in different processes.
        with (self._models_root / ".registry.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                self._record(deploy_payload)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _record(self, deploy_payload: dict[str, Any]) -> None:
        artifact = Path(str(deploy_payload["artifactPath"])).resolve(strict=True)
        artifact.relative_to(self._models_root)
        if not artifact.is_file():
            raise ValueError("deployed model artifact is not a regular file")
        expected_sha256 = str(deploy_payload["sha256"])
        if _sha256(artifact) != expected_sha256:
            raise ValueError("deployed model artifact checksum changed before persistence")

        document = self._read_document()
        model = DeployedModel.model_validate(
            {
                **deploy_payload,
                "artifactRelativePath": str(artifact.relative_to(self._data_root)),
            }
        )
        models = [
            item for item in document.models if item.model_version_id != model.model_version_id
        ]
        models.append(model)
        self._write_document(
            DeployedModelDocument(
                models=sorted(models, key=lambda item: item.model_version_id),
                removals=document.removals,
            )
        )

    def remove(self, model_id: int, sha256: str, request_id: str) -> None:
        self._models_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self._models_root / ".registry.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                document = self._read_document()
                fingerprint = f"{model_id}:{sha256}"
                if request_id in document.removals:
                    if document.removals[request_id] != fingerprint:
                        raise ValueError("uninstall request identity conflict")
                    return
                current = next((m for m in document.models if m.model_version_id == model_id), None)
                if current and current.sha256 != sha256:
                    raise ValueError("model changed; refresh before uninstalling")
                remaining = [m for m in document.models if m.model_version_id != model_id]
                document.models = remaining
                document.removals[request_id] = fingerprint
                self._write_document(document)
                if current and not any(
                    m.artifact_relative_path == current.artifact_relative_path for m in remaining
                ):
                    path = (self._data_root / current.artifact_relative_path).resolve()
                    path.relative_to(self._models_root)
                    path.unlink(missing_ok=True)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def removal_completed(self, request_id: str, model_id: int, sha256: str) -> bool:
        value = self._read_document().removals.get(request_id)
        if value is not None and value != f"{model_id}:{sha256}":
            raise ValueError("uninstall request identity conflict")
        return value is not None

    def summaries(self) -> list[dict[str, Any]]:
        return [
            {
                key: value
                for key, value in item.model_dump(by_alias=True, exclude_none=True).items()
                if key != "artifactRelativePath"
            }
            for item in self._read_document().models
        ]

    def load_payloads(self, model_ids: set[int] | None = None) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for model in self._read_document().models:
            if model_ids is not None and model.model_version_id not in model_ids:
                continue
            try:
                artifact = (self._data_root / model.artifact_relative_path).resolve(strict=True)
                artifact.relative_to(self._models_root)
                if not artifact.is_file() or _sha256(artifact) != model.sha256:
                    raise ValueError("artifact is missing or checksum verification failed")
                payloads.append(
                    {
                        "modelVersionId": model.model_version_id,
                        "artifactPath": str(artifact),
                        "artifactFormat": model.artifact_format,
                        "trustedArtifact": model.trusted_artifact,
                        "sha256": model.sha256,
                        "device": model.device,
                        **({"adapter": model.adapter} if model.adapter is not None else {}),
                        **(
                            {"runtimeManifest": model.runtime_manifest}
                            if model.runtime_manifest is not None
                            else {}
                        ),
                    }
                )
            except (OSError, ValueError) as error:
                LOGGER.error(
                    "Persisted model cannot be restored modelVersionId=%s errorType=%s",
                    model.model_version_id,
                    type(error).__name__,
                )
                raise RuntimeError(
                    f"persisted model {model.model_version_id} failed local verification"
                ) from error
        return payloads

    def _read_document(self) -> DeployedModelDocument:
        if not self._path.exists():
            return DeployedModelDocument()
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            return DeployedModelDocument.model_validate(value)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise RuntimeError("deployed model registry is invalid") from error

    def _write_document(self, document: DeployedModelDocument) -> None:
        self._models_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self._path.with_name(f".{self._path.name}.{uuid.uuid4().hex}.tmp")
        try:
            payload = document.model_dump(by_alias=True, exclude_none=True)
            if not document.removals:
                payload.pop("removals", None)
            temporary.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            os.chmod(temporary, 0o600)
            with temporary.open("rb") as durable:
                os.fsync(durable.fileno())
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
