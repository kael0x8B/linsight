import asyncio
import ipaddress
import json
import logging
from contextlib import suppress
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID, uuid4

import httpx
from websockets.asyncio.client import ClientConnection, connect

from edge_agent.app.client.runtime import RuntimeClient
from edge_agent.app.core.config import AgentSettings
from edge_agent.app.core.identity import NodeIdentity

LOGGER = logging.getLogger("linsight.edge_agent.preview_tunnel")
PROTOCOL_VERSION = "1.0"
MEDIA_FILES = {"index.m3u8"}


async def preview_tunnel_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    runtime: RuntimeClient,
) -> None:
    if not settings.preview_tunnel_enabled:
        LOGGER.info("Preview tunnel disabled nodeId=%s", identity.node_id)
        return
    uri = _tunnel_uri(settings)
    retry_seconds = 1.0
    while True:
        try:
            async with connect(
                uri,
                additional_headers={
                    "tenant-id": str(identity.tenant_id),
                    "X-Node-Id": str(identity.node_id),
                    "X-Node-Credential": identity.credential.get_secret_value(),
                },
                max_size=64 * 1024,
                proxy=None,
                ping_interval=20,
                ping_timeout=20,
                open_timeout=settings.request_timeout_seconds,
            ) as websocket:
                LOGGER.info("Preview tunnel connected nodeId=%s", identity.node_id)
                retry_seconds = 1.0
                await _serve(websocket, settings, runtime)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOGGER.warning(
                "Preview tunnel disconnected nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
        await asyncio.sleep(retry_seconds)
        retry_seconds = min(retry_seconds * 2, 30.0)


async def _serve(
    websocket: ClientConnection,
    settings: AgentSettings,
    runtime: RuntimeClient,
) -> None:
    send_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(settings.preview_tunnel_concurrency)
    workers: set[asyncio.Task[None]] = set()
    try:
        async for raw in websocket:
            if not isinstance(raw, str):
                continue
            worker = asyncio.create_task(
                _handle_request(websocket, send_lock, semaphore, settings, runtime, raw)
            )
            workers.add(worker)
            worker.add_done_callback(workers.discard)
    finally:
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker


async def _handle_request(
    websocket: ClientConnection,
    send_lock: asyncio.Lock,
    semaphore: asyncio.Semaphore,
    settings: AgentSettings,
    runtime: RuntimeClient,
    raw: str,
) -> None:
    request_id: str | None = None
    request: Any = None
    async with semaphore:
        try:
            request = json.loads(raw)
            if not isinstance(request, dict) or request.get("version") != PROTOCOL_VERSION:
                raise PreviewTunnelError("INVALID_PROTOCOL", "unsupported tunnel protocol")
            request_id = _request_id(request.get("requestId"))
            action = request.get("action")
            payload = request.get("payload")
            if not isinstance(payload, dict):
                raise PreviewTunnelError("INVALID_PAYLOAD", "preview payload must be an object")
            if action == "preview.create":
                response = await runtime.create_preview(_create_payload(payload))
                await _send_json(websocket, send_lock, _success(request_id, response))
            elif action == "preview.get":
                response = await runtime.get_preview(_session_id(payload))
                await _send_json(websocket, send_lock, _success(request_id, response))
            elif action == "preview.release":
                await runtime.release_preview(_session_id(payload))
                await _send_json(websocket, send_lock, _success(request_id, {}))
            elif action == "preview.media":
                await _send_media(websocket, send_lock, settings, runtime, request_id, payload)
            elif action == "rule.dry-run":
                response = await runtime.dry_run_rule(payload)
                await _send_json(websocket, send_lock, _success(request_id, response))
            elif action == "gateway.rpc":
                response = await runtime.gateway_rpc(payload)
                await _send_json(websocket, send_lock, _success(request_id, response))
            elif action == "runtime.health":
                response = await runtime.observability_snapshot()
                await _send_json(websocket, send_lock, _success(request_id, response))
            elif action == "webrtc.offer":
                response = await runtime.create_webrtc(_webrtc_offer_payload(payload))
                await _send_json(websocket, send_lock, _success(request_id, response))
            elif action == "webrtc.get":
                response = await runtime.get_webrtc(_session_id(payload))
                await _send_json(websocket, send_lock, _success(request_id, response))
            elif action == "webrtc.release":
                await runtime.release_webrtc(_session_id(payload))
                await _send_json(websocket, send_lock, _success(request_id, {}))
            else:
                raise PreviewTunnelError("ACTION_NOT_ALLOWED", "preview action is not allowed")
        except asyncio.CancelledError:
            raise
        except Exception as error:  # every request must receive a bounded, sanitized response
            diagnostic_id, error_code, message = _safe_error(error)
            if request_id is not None:
                await _send_json(
                    websocket,
                    send_lock,
                    {
                        "version": PROTOCOL_VERSION,
                        "requestId": request_id,
                        "ok": False,
                        "errorCode": error_code,
                        "errorMessage": message,
                        "diagnosticId": diagnostic_id,
                    },
                )
            LOGGER.warning(
                "Preview tunnel request failed action=%s diagnosticId=%s errorType=%s",
                request.get("action") if isinstance(request, dict) else None,
                diagnostic_id,
                type(error).__name__,
            )


async def _send_media(
    websocket: ClientConnection,
    send_lock: asyncio.Lock,
    settings: AgentSettings,
    runtime: RuntimeClient,
    request_id: str,
    payload: dict[str, Any],
) -> None:
    file_name = payload.get("fileName")
    if not isinstance(file_name, str) or (
        file_name not in MEDIA_FILES
        and not (file_name.startswith("segment-") and file_name.endswith(".ts")
                 and len(file_name) == len("segment-000000.ts")
                 and file_name[8:14].isdigit())
    ):
        raise PreviewTunnelError("INVALID_MEDIA_NAME", "preview media name is invalid")
    body, content_type = await runtime.get_preview_media(_session_id(payload), file_name)
    if len(body) > settings.preview_tunnel_max_media_bytes:
        raise PreviewTunnelError("MEDIA_TOO_LARGE", "preview media exceeds tunnel limit")
    metadata = {
        "version": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "frameType": "media-meta",
        "contentType": content_type,
        "contentLength": len(body),
    }
    async with send_lock:
        await websocket.send(json.dumps(metadata, separators=(",", ":")))
        await websocket.send(request_id.encode("ascii") + body)


async def _send_json(
    websocket: ClientConnection, send_lock: asyncio.Lock, payload: dict[str, Any]
) -> None:
    async with send_lock:
        await websocket.send(json.dumps(payload, separators=(",", ":")))


def _success(request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "frameType": "response",
        "payload": payload,
    }


def _create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    camera_id = payload.get("cameraId")
    source_url = payload.get("sourceUrl")
    stream_type = payload.get("streamType")
    if not isinstance(camera_id, int) or camera_id <= 0:
        raise PreviewTunnelError("INVALID_CAMERA", "camera id is invalid")
    if not isinstance(source_url, str) or not source_url.startswith(("rtsp://", "rtsps://")):
        raise PreviewTunnelError("INVALID_SOURCE", "preview source must be RTSP")
    if stream_type not in {"MAIN", "SUB"}:
        raise PreviewTunnelError("INVALID_STREAM_TYPE", "stream type is invalid")
    return {"cameraId": camera_id, "sourceUrl": source_url, "streamType": stream_type}


def _webrtc_offer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    camera_id = payload.get("cameraId")
    source_url = payload.get("sourceUrl")
    offer_sdp = payload.get("offerSdp")
    offer_type = payload.get("offerType")
    if not isinstance(camera_id, int) or camera_id <= 0:
        raise PreviewTunnelError("INVALID_CAMERA", "camera id is invalid")
    if not isinstance(source_url, str) or not source_url.startswith(("rtsp://", "rtsps://")):
        raise PreviewTunnelError("INVALID_SOURCE", "preview source must be RTSP")
    if not isinstance(offer_sdp, str) or not offer_sdp or len(offer_sdp) > 1_000_000:
        raise PreviewTunnelError("INVALID_SDP", "WebRTC offer SDP is invalid")
    if offer_type != "offer":
        raise PreviewTunnelError("INVALID_SDP_TYPE", "WebRTC description type must be offer")
    return {
        "cameraId": camera_id,
        "sourceUrl": source_url,
        "offerSdp": offer_sdp,
        "offerType": "offer",
    }


def _session_id(payload: dict[str, Any]) -> str:
    value = payload.get("sessionId")
    if not isinstance(value, str):
        raise PreviewTunnelError("INVALID_SESSION", "preview session id is invalid")
    try:
        UUID(value)
        return value
    except ValueError as error:
        raise PreviewTunnelError("INVALID_SESSION", "preview session id is invalid") from error


def _request_id(value: Any) -> str:
    if not isinstance(value, str):
        raise PreviewTunnelError("INVALID_REQUEST_ID", "request id is invalid")
    try:
        return str(UUID(value))
    except ValueError as error:
        raise PreviewTunnelError("INVALID_REQUEST_ID", "request id is invalid") from error


def _safe_error(error: Exception) -> tuple[str, str, str]:
    if isinstance(error, PreviewTunnelError):
        return str(uuid4()), error.code, str(error)
    if isinstance(error, httpx.HTTPStatusError):
        diagnostic_id = None
        try:
            detail = error.response.json().get("detail")
            if isinstance(detail, dict):
                diagnostic_id = detail.get("diagnosticId")
        except (ValueError, AttributeError):
            pass
        return diagnostic_id or str(uuid4()), "RUNTIME_REJECTED", "Runtime rejected preview request"
    if isinstance(error, httpx.HTTPError):
        return str(uuid4()), "RUNTIME_UNREACHABLE", "Runtime is unreachable"
    return str(uuid4()), "PREVIEW_TUNNEL_ERROR", "preview tunnel request failed"


def _tunnel_uri(settings: AgentSettings) -> str:
    parsed = urlparse(settings.control_plane_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Control plane URL must use http or https")
    if parsed.scheme == "http" and not settings.preview_tunnel_allow_insecure:
        try:
            private_address = ipaddress.ip_address(parsed.hostname).is_private
        except ValueError:
            private_address = parsed.hostname in {"localhost"}
        if not private_address:
            raise ValueError(
                "Insecure preview tunnel is allowed only for private network addresses"
            )
    return urlunparse(
        (
            "wss" if parsed.scheme == "https" else "ws",
            parsed.netloc,
            "/node-api/ai-video/preview/tunnel",
            "",
            "",
            "",
        )
    )


class PreviewTunnelError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
