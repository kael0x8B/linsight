"""Offline developer CLI, using the production package validator and isolated runner."""

import argparse
import asyncio
import hashlib
import io
import json
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

from ai_runtime.app.capability.diagnostics import AlgorithmExecutionError
from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import (
    MAX_EXPANDED_BYTES,
    AlgorithmPackageStore,
    inspect_package,
    validate_manifest,
)
from ai_runtime.app.model.contracts import DetectionObject, ModelTestResult
from ai_runtime.app.task.contracts import TaskInferenceParameters

PROCESSOR = """class Algorithm:
    def process(self, frame, sdk):
        # SDK model responses are fixture data locally; the gateway uses bound models.
        detected = sdk.infer("person")["objects"]
        return {"objects": [
            {**obj, "attributes": {"eventCandidate": True, "displayLabel": "人员候选"}}
            for obj in detected
            if obj["class"] == "person" and obj["confidence"] >= frame["parameters"]["confidence"]
        ]}
"""


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def init_project(directory: Path, code: str):
    manifest = validate_manifest(
        {
            "schemaVersion": "1.0",
            "sdkVersion": "1.0",
            "code": code,
            "name": "SDK 人员候选示例",
            "version": "0.1.0",
            "entrypoint": "processor.py",
            "eventType": "PERSON_DETECTED",
            "category": "GENERAL",
            "timeoutMillis": 3000,
            "models": [
                {
                    "slot": "person",
                    "name": "人员检测",
                    "taskType": "OBJECT_DETECTION",
                    "formats": ["ONNX", "RKNN"],
                    "labels": ["person"],
                }
            ],
            "parameterSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["confidence"],
                "properties": {"confidence": {"type": "number", "minimum": 0, "maximum": 1}},
            },
            "defaultParameters": {"confidence": 0.5},
        }
    )
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "fixtures").mkdir()
    write_json(directory / "algorithm.json", manifest)
    (directory / "processor.py").write_text(PROCESSOR)
    obj = {
        "class": "person",
        "confidence": 0.9,
        "trackId": "fixture-1",
        "bbox": {"x": 0.2, "y": 0.2, "width": 0.2, "height": 0.5},
        "attributes": {},
    }
    fixture_objects = [
        obj,
        {**obj, "class": "car", "trackId": "fixture-2"},
        {**obj, "confidence": 0.1, "trackId": "fixture-3"},
    ]
    write_json(
        directory / "fixtures/frame.json",
        {
            "schemaVersion": "1.0",
            "sourceWidth": 640,
            "sourceHeight": 360,
            "timestampMillis": 1000,
            "objects": fixture_objects,
            "modelResults": {"person": fixture_objects},
        },
    )
    write_json(
        directory / "fixtures/expected.json",
        {
            "objects": [
                {**obj, "attributes": {"eventCandidate": True, "displayLabel": "人员候选"}}
            ],
            "observationValid": True,
        },
    )
    (directory / "README.md").write_text(
        "# SDK 示例\n\nfixtures 是合成检测输入，不代表真实模型准确率。\n"
        "修改 processor.py 后执行 run --expect 做回归；pack 生成平台可上传的 ZIP。\n"
        "模型权重单独管理；上线前须绑定模型并做真实视频评测。\n"
    )


def build_package(directory: Path) -> bytes:
    directory = directory.resolve(strict=True)
    output = io.BytesIO()
    total, count = 0, 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(directory)
            if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError("算法包不允许符号链接")
            if path.is_dir() or relative.parts[0] in {"fixtures", "tests"}:
                continue
            if path.suffix not in {".py", ".json", ".txt", ".md"}:
                raise ValueError("包目录含不支持的文件类型，模型和产物应存放在包外")
            total += path.stat().st_size
            count += 1
            if total > MAX_EXPANDED_BYTES or count > 128:
                raise ValueError("算法包内容超过大小或文件数量限制")
            info = zipfile.ZipInfo(relative.as_posix(), (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes())
    content = output.getvalue()
    inspect_package(content)
    return content


class FixturePool:
    def __init__(self, fixture, bindings):
        self.results = {
            version: fixture.get("modelResults", {}).get(slot) for slot, version in bindings.items()
        }

    async def test(self, request, *, image):
        objects = self.results[request.model_version_id]
        if objects is None:
            raise ValueError("fixture 缺少模型角色返回值")
        return ModelTestResult(
            sourceWidth=image.width,
            sourceHeight=image.height,
            objects=objects,
            backend="FIXTURE",
            device="FIXTURE",
            preprocessMillis=0,
            inferenceMillis=0,
            postprocessMillis=0,
        )

    async def extract_face(self, *_args):
        raise ValueError("快速入门 fixture 不支持 embedding，请使用真实节点验证")


async def run_fixture(content: bytes, fixture: dict, parameters=None) -> dict:
    if fixture.get("schemaVersion") != "1.0":
        raise ValueError("fixture schemaVersion 必须为 1.0")
    width, height = fixture["sourceWidth"], fixture["sourceHeight"]
    if not all(isinstance(value, int) and 1 <= value <= 4096 for value in (width, height)):
        raise ValueError("fixture 图片尺寸必须为 1–4096")
    objects = [DetectionObject.model_validate(obj) for obj in fixture.get("objects", [])]
    if len(objects) > 512:
        raise ValueError("fixture 对象超过上限")
    with tempfile.TemporaryDirectory(prefix="linsight-sdk-") as temporary:
        root = Path(temporary)
        descriptor = AlgorithmPackageStore(root).install(content)
        manifest = descriptor["manifest"]
        bindings = {role["slot"]: i + 1 for i, role in enumerate(manifest["models"])}
        runner = PackageRunner(
            root,
            descriptor,
            manifest.get("defaultParameters", {}) if parameters is None else parameters,
            bindings,
            FixturePool(fixture, bindings),
        )
        try:
            await runner.start()
            with Image.new("RGB", (width, height)) as image:
                result = await runner.run(
                    objects,
                    image,
                    fixture["timestampMillis"],
                    TaskInferenceParameters(schemaVersion="1.0"),
                )
            return {
                "objects": [obj.model_dump(mode="json", by_alias=True) for obj in result],
                "observationValid": runner.observation_valid,
            }
        finally:
            await runner.close()


def read_json(path):
    if Path(path).stat().st_size > 4 * 1024 * 1024:
        raise ValueError("JSON 文件超过 4 MB")
    return json.loads(Path(path).read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description="LInsight 算法 SDK（离线 fixture 调试）")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="生成示例算法及确定性 fixture")
    init.add_argument("directory", type=Path)
    init.add_argument("--code", default="hello-person")
    for name in ("check", "pack", "run"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name in {"pack", "run"}:
            command.add_argument("--output", type=Path, required=name == "pack")
        if name == "run":
            command.add_argument("--fixture", type=Path, required=True)
            command.add_argument("--parameters", type=Path)
            command.add_argument("--expect", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init_project(args.directory, args.code)
            result = {"status": "CREATED", "directory": str(args.directory)}
        else:
            content = build_package(args.directory)
            digest = hashlib.sha256(content).hexdigest()
            result = {"status": "VALID", "packageSha256": digest, "sizeBytes": len(content)}
            if args.command == "pack":
                with args.output.open("xb") as target:
                    target.write(content)
            if args.command == "run":
                output = asyncio.run(
                    run_fixture(
                        content,
                        read_json(args.fixture),
                        read_json(args.parameters) if args.parameters else None,
                    )
                )
                passed = args.expect is None or output == read_json(args.expect)
                result = {
                    **result,
                    "status": "PASS" if passed else "FAIL",
                    "source": "SDK_FIXTURE",
                    "result": output,
                }
                if args.output:
                    write_json(args.output, result)
                if not passed:
                    print(json.dumps(result, ensure_ascii=False))
                    return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except AlgorithmExecutionError as error:
        result = {"status": "ERROR", "source": "SDK_FIXTURE", "error": error.diagnostic}
        if getattr(args, "output", None) and args.command == "run":
            write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Input/IO errors are local to the developer; do not print arbitrary file contents.
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "code": "SDK_INPUT_INVALID",
                    "exceptionType": type(error).__name__,
                    "message": "检查目录、manifest、fixture、参数或输出路径",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
