"""LAN management entrance. Runtime remains loopback-only and owns every mutation."""

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.gateway.platform_connection import (
    normalize_platform_url,
    read_platform_connection,
    write_platform_connection,
)
from ai_runtime.app.gateway.session import SESSION_TTL, GatewaySessions


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PlatformConnectionRequest(BaseModel):
    platform_url: str = Field(alias="platformUrl", min_length=1, max_length=512)


def initialize_password(root: Path) -> Path:
    """Generate once; redeployments preserve the device's independent login credential."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "local-password"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path
    with os.fdopen(descriptor, "w") as output:
        output.write(secrets.token_urlsafe(24))
        output.flush()
        os.fsync(output.fileno())
    return path


def console_static_root() -> Path:
    return Path(__file__).resolve().parents[3] / "gateway-console" / "current"


def create_app(
    settings: RuntimeSettings | None = None,
    transport=None,
    static_root: Path | None = None,
    runtime_owned: bool = False,
    event_stream=None,
):
    settings = settings or RuntimeSettings()
    root = settings.runtime_data_root / "gateway"
    password_path = initialize_password(root)
    static = static_root or console_static_root()
    sessions = GatewaySessions(root)
    attempts: OrderedDict[str, tuple[int, float]] = OrderedDict()
    client = httpx.AsyncClient(
        base_url=settings.gateway_runtime_url,
        transport=transport,
        timeout=180,
        headers={"X-Runtime-Key": settings.api_key},
        trust_env=False,
    )

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await client.aclose()

    app = FastAPI(
        title="LInsight 网关管理",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def session_cookie(response, request, token):
        response.set_cookie(
            "linsight_gateway",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=SESSION_TTL,
        )

    @app.middleware("http")
    async def protect(request: Request, call_next):
        renew = False
        token = ""
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Origin rejected"}, status_code=403)
            if not (
                request.headers.get("content-type", "").startswith("application/json")
                or request.url.path == "/gateway-api/models/upload"
            ):
                return JSONResponse({"detail": "JSON required"}, status_code=415)
        if (
            request.url.path.startswith("/gateway-api/")
            and request.url.path != "/gateway-api/login"
        ):
            token = request.cookies.get("linsight_gateway", "")
            current_digest = hashlib.sha256(password_path.read_bytes().strip()).digest()
            valid, renew = sessions.validate(token, current_digest)
            if not valid:
                return JSONResponse({"detail": "请先登录网关"}, status_code=401)
        response = await call_next(request)
        if renew and request.url.path != "/gateway-api/logout":
            session_cookie(response, request, token)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @app.get("/gateway-health")
    async def gateway_health():
        return {"status": "UP", "owner": "runtime" if runtime_owned else "standalone"}

    @app.get("/event-images/{event_id}")
    async def event_image(event_id: str, expires: int, signature: str):
        # URL 的签名由 TCP 订阅密钥生成；无需管理端登录 Cookie。
        if event_stream is None:
            raise HTTPException(404, "Image service unavailable")
        try:
            path = event_stream.authorized_image_path(event_id, expires, signature)
        except (KeyError, OSError, ValueError) as error:
            raise HTTPException(404, "Image unavailable or link expired") from error
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/gateway-api/login")
    async def login(value: LoginRequest, request: Request):
        address = request.client.host if request.client else "unknown"
        count, until = attempts.get(address, (0, time.monotonic() + 60))
        if time.monotonic() > until:
            count, until = 0, time.monotonic() + 60
        if count >= 10:
            raise HTTPException(429, "登录尝试过多，请稍后重试")
        attempts[address] = (count + 1, until)
        if len(attempts) > 1024:
            attempts.popitem(last=False)
        if not hmac.compare_digest(
            hashlib.sha256(value.password.encode()).digest(),
            hashlib.sha256(password_path.read_bytes().strip()).digest(),
        ):
            raise HTTPException(401, "网关管理密码不正确")
        attempts.pop(address, None)
        try:
            token = sessions.create(
                hashlib.sha256(password_path.read_bytes().strip()).digest(),
                request.cookies.get("linsight_gateway", ""),
            )
        except ValueError as error:
            raise HTTPException(429, str(error)) from error
        response = JSONResponse({"ok": True})
        session_cookie(response, request, token)
        return response

    @app.get("/gateway-api/session")
    async def session_status():
        return {"ok": True}

    @app.post("/gateway-api/logout")
    async def logout(request: Request):
        sessions.revoke(request.cookies.get("linsight_gateway", ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie("linsight_gateway")
        return response

    async def probe_platform(value: str) -> dict:
        try:
            platform_url = normalize_platform_url(value)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        started = time.monotonic()
        status = None
        try:
            async with httpx.AsyncClient(
                timeout=3, trust_env=False, follow_redirects=False
            ) as probe:
                response = await probe.get(f"{platform_url}/node-api/ai-video/node/ping")
                status = response.status_code
                payload = response.json()
            reachable = response.is_success and payload.get("data") == "linsight-control-plane"
            message = (
                "LInsight 平台连接正常" if reachable else "地址可访问，但不是可用的 LInsight 平台"
            )
        except (httpx.HTTPError, OSError, ValueError):
            reachable = False
            message = "无法连接平台；地址仍可保存，Agent 将持续重试"
        return {
            "platformUrl": platform_url,
            "reachable": reachable,
            "httpStatus": status,
            "latencyMs": round((time.monotonic() - started) * 1000),
            "checkedAt": datetime.now(UTC).isoformat(),
            "message": message,
        }

    @app.get("/gateway-api/platform-connection")
    async def platform_connection():
        try:
            return read_platform_connection(settings.runtime_data_root, settings.platform_url)
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
            raise HTTPException(500, "平台连接配置已损坏，请检查设备数据文件") from error

    @app.post("/gateway-api/platform-connection/test")
    async def test_platform_connection(value: PlatformConnectionRequest):
        return await probe_platform(value.platform_url)

    @app.put("/gateway-api/platform-connection")
    async def save_platform_connection(value: PlatformConnectionRequest):
        try:
            saved = write_platform_connection(settings.runtime_data_root, value.platform_url)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {**saved, "probe": await probe_platform(saved["platformUrl"])}

    @app.post("/gateway-api/rpc")
    async def rpc(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 12 * 1024 * 1024:
                raise HTTPException(413, "请求过大")
        try:
            message = json.loads(body)
            if (
                isinstance(message, dict)
                and message.get("action") == "task.save"
                and isinstance(message.get("payload"), dict)
            ):
                # Older shared editors also sent platform routing hints locally.
                # Ownership comes from the stored task, never from these hints.
                payload = message["payload"]
                if payload.pop("streamTypeChanged", False):
                    return JSONResponse(
                        {
                            "ok": False,
                            "code": 422,
                            "message": "请在平台切换主/子码流，或在高级设置中填写目标 RTSP 地址",
                        },
                        status_code=422,
                    )
                payload.pop("platformManaged", None)
            response = await client.post("/v1/gateway/rpc", json=message)
            return JSONResponse(response.json(), status_code=response.status_code)
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(503, "网关推理服务暂不可用，请稍后重试") from error

    @app.post("/gateway-api/models/upload")
    async def upload(request: Request):
        async def bounded():
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 512 * 1024 * 1024:
                    raise HTTPException(413, "模型文件超过 512 MB")
                yield chunk

        response = await client.post(
            "/v1/gateway/models/upload",
            content=bounded(),
            headers={"X-Model-Manifest": request.headers.get("X-Model-Manifest", "")},
        )
        return JSONResponse(response.json(), status_code=response.status_code)

    @app.get("/gateway-api/events/{event_id}/{kind}")
    async def media(event_id: str, kind: str, request: Request):
        from uuid import UUID

        try:
            UUID(event_id)
        except ValueError as error:
            raise HTTPException(404) from error
        if kind not in {"snapshot", "video"}:
            raise HTTPException(404)
        headers = {"Range": request.headers["range"]} if "range" in request.headers else {}
        upstream = await client.send(
            client.build_request("GET", f"/v1/gateway/events/{event_id}/{kind}", headers=headers),
            stream=True,
        )

        async def body():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(
            body(),
            status_code=upstream.status_code,
            headers={
                k: v
                for k, v in upstream.headers.items()
                if k in {"content-type", "content-length", "content-range", "accept-ranges"}
            },
        )

    @app.get("/{path:path}")
    async def page(path: str):
        candidate = (static / (path or "gateway.html")).resolve()
        if not candidate.is_relative_to(static.resolve()) or not candidate.is_file():
            raise HTTPException(404, "网关页面尚未安装，请构建并部署网关控制台")
        return FileResponse(candidate)

    return app
