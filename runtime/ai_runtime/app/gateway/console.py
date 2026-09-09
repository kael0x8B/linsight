"""LAN management entrance. Runtime remains loopback-only and owns every mutation."""

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ai_runtime.app.core.config import RuntimeSettings


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


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
    return Path(__file__).resolve().parents[3] / "edge_agent" / "app" / "console"


def create_app(
    settings: RuntimeSettings | None = None,
    transport=None,
    static_root: Path | None = None,
    runtime_owned: bool = False,
):
    settings = settings or RuntimeSettings()
    root = settings.runtime_data_root / "gateway"
    password_path = initialize_password(root)
    static = static_root or console_static_root()
    sessions: dict[str, tuple[float, bytes]] = {}
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

    @app.middleware("http")
    async def protect(request: Request, call_next):
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
            expiry, digest = sessions.get(token, (0, b""))
            current_digest = hashlib.sha256(password_path.read_bytes().strip()).digest()
            if expiry < time.time() or not hmac.compare_digest(digest, current_digest):
                return JSONResponse({"detail": "请先登录网关"}, status_code=401)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @app.get("/gateway-health")
    async def gateway_health():
        return {"status": "UP", "owner": "runtime" if runtime_owned else "standalone"}

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
        for token, (expiry, _digest) in list(sessions.items()):
            if expiry < time.time():
                sessions.pop(token, None)
        if len(sessions) >= 64:
            raise HTTPException(429, "登录会话已满")
        token = secrets.token_urlsafe(32)
        sessions[token] = (
            time.time() + 8 * 3600,
            hashlib.sha256(password_path.read_bytes().strip()).digest(),
        )
        response = JSONResponse({"ok": True})
        response.set_cookie(
            "linsight_gateway",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=8 * 3600,
        )
        return response

    @app.post("/gateway-api/logout")
    async def logout(request: Request):
        sessions.pop(request.cookies.get("linsight_gateway", ""), None)
        response = JSONResponse({"ok": True})
        response.delete_cookie("linsight_gateway")
        return response

    @app.post("/gateway-api/rpc")
    async def rpc(request: Request):
        body = await request.body()
        if len(body) > 512 * 1024:
            raise HTTPException(413, "请求过大")
        try:
            response = await client.post("/v1/gateway/rpc", json=json.loads(body))
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
