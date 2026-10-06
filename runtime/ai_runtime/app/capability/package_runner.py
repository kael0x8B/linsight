"""Fault-isolated algorithm execution; host keeps ownership of frames and model instances."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from ai_runtime.app.capability.packages import AlgorithmPackageStore, validate_parameters
from ai_runtime.app.capability.plate_input import PLATE_EVIDENCE_CAPABILITY
from ai_runtime.app.model.contracts import DetectionObject, ModelTestRequest

RUNTIME_CAPABILITIES = ["observation-validity-v1", PLATE_EVIDENCE_CAPABILITY]


class PackageRunner:
    def __init__(self, root, descriptor, parameters, bindings, pool):
        self.path, self.manifest = AlgorithmPackageStore(root).resolve(descriptor["sha256"])
        if self.manifest != descriptor["manifest"]:
            raise ValueError("算法包描述与已安装内容不一致")
        validate_parameters(self.manifest.get("parameterSchema", {}), parameters)
        if {m["slot"] for m in self.manifest["models"]} - set(bindings):
            raise ValueError("算法缺少模型角色绑定")
        if set(self.manifest.get("runtimeRequirements", [])) - set(RUNTIME_CAPABILITIES):
            raise ValueError("算法需要更新的网关运行能力")
        self.observation_valid = True
        self.parameters, self.bindings, self.pool = parameters, bindings, pool
        self.resource_root = (root / "algorithm-resources").resolve()
        self.reference_cache = {}
        self.process = None

    async def start(self):
        # Do not pass platform tokens, RTSP credentials or operator environment to packages.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT"}
        }
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(Path(__file__).with_name("package_worker.py")),
            str(self.path),
            self.manifest["entrypoint"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
            cwd=self.path,
            limit=4 * 1024 * 1024 + 1,
        )
        try:
            async with asyncio.timeout(10):
                if json.loads(await self.process.stdout.readline()) != {"ready": True}:
                    raise ValueError("算法工作进程未就绪")
        except BaseException:
            await self.close()
            raise

    async def close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()

    async def run(self, objects, image, timestamp, inference_parameters, resources=None):
        if self.process is None or self.process.returncode is not None:
            raise ValueError("算法工作进程已退出")
        resources = {key: list(entries) for key, entries in (resources or {}).items()}
        for resource in self.manifest.get("resources", []):
            selection = self.parameters.get(resource.get("selectionParameter"), [])
            if selection:
                resources[resource["key"]] = [
                    r for r in resources.get(resource["key"], []) if r["id"] in selection
                ]
        try:
            async with asyncio.timeout(self.manifest.get("timeoutMillis", 3000) / 1000):
                await self._send(
                    {
                        "runtimeCapabilities": RUNTIME_CAPABILITIES,
                        "objects": [o.model_dump(mode="json", by_alias=True) for o in objects],
                        "timestampMillis": timestamp,
                        "sourceWidth": image.width,
                        "sourceHeight": image.height,
                        "parameters": self.parameters,
                        "resources": {
                            key: [
                                {
                                    k: v
                                    for k, v in entry.items()
                                    if k in {"id", "name", "validUntil"}
                                }
                                for entry in entries
                            ]
                            for key, entries in (resources or {}).items()
                        },
                    }
                )
                for _ in range(33):
                    line = await self.process.stdout.readline()
                    if not line or len(line) > 4 * 1024 * 1024:
                        raise ValueError("算法工作进程返回无效消息")
                    response = json.loads(line)
                    if "result" in response:
                        output = response["result"]
                        if (
                            not isinstance(output, dict)
                            or not isinstance(output.get("objects"), list)
                            or len(output["objects"]) > 512
                        ):
                            raise ValueError("算法输出不符合标准对象契约")
                        validity = output.get("observationValid", True)
                        if not isinstance(validity, bool):
                            raise ValueError("算法 observationValid 必须为布尔值")
                        self.observation_valid = validity
                        result = [DetectionObject.model_validate(obj) for obj in output["objects"]]
                        if self.manifest.get("frameInput"):
                            tracks = {obj.track_id for obj in objects if obj.track_id is not None}
                            if any(obj.track_id not in tracks for obj in result):
                                raise ValueError("车牌算法输出必须保留输入的物理轨迹")
                        return result
                    if "error" in response:
                        raise ValueError("算法处理失败：" + str(response["error"])[:80])
                    operation, arguments = response.get("call"), response.get("arguments", {})
                    if operation == "reference_embedding":
                        import hashlib
                        import time

                        from PIL import Image

                        entries = (resources or {}).get(arguments.get("resource"), [])
                        reference = next(
                            (entry for entry in entries if entry["id"] == arguments.get("entryId")),
                            None,
                        )
                        if (
                            not reference
                            or reference.get("validUntil", 0) < time.time_ns() // 1_000_000
                        ):
                            raise ValueError("人员参考不可用或已过期")
                        path = await asyncio.to_thread(Path(reference["path"]).resolve)
                        if (
                            not path.is_relative_to(self.resource_root)
                            or reference["modelSlot"] not in self.bindings
                        ):
                            raise ValueError("人员参考不在允许的资源目录")
                        key = (reference["sha256"], self.bindings[reference["modelSlot"]])
                        if key not in self.reference_cache:
                            if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
                                raise ValueError("人员参考校验失败")
                            with Image.open(path) as picture:
                                feature, _, _, _ = await self.pool.extract_face(key[1], picture)
                            self.reference_cache[key] = feature.tolist()
                        await self._send(
                            {"ok": True, "data": {"embedding": self.reference_cache[key]}}
                        )
                        continue
                    if (
                        operation not in {"infer", "embedding"}
                        or arguments.get("slot") not in self.bindings
                    ):
                        raise ValueError("算法请求未授权的模型能力")
                    region = arguments.get("region")
                    selected = image
                    if region is not None:
                        from ai_runtime.app.model.contracts import BoundingBox

                        box = BoundingBox.model_validate(region)
                        if (
                            box.width <= 0
                            or box.height <= 0
                            or box.x + box.width > 1
                            or box.y + box.height > 1
                        ):
                            raise ValueError("算法裁剪区域无效")
                        selected = image.crop(
                            (
                                round(box.x * image.width),
                                round(box.y * image.height),
                                round((box.x + box.width) * image.width),
                                round((box.y + box.height) * image.height),
                            )
                        )
                    version = self.bindings[arguments["slot"]]
                    if operation == "embedding":
                        from ai_runtime.app.model.face_pair import FaceQualityError

                        try:
                            feature, face, backend, device = await self.pool.extract_face(
                                version, selected
                            )
                            data = {
                                "embedding": feature.tolist(),
                                "box": face.box.tolist(),
                                "backend": backend,
                                "device": device,
                            }
                        except FaceQualityError as error:
                            data = {"embedding": None, "reason": str(error)}
                    else:
                        with tempfile.NamedTemporaryFile(suffix=".jpg") as frame_file:
                            selected.save(frame_file.name, "JPEG")
                            request = ModelTestRequest(
                                modelVersionId=version,
                                imagePath=frame_file.name,
                                parameters={
                                    **inference_parameters.model_dump(by_alias=True),
                                    "outputCoordinates": "NORMALIZED_XYWH",
                                },
                            )
                            result = await self.pool.test(request, image=selected)
                        data = result.model_dump(mode="json", by_alias=True)
                    await self._send({"ok": True, "data": data})
                raise ValueError("算法每帧模型调用超过上限")
        except BaseException:
            await self.close()
            raise

    async def _send(self, value):
        data = json.dumps(value, allow_nan=False).encode() + b"\n"
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("算法消息超过大小限制")
        self.process.stdin.write(data)
        await self.process.stdin.drain()
