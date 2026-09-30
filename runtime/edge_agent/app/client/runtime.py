from typing import Any

import httpx
from pydantic import SecretStr


class RuntimeClient:
    def __init__(self, base_url: str, api_key: SecretStr, timeout_seconds: float) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"X-Runtime-Key": api_key.get_secret_value()},
            trust_env=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def dry_run_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/v1/rules/dry-run", json=payload)
        response.raise_for_status()
        result = response.json()
        # The engine includes the full immutable AST in every transition. Keep
        # the trial response bounded without evaluating any rules in the agent.
        return {
            "confirmed": result["confirmed"],
            "transitions": [
                {
                    key: transition.get(key)
                    for key in ("state", "occurredAtMillis", "trackId", "eventType")
                }
                for transition in result["transitions"]
            ],
        }

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/v1/models/deploy", json=payload, timeout=150.0)
        response.raise_for_status()
        return response.json()

    async def entry_access(self, payload: dict) -> dict:
        response = await self._client.post("/v1/tasks/entry-access", json=payload, timeout=125)
        response.raise_for_status()
        return response.json()

    async def sync_entry_stations(self, stations: list[dict]) -> list[dict]:
        response = await self._client.post(
            "/v1/tasks/entry-stations/sync", json={"stations": stations}
        )
        response.raise_for_status()
        return response.json()

    async def acknowledge_entry_station(self, entry_id: int, encounter_id: str, completed: bool):
        response = await self._client.post(
            "/v1/tasks/entry-stations/ack",
            json={"entryId": entry_id, "encounterId": encounter_id, "completed": completed},
        )
        response.raise_for_status()

    async def cancel_entry(self, session_id: str) -> None:
        from uuid import UUID

        response = await self._client.post(f"/v1/tasks/entry-access/{UUID(session_id)}/cancel")
        response.raise_for_status()

    async def verify_face(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/tasks/face-verification",
            json=payload,
            timeout=35.0,
        )
        response.raise_for_status()
        return response.json()

    async def test(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/v1/models/test", json=payload, timeout=150.0)
        response.raise_for_status()
        return response.json()

    async def prepare_dependencies(self, artifact_format: str) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/models/dependencies/prepare", json={"artifactFormat": artifact_format}
        )
        response.raise_for_status()
        return response.json()

    async def dependency_status(self, profile: str) -> dict[str, Any]:
        response = await self._client.get(f"/v1/models/dependencies/{profile}")
        response.raise_for_status()
        return response.json()

    async def start_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        revision = payload.pop("expectedGatewayRevision", None)
        headers = {} if revision is None else {"X-Gateway-Revision": str(revision)}
        response = await self._client.post(
            "/v1/tasks/start", json=payload, headers=headers, timeout=150.0
        )
        response.raise_for_status()
        return response.json()

    async def stop_task(
        self, task_id: int, run_id: str, expected_revision: int | None = None
    ) -> dict[str, Any]:
        # Stopping drains event video before acknowledging; an encoder alone may
        # legitimately take longer than the ordinary 10-second API budget.
        response = await self._client.delete(
            f"/v1/tasks/{task_id}",
            params={"runId": run_id},
            timeout=150.0,
            headers={}
            if expected_revision is None
            else {"X-Gateway-Revision": str(expected_revision)},
        )
        response.raise_for_status()
        return response.json()

    async def apply_task_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/v1/tasks/settings/apply", json=payload)
        response.raise_for_status()
        return response.json()

    async def gateway_rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/gateway/rpc", json=payload, timeout=150.0, headers={"X-Gateway-Origin": "PLATFORM"}
        )
        response.raise_for_status()
        return response.json()

    async def task_statuses(self) -> list[dict[str, Any]]:
        response = await self._client.get("/v1/tasks/statuses")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("Runtime task status response is invalid")
        return data

    async def observability_snapshot(self) -> dict[str, Any]:
        response = await self._client.get("/v1/observability/snapshot")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Runtime observability response is invalid")
        return data

    async def create_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/v1/preview/sessions", json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Runtime preview response is invalid")
        return data

    async def get_preview(self, session_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/v1/preview/sessions/{session_id}")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Runtime preview response is invalid")
        return data

    async def get_preview_media(self, session_id: str, file_name: str) -> tuple[bytes, str]:
        response = await self._client.get(f"/v1/preview/sessions/{session_id}/media/{file_name}")
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream")

    async def release_preview(self, session_id: str) -> None:
        response = await self._client.delete(f"/v1/preview/sessions/{session_id}")
        response.raise_for_status()

    async def create_webrtc(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/v1/webrtc/sessions/offer", json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Runtime WebRTC response is invalid")
        return data

    async def get_webrtc(self, session_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/v1/webrtc/sessions/{session_id}")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Runtime WebRTC response is invalid")
        return data

    async def release_webrtc(self, session_id: str) -> None:
        response = await self._client.delete(f"/v1/webrtc/sessions/{session_id}")
        response.raise_for_status()

    async def pending_events(self) -> dict[str, Any]:
        response = await self._client.get("/v1/events/pending")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Runtime event delivery response is invalid")
        return data

    async def pending_overlays(self) -> list[dict[str, Any]]:
        response = await self._client.get("/v1/overlays/pending")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("Runtime overlay response is invalid")
        return data

    async def acknowledge_event(self, source_event_id: str) -> None:
        response = await self._client.post(f"/v1/events/{source_event_id}/ack")
        response.raise_for_status()

    async def defer_event(self, source_event_id: str) -> None:
        response = await self._client.post(f"/v1/events/{source_event_id}/defer")
        response.raise_for_status()

    async def acknowledge_transition(self, delivery_key: str) -> None:
        response = await self._client.post(
            "/v1/event-transitions/ack", params={"deliveryKey": delivery_key}
        )
        response.raise_for_status()

    async def defer_transition(self, delivery_key: str) -> None:
        response = await self._client.post(
            "/v1/event-transitions/defer", params={"deliveryKey": delivery_key}
        )
        response.raise_for_status()

    async def dead_letter_transition(self, delivery_key: str, reason: str) -> None:
        response = await self._client.post(
            "/v1/event-transitions/dead-letter",
            params={"deliveryKey": delivery_key, "reason": reason},
        )
        response.raise_for_status()
