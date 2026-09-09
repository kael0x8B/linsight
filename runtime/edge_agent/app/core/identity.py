import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class NodeIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    credential: SecretStr
    heartbeat_sequence: int = Field(default=0, ge=0)


class IdentityStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> NodeIdentity | None:
        if not self._path.exists():
            return None
        mode = self._path.stat().st_mode & 0o777
        if mode & 0o077:
            raise PermissionError("Node credential file must not be accessible by group or others")
        return NodeIdentity.model_validate_json(self._path.read_text(encoding="utf-8"))

    def save(self, identity: NodeIdentity) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = identity.model_dump(mode="json")
        payload["credential"] = identity.credential.get_secret_value()
        descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
