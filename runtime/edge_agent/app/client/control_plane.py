from typing import Any

import httpx
from pydantic import BaseModel, Field, SecretStr

from edge_agent.app.core.identity import NodeIdentity


class ControlPlaneRejectedError(RuntimeError):
    def __init__(self, code: int | None) -> None:
        self.code = code
        super().__init__(f"Control plane rejected request with code {code}")


class RegistrationResponse(BaseModel):
    node_id: int = Field(alias="nodeId", gt=0)
    tenant_id: int = Field(alias="tenantId", gt=0)
    credential: SecretStr


class StreamCheckAssignment(BaseModel):
    check_id: int = Field(alias="checkId", gt=0)
    camera_id: int = Field(alias="cameraId", gt=0)
    protocol: str
    host: str
    port: int
    stream_uri: SecretStr = Field(alias="streamUri")
    username: SecretStr | None = None
    password: SecretStr | None = None


class NodeCommandAssignment(BaseModel):
    command_id: str = Field(alias="commandId")
    command_type: str = Field(alias="commandType")
    aggregate_id: int = Field(alias="aggregateId", gt=0)
    config_version: int = Field(alias="configVersion", gt=0)
    idempotency_key: str = Field(alias="idempotencyKey")


class ModelCommandDetail(BaseModel):
    command_id: str = Field(alias="commandId")
    command_type: str = Field(alias="commandType")
    config_version: int = Field(alias="configVersion")
    model_version_id: int = Field(alias="modelVersionId")
    display_name: str | None = Field(default=None, alias="modelName")
    version: str | None = Field(default=None, alias="modelVersion")
    artifact_url: SecretStr = Field(alias="artifactUrl")
    artifact_name: str = Field(alias="artifactName")
    artifact_format: str = Field(alias="artifactFormat")
    trusted_artifact: bool = Field(default=False, alias="trustedArtifact")
    sha256: str
    adapter: str | None = None
    runtime_manifest: dict[str, Any] | None = Field(default=None, alias="runtimeManifest")
    image_url: SecretStr | None = Field(default=None, alias="imageUrl")
    image_name: str | None = Field(default=None, alias="imageName")
    parameters: dict[str, Any] | None = None


class TaskCommandDetail(BaseModel):
    algorithm_package_url: SecretStr | None = Field(default=None, alias="algorithmPackageUrl")
    algorithm_resources: dict[str, Any] | None = Field(
        default=None, alias="algorithmResources", exclude=True
    )
    expected_gateway_revision: int | None = Field(
        default=None, alias="expectedGatewayRevision", ge=0
    )
    command_id: str = Field(alias="commandId")
    command_type: str = Field(alias="commandType")
    config_version: int = Field(alias="configVersion", gt=0)
    task_id: int = Field(alias="taskId", gt=0)
    run_id: str = Field(alias="runId")
    camera_id: int = Field(alias="cameraId", gt=0)
    stream_url: SecretStr | None = Field(default=None, alias="streamUrl")
    stream_urls: dict[str, SecretStr] | None = Field(default=None, alias="streamUrls")
    algorithm_id: int = Field(alias="algorithmId", gt=0)
    pipeline_version_id: int = Field(alias="pipelineVersionId", gt=0)
    pipeline: dict[str, Any]
    display_names: dict[str, str] | None = Field(default=None, alias="displayNames")
    model_version_id: int = Field(alias="modelVersionId", gt=0)
    model_bindings: dict[str, int] = Field(default_factory=dict, alias="modelBindings")
    rule_id: int | None = Field(default=None, alias="ruleId", gt=0)
    rule_version_id: int | None = Field(default=None, alias="ruleVersionId", gt=0)
    rule: dict[str, Any] | None = None
    parameters: dict[str, Any]
    global_settings_version: int = Field(default=0, alias="globalSettingsVersion", ge=0)
    global_settings: dict[str, Any] | None = Field(default=None, alias="globalSettings")


class UpgradeCommandDetail(BaseModel):
    command_id: str = Field(alias="commandId")
    command_type: str = Field(alias="commandType")
    config_version: int = Field(alias="configVersion", gt=0)
    target_version: str | None = Field(default=None, alias="targetVersion")
    package_url: SecretStr | None = Field(default=None, alias="packageUrl")
    package_name: str | None = Field(default=None, alias="packageName")
    sha256: str | None = None
    signature: str | None = None


class ControlPlaneClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            # 节点凭据只发送到显式配置的控制面，不能被宿主机代理环境转发。
            trust_env=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def register(
        self,
        bootstrap_token: SecretStr,
        code: str,
        name: str,
        agent_version: str,
        host_name: str,
    ) -> NodeIdentity:
        response = await self._client.post(
            "/node-api/ai-video/node/register",
            json={
                "bootstrapToken": bootstrap_token.get_secret_value(),
                "code": code,
                "name": name,
                "agentVersion": agent_version,
                "hostName": host_name,
            },
        )
        data = self._checked_data(response)
        registration = RegistrationResponse.model_validate(data)
        return NodeIdentity(
            node_id=registration.node_id,
            tenant_id=registration.tenant_id,
            credential=registration.credential,
        )

    async def heartbeat(self, identity: NodeIdentity, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            "/node-api/ai-video/node/heartbeat",
            headers={
                "tenant-id": str(identity.tenant_id),
                "X-Node-Id": str(identity.node_id),
                "X-Node-Credential": identity.credential.get_secret_value(),
            },
            json=payload,
        )
        return self._checked_data(response)

    async def pull_stream_check(self, identity: NodeIdentity) -> StreamCheckAssignment | None:
        response = await self._client.post(
            "/node-api/ai-video/camera/check/pull",
            headers=self._node_headers(identity),
        )
        data = self._checked_optional_data(response)
        return None if data is None else StreamCheckAssignment.model_validate(data)

    async def report_stream_check(
        self,
        identity: NodeIdentity,
        payload: dict[str, Any],
    ) -> None:
        response = await self._client.post(
            "/node-api/ai-video/camera/check/report",
            headers=self._node_headers(identity),
            json=payload,
        )
        self._checked_envelope(response)

    async def pull_command(self, identity: NodeIdentity) -> NodeCommandAssignment | None:
        response = await self._client.post(
            "/node-api/ai-video/node/command/pull",
            headers=self._node_headers(identity),
        )
        data = self._checked_optional_data(response)
        return None if data is None else NodeCommandAssignment.model_validate(data)

    async def get_entry_stations(self, identity: NodeIdentity) -> list[dict]:
        response = await self._client.get(
            "/node-api/ai-video/task/entry-access/stations", headers=self._node_headers(identity)
        )
        return self._checked_envelope(response)["data"]

    async def start_entry_automatically(self, identity: NodeIdentity, payload: dict) -> int:
        response = await self._client.post(
            "/node-api/ai-video/task/entry-access/auto-start",
            headers=self._node_headers(identity),
            json=payload,
        )
        return self._checked_envelope(response)["data"]

    async def report_entry_station(self, identity: NodeIdentity, state: dict):
        response = await self._client.post(
            "/node-api/ai-video/task/entry-access/station-report",
            headers=self._node_headers(identity),
            params={key: state[key] for key in ("entryId", "version", "state")},
            json=state.get("frame"),
        )
        return self._checked_envelope(response)["data"]

    async def get_entry_command(
        self, identity: NodeIdentity, command_id: str, state: bool = False
    ) -> dict:
        response = await self._client.get(
            "/node-api/ai-video/task/entry-access/" + ("state" if state else "command"),
            headers=self._node_headers(identity),
            params={"commandId": command_id},
        )
        return self._checked_data(response)

    async def get_face_verification(self, identity: NodeIdentity, command_id: str) -> dict:
        response = await self._client.get(
            "/node-api/ai-video/task/face-verification/command",
            headers=self._node_headers(identity),
            params={"commandId": command_id},
        )
        return self._checked_data(response)

    async def get_model_command(
        self, identity: NodeIdentity, command_id: str
    ) -> ModelCommandDetail:
        response = await self._client.get(
            "/node-api/ai-video/model/command/get",
            headers=self._node_headers(identity),
            params={"commandId": command_id},
        )
        return ModelCommandDetail.model_validate(self._checked_data(response))

    async def get_task_command(self, identity: NodeIdentity, command_id: str) -> TaskCommandDetail:
        response = await self._client.get(
            "/node-api/ai-video/task/command/get",
            headers=self._node_headers(identity),
            params={"commandId": command_id},
        )
        return TaskCommandDetail.model_validate(self._checked_data(response))

    async def get_upgrade_command(
        self, identity: NodeIdentity, command_id: str
    ) -> UpgradeCommandDetail:
        response = await self._client.get(
            "/node-api/ai-video/node/upgrade/command/get",
            headers=self._node_headers(identity),
            params={"commandId": command_id},
        )
        return UpgradeCommandDetail.model_validate(self._checked_data(response))

    async def report_command(self, identity: NodeIdentity, payload: dict[str, Any]) -> None:
        response = await self._client.post(
            "/node-api/ai-video/node/command/report",
            headers=self._node_headers(identity),
            json=payload,
        )
        self._checked_envelope(response)

    async def report_task_runtime(self, identity: NodeIdentity, payload: dict[str, Any]) -> None:
        response = await self._client.post(
            "/node-api/ai-video/task/runtime/report",
            headers=self._node_headers(identity),
            json=payload,
        )
        self._checked_envelope(response)

    async def report_task_removal(self, identity: NodeIdentity, payload: dict[str, Any]) -> None:
        response = await self._client.post(
            "/node-api/ai-video/task/removal/report",
            headers=self._node_headers(identity),
            json=payload,
        )
        self._checked_envelope(response)

    async def report_overlay(self, identity: NodeIdentity, payload: dict[str, Any]) -> None:
        response = await self._client.post(
            "/node-api/ai-video/camera/overlay/report",
            headers=self._node_headers(identity),
            json=payload,
        )
        self._checked_envelope(response)

    async def report_logs(self, identity: NodeIdentity, entries: list[dict[str, Any]]) -> None:
        response = await self._client.post(
            "/node-api/ai-video/node/log/batch",
            headers=self._node_headers(identity),
            json={"entries": entries},
        )
        self._checked_envelope(response)

    async def ingest_event(self, identity: NodeIdentity, payload: dict[str, Any]) -> int:
        response = await self._client.post(
            "/node-api/ai-video/event/ingest",
            headers=self._node_headers(identity),
            json=payload,
        )
        envelope = self._checked_envelope(response)
        value = envelope.get("data")
        if not isinstance(value, int):
            raise RuntimeError("Control plane event id is invalid")
        return value

    async def upload_event_media(
        self,
        identity: NodeIdentity,
        event_id: int,
        media_type: str,
        path,
        content_type: str,
    ) -> int:
        with path.open("rb") as stream:
            response = await self._client.post(
                f"/node-api/ai-video/event/{event_id}/media",
                headers=self._node_headers(identity),
                params={"mediaType": media_type},
                files={"file": (path.name, stream, content_type)},
            )
        envelope = self._checked_envelope(response)
        value = envelope.get("data")
        if not isinstance(value, int):
            raise RuntimeError("Control plane media id is invalid")
        return value

    async def report_event_transition(
        self, identity: NodeIdentity, payload: dict[str, Any]
    ) -> None:
        response = await self._client.post(
            "/node-api/ai-video/event/transition",
            headers=self._node_headers(identity),
            json=payload,
        )
        self._checked_envelope(response)

    @staticmethod
    def _node_headers(identity: NodeIdentity) -> dict[str, str]:
        return {
            "tenant-id": str(identity.tenant_id),
            "X-Node-Id": str(identity.node_id),
            "X-Node-Credential": identity.credential.get_secret_value(),
        }

    @staticmethod
    def _checked_data(response: httpx.Response) -> dict[str, Any]:
        data = ControlPlaneClient._checked_optional_data(response)
        if data is None:
            raise RuntimeError("Control plane response data is invalid")
        return data

    @staticmethod
    def _checked_optional_data(response: httpx.Response) -> dict[str, Any] | None:
        envelope = ControlPlaneClient._checked_envelope(response)
        data = envelope.get("data")
        if data is None:
            return None
        if not isinstance(data, dict):
            raise RuntimeError("Control plane response data is invalid")
        return data

    @staticmethod
    def _checked_envelope(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        envelope = response.json()
        if not isinstance(envelope, dict):
            raise RuntimeError("Control plane response envelope is invalid")
        if envelope.get("code") != 0:
            code = envelope.get("code")
            raise ControlPlaneRejectedError(code if isinstance(code, int) else None)
        return envelope
