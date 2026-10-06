"""Immutable, device-local algorithm packages. Installing never imports their code."""

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from ai_runtime.app.capability.plate_input import PLATE_EVIDENCE_CAPABILITY

MAX_PACKAGE_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
SDK_VERSION = "1.0"


def validate_manifest(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != "1.0":
        raise ValueError("算法包描述版本不支持")
    if value.get("sdkVersion") != SDK_VERSION:
        raise ValueError("算法包需要不同的 Runtime SDK，请升级网关或选择兼容版本")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", str(value.get("code", ""))):
        raise ValueError("算法编码无效")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}", str(value.get("version", ""))):
        raise ValueError("算法版本无效")
    if not isinstance(value.get("name"), str) or not 1 <= len(value["name"]) <= 100:
        raise ValueError("算法名称无效")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*\.py", str(value.get("entrypoint", ""))):
        raise ValueError("算法入口必须是包根目录中的 Python 文件")
    if not isinstance(value.get("models"), list) or not 1 <= len(value["models"]) <= 20:
        raise ValueError("算法必须声明 1–20 个模型角色")
    requirements = value.get("runtimeRequirements", [])
    if not isinstance(requirements, list) or any(not isinstance(v, str) for v in requirements):
        raise ValueError("算法运行能力要求必须为字符串数组")
    slots = set()
    for model in value["models"]:
        if not isinstance(model, dict):
            raise ValueError("模型角色必须是对象")
        slot = model.get("slot", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", slot) or slot in slots:
            raise ValueError("模型角色无效或重复")
        slots.add(slot)
        decoders = model.get("decoderTypes", [])
        if not isinstance(decoders, list) or any(not isinstance(d, str) for d in decoders):
            raise ValueError("模型解码器要求必须为字符串数组")
        if not isinstance(model.get("labels", []), list):
            raise ValueError("模型类别要求无效")
    if "frameInput" in value:
        inputs = value["frameInput"]
        roles = {role["slot"]: role for role in value["models"]}
        if (
            not isinstance(inputs, dict)
            or inputs.get("type") != "PLATE_OCR"
            or PLATE_EVIDENCE_CAPABILITY not in requirements
            or not isinstance(inputs.get("detectorSlot"), str)
            or not isinstance(inputs.get("ocrSlot"), str)
            or inputs.get("detectorSlot") == inputs.get("ocrSlot")
            or set(roles) != {inputs.get("detectorSlot"), inputs.get("ocrSlot")}
            or roles.get(inputs.get("detectorSlot"), {}).get("taskType") != "OBJECT_DETECTION"
            or roles.get(inputs.get("ocrSlot"), {}).get("taskType") != "OCR"
        ):
            raise ValueError("车牌输入需要明确的定位/OCR角色及 plate-ocr-evidence-v1 能力")
        supported = {
            "detectorSlot": {"YOLO_PLATE", "YOLO26_PLATE_POSE"},
            "ocrSlot": {"CHINESE_PLATE_CTC", "PLATE_OCR_ROUTED"},
        }
        for key, allowed in supported.items():
            decoders = roles[inputs[key]].get("decoderTypes")
            if not isinstance(decoders, list) or not decoders or any(
                decoder not in allowed for decoder in decoders
            ):
                raise ValueError("车牌输入必须声明兼容的模型解码器")
    schema = value.get("parameterSchema", {"type": "object", "properties": {}})
    if schema.get("type") != "object" or not isinstance(schema.get("properties", {}), dict):
        raise ValueError("参数必须使用对象 JSON Schema")
    if (
        not isinstance(value.get("timeoutMillis", 3000), int)
        or not 100 <= value.get("timeoutMillis", 3000) <= 30000
    ):
        raise ValueError("算法处理超时必须为 100–30000 毫秒")
    for resource in value.get("resources", []):
        if (
            not isinstance(resource, dict)
            or resource.get("type") != "FACE_LIBRARY"
            or resource.get("modelSlot") not in slots
            or resource.get("parameter") not in schema.get("properties", {})
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", resource.get("key", ""))
        ):
            raise ValueError("算法资源声明无效")
    validate_parameters({**schema, "required": []}, value.get("defaultParameters", {}))
    if "defaultRule" in value:
        from ai_runtime.app.rule.contracts import RuleAst

        rule = RuleAst.model_validate(value["defaultRule"])
        if rule.event_type != value.get("eventType", "ALGORITHM_EVENT"):
            raise ValueError("默认告警规则的事件类型必须与算法一致")
    return value


def validate_parameters(schema: dict, values: dict) -> None:
    """The SDK's bounded JSON Schema subset is shared by install and task admission."""
    if not isinstance(values, dict):
        raise ValueError("算法参数必须是对象")
    properties = schema.get("properties", {})
    if any(key not in values for key in schema.get("required", [])):
        raise ValueError("算法缺少必填配置")
    if schema.get("additionalProperties") is False and set(values) - set(properties):
        raise ValueError("算法包含未声明配置")
    for key, value in values.items():
        spec = properties.get(key)
        if spec is None:
            continue
        kind = spec.get("type")
        valid = {
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "string": isinstance(value, str),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }
        if kind not in valid or not valid[kind]:
            raise ValueError(f"算法配置 {key} 类型无效")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"算法配置 {key} 选项无效")
        if kind in {"number", "integer"}:
            import math

            if (
                not math.isfinite(value)
                or value < spec.get("minimum", -1e100)
                or value > spec.get("maximum", 1e100)
            ):
                raise ValueError(f"算法配置 {key} 超出范围")
        if kind in {"string", "array"} and len(value) < spec.get(
            "minLength" if kind == "string" else "minItems", 0
        ):
            raise ValueError(f"算法配置 {key} 条目不足")
        if kind in {"string", "array"} and len(value) > spec.get(
            "maxLength" if kind == "string" else "maxItems", 4096
        ):
            raise ValueError(f"算法配置 {key} 过长")
        if kind == "object":
            validate_parameters(spec, value)
            if spec.get("x-widget") == "roi" and (
                value.get("width", 0) <= 0
                or value.get("height", 0) <= 0
                or value.get("x", 0) + value.get("width", 0) > 1
                or value.get("y", 0) + value.get("height", 0) > 1
            ):
                raise ValueError("识别区域必须在画面范围内且面积大于零")
        if kind == "array" and spec.get("items"):
            for item in value:
                validate_parameters({"properties": {key: spec["items"]}}, {key: item})


def validate_bindings(manifest, bindings, models):
    by_id = {m["modelVersionId"]: m for m in models}
    for role in manifest["models"]:
        model = by_id.get(bindings.get(role["slot"]))
        if not model:
            raise ValueError("算法依赖模型尚未安装")
        contract = model.get("runtimeManifest") or {}
        if (
            (role.get("formats") and model["artifactFormat"] not in role["formats"])
            or (role.get("taskType") and role["taskType"] != contract.get("taskType"))
            or (role.get("decoderTypes") and contract.get("decoder", {}).get("type")
                not in role["decoderTypes"])
            or not set(role.get("labels", [])).issubset(
                contract.get("decoder", {}).get("labels", [])
            )
        ):
            raise ValueError("模型与算法角色的输入输出要求不兼容")


def inspect_package(content: bytes) -> tuple[dict, dict[str, bytes]]:
    if not content or len(content) > MAX_PACKAGE_BYTES:
        raise ValueError("算法包大小必须为 1 字节至 8 MB，模型请单独上传")
    files: dict[str, bytes] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if len(archive.infolist()) > 128:
                raise ValueError("算法包文件过多")
            for info in archive.infolist():
                name = info.filename
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or ":" in name
                    or str(path) != name.rstrip("/")
                    or name in files
                    or stat.S_ISLNK(info.external_attr >> 16)
                ):
                    raise ValueError("算法包包含不安全或重复的路径")
                if info.is_dir():
                    continue
                total += info.file_size
                if total > MAX_EXPANDED_BYTES or path.suffix not in {".py", ".json", ".txt", ".md"}:
                    raise ValueError("算法包内容类型或解压大小不支持")
                data = archive.read(info)
                files[name] = data
        manifest = validate_manifest(json.loads(files["algorithm.json"]))
        if manifest["entrypoint"] not in files:
            raise ValueError("算法执行入口不存在")
        return manifest, files
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("算法包损坏或缺少 algorithm.json") from error


class AlgorithmPackageStore:
    def __init__(self, root: Path):
        self.root = root / "algorithms"
        self.root.mkdir(parents=True, exist_ok=True)

    def install(self, content: bytes, expected_sha256: str | None = None) -> dict:
        digest = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("算法包 SHA256 不匹配")
        manifest, files = inspect_package(content)
        target = self.root / digest
        if not target.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".install-", dir=self.root))
            try:
                for name, data in files.items():
                    file = temporary / name
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(data)
                (temporary / ".package.zip").write_bytes(content)
                try:
                    os.rename(temporary, target)
                except FileExistsError:
                    pass
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
        self.resolve(digest)
        return {"sha256": digest, "manifest": manifest, "status": "READY"}

    def resolve(self, digest: str) -> tuple[Path, dict]:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("算法包标识无效")
        path = self.root / digest
        content = (path / ".package.zip").read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("本地算法包校验失败")
        manifest, files = inspect_package(content)
        for name, expected in files.items():
            file = path / name
            if (
                file.is_symlink()
                or not file.resolve().is_relative_to(path.resolve())
                or file.read_bytes() != expected
            ):
                raise ValueError("本地算法文件已变化，拒绝执行")
        return path, manifest

    def list(self) -> list[dict]:
        result = []
        for path in sorted(self.root.iterdir()):
            if re.fullmatch(r"[0-9a-f]{64}", path.name):
                try:
                    _, manifest = self.resolve(path.name)
                    result.append({"sha256": path.name, "manifest": manifest, "status": "READY"})
                except (ValueError, OSError):
                    result.append({"sha256": path.name, "status": "FAILED"})
        return result
