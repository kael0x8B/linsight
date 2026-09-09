import base64
import hashlib
import json
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_runtime.app.gateway.service import GatewayChange, GatewayConflict
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.stream.webrtc import WebRtcUnavailableError


class GatewayRpc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(max_length=40)
    payload: dict = Field(default_factory=dict)


def build_gateway_router(service, authenticate):
    router = APIRouter(prefix="/gateway", dependencies=[Depends(authenticate)])

    @router.post("/rpc")
    async def rpc(
        request: GatewayRpc, gateway_origin: str = Header(default="LOCAL", alias="X-Gateway-Origin")
    ):
        try:
            payload = request.payload
            if request.action == "snapshot":
                result = service.snapshot()
            elif request.action in {
                "preview.open",
                "preview.status",
                "preview.close",
                "preview.frame",
                "preview.frames",
            }:
                result = await service.preview.invoke(request.action, payload)
            elif request.action == "task.save":
                result = await service.change(
                    GatewayChange.model_validate(payload),
                    origin="PLATFORM" if gateway_origin == "PLATFORM" else "LOCAL",
                )
            elif request.action == "model.uninstall":
                model_id = int(payload["modelVersionId"])
                sha256 = str(payload["sha256"])
                request_id = str(UUID(payload["requestId"]))
                if model_id <= 0 or len(sha256) != 64:
                    raise ValueError("invalid model identity")
                try:
                    result = await service.uninstall_model(model_id, sha256, request_id)
                except ValueError as error:
                    return {"ok": False, "code": 409, "message": str(error)}
            elif request.action == "access.password":
                password = payload.get("password", "")
                if not isinstance(password, str) or not 12 <= len(password) <= 256:
                    return {"ok": False, "code": 422, "message": "密码长度须为 12–256 位"}
                root = service.settings.runtime_data_root / "gateway"
                temporary = root / f".password-{uuid4()}"
                try:
                    with temporary.open("x") as output:
                        os.chmod(temporary, 0o600)
                        output.write(password)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temporary, root / "local-password")
                finally:
                    temporary.unlink(missing_ok=True)
                result = {"updated": True}
            elif request.action == "overlay":
                frame = service.tasks.latest_overlay(int(payload["taskId"]))
                result = None if frame is None else frame.model_dump(mode="json", by_alias=True)
            elif request.action == "events":
                page, size = int(payload.get("page", 1)), int(payload.get("size", 20))
                if page < 1 or not 1 <= size <= 100:
                    raise ValueError("invalid page")
                result = service.tasks.event_store.history(page, size)
            elif request.action == "event.video":
                path = service.tasks.event_store.history_media(payload["sourceEventId"], "video")
                offset = int(payload.get("offset", 0))
                if offset < 0 or offset > path.stat().st_size:
                    raise ValueError("invalid offset")
                with path.open("rb") as stream:
                    stream.seek(offset)
                    chunk = stream.read(384 * 1024)
                result = {
                    "base64": base64.b64encode(chunk).decode(),
                    "size": path.stat().st_size,
                    "offset": offset,
                    "length": len(chunk),
                }
            elif request.action == "event.snapshot":
                path = service.tasks.event_store.history_media(payload["sourceEventId"], "snapshot")
                if path.stat().st_size > 512 * 1024:
                    from io import BytesIO

                    from PIL import Image

                    with Image.open(path) as picture:
                        picture.thumbnail((1280, 720))
                        output = BytesIO()
                        picture.convert("RGB").save(output, "JPEG", quality=80)
                        data = output.getvalue()
                else:
                    data = path.read_bytes()
                result = {"imageBase64": base64.b64encode(data).decode()}
            else:
                return {"ok": False, "code": 400, "message": "不支持的网关操作"}
            return {"ok": True, "data": result}
        except WebRtcUnavailableError as error:
            return {
                "ok": False,
                "code": 503,
                "message": "视频连接暂不可用，请重试",
                "diagnosticId": error.diagnostic_id,
            }
        except GatewayConflict:
            return {
                "ok": False,
                "code": 409,
                "message": "配置已被修改，请刷新后重新提交；当前草稿仍保留",
            }
        except ValidationError as error:
            fields = [".".join(map(str, e["loc"])) for e in error.errors()]
            return {"ok": False, "code": 422, "message": "配置校验失败：" + ", ".join(fields)}
        except (KeyError, FileNotFoundError):
            return {"ok": False, "code": 404, "message": "任务、模型或证据不存在，请刷新检查"}
        except (ValueError, OSError):
            return {
                "ok": False,
                "code": 422,
                "message": "配置无法应用，请检查模型是否已部署、摄像头及规则是否有效",
            }

    @router.get("/events/{event_id}/{kind}")
    async def media(event_id: str, kind: str):
        try:
            path = service.tasks.event_store.history_media(event_id, kind)
        except (KeyError, ValueError, OSError) as error:
            raise HTTPException(404, "Evidence not found") from error
        return FileResponse(
            path,
            media_type="video/mp4" if kind == "video" else "image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/models/upload")
    async def upload(request: Request):
        root = service.settings.runtime_data_root / "models" / "local"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = root / f"{uuid4()}.artifact"
        try:
            encoded = request.headers.get("X-Model-Manifest", "")
            if len(encoded) > 64 * 1024:
                raise ValueError("manifest exceeds limit")
            raw = json.loads(base64.b64decode(encoded, validate=True))
            # Uploads cannot grant themselves permission to execute pickle code.
            raw["trustedArtifact"] = False
            raw["artifactPath"] = str(target.resolve())
            expected_sha256 = raw.get("sha256")
            raw["sha256"] = expected_sha256 or "0" * 64
            config = DeployModelRequest.model_validate(raw)
            if config.artifact_format not in {"ONNX", "RKNN"}:
                raise ValueError("local uploads require ONNX or RKNN")
            if any(
                p["modelVersionId"] == config.model_version_id for p in service.models.summaries()
            ):
                raise GatewayConflict("model version is immutable; choose a new version id")
            digest, size = hashlib.sha256(), 0
            with target.open("xb") as output:
                os.chmod(target, 0o600)
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        raise ValueError("model exceeds upload limit")
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            if expected_sha256 and digest.hexdigest() != expected_sha256:
                raise ValueError("model checksum mismatch")
            config.sha256 = digest.hexdigest()
            result = await service.deploy_model(config, require_new=True)
            return {"ok": True, "data": result.model_dump(by_alias=True)}
        except Exception as error:
            target.unlink(missing_ok=True)
            if isinstance(error, GatewayConflict):
                return {"ok": False, "code": 409, "message": "该模型版本已存在，请使用新的版本编号"}
            return {
                "ok": False,
                "code": 422,
                "message": "模型导入失败，请检查格式、SHA256、执行配置与硬件是否匹配",
            }

    return router
