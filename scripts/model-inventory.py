#!/usr/bin/env python3
"""Build a fail-closed inventory of every declared LInsight model and algorithm."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "runtime/model_assets/builtin-model-assets-v1.json"
MANIFESTS = ROOT / "runtime/model_assets/runtime-manifests-v1.json"
DEFAULT_ASSET_DIR = ROOT / "var/model-assets/v1"
DEFAULT_JSON = ROOT / "artifacts/production-readiness/model-inventory.json"
DEFAULT_MARKDOWN = ROOT / "artifacts/production-readiness/model-inventory.md"

SAFE_COMMERCIAL_LICENSES = {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"}
FORBIDDEN_COMMERCIAL_MARKERS = {"NONCOMMERCIAL", "NON-COMMERCIAL", "RESEARCH-ONLY"}
MODEL_SUFFIXES = {".onnx", ".pt", ".pth", ".rknn", ".jit", ".torchscript", ".zip"}
PLACEHOLDER_MARKERS = {"mock", "dummy", "fake", "placeholder", "empty", "fixture"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def commercial_status(license_spdx: str | None) -> str:
    if not license_spdx:
        return "UNKNOWN"
    normalized = license_spdx.upper()
    if any(marker in normalized for marker in FORBIDDEN_COMMERCIAL_MARKERS):
        return "NO"
    if license_spdx in SAFE_COMMERCIAL_LICENSES:
        return "YES_WITH_LICENSE_OBLIGATIONS"
    return "REQUIRES_LEGAL_REVIEW"


def device_support(asset: dict[str, Any]) -> dict[str, str]:
    compatibility = {str(value).lower() for value in asset.get("runtimeCompatibility", [])}
    cpu = "DECLARED" if any("onnxruntime" in value or "pytorch" in value for value in compatibility) else "UNKNOWN"
    gpu = "UNVERIFIED" if cpu == "DECLARED" else "UNKNOWN"
    npu = "DECLARED_RK3566" if any("rknn" in value for value in compatibility) else "UNKNOWN"
    return {"cpu": cpu, "gpu": gpu, "npu": npu}


def inspect_input(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".onnx":
        return {"width": "UNKNOWN", "height": "UNKNOWN", "shape": "UNKNOWN"}
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        shape = list(session.get_inputs()[0].shape)
    except Exception:
        return {"width": "UNKNOWN", "height": "UNKNOWN", "shape": "UNREADABLE"}
    height = shape[-2] if len(shape) >= 4 and isinstance(shape[-2], int) else "DYNAMIC"
    width = shape[-1] if len(shape) >= 4 and isinstance(shape[-1], int) else "DYNAMIC"
    return {"width": width, "height": height, "shape": shape}


def display_path(path: Path | None) -> str:
    if path is None:
        return "UNKNOWN"
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def scan_algorithms() -> list[dict[str, Any]]:
    pattern = re.compile(
        r"\((\d+),\s*'((?:''|[^'])*)',\s*'([a-z0-9-]+)',\s*'(CORE|EXTENSION|CUSTOM)'"
    )
    algorithms: dict[str, dict[str, Any]] = {}
    migration_dir = ROOT / "backend/sql/mysql/migrations/ai-video"
    retired_ids: set[int] = set()
    retirement_pattern = re.compile(r"inventory-retired-algorithm-ids:\s*([0-9,]+)")
    for migration in sorted(migration_dir.glob("V*.sql")):
        text = migration.read_text(encoding="utf-8")
        for match in retirement_pattern.finditer(text):
            retired_ids.update(int(value) for value in match.group(1).split(","))
    for migration in sorted(migration_dir.glob("V*.sql")):
        text = migration.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            algorithm_id, name, code, category = match.groups()
            if int(algorithm_id) in retired_ids:
                continue
            algorithms[code] = {
                "id": int(algorithm_id),
                "name": name.replace("''", "'"),
                "code": code,
                "category": category,
                "declaredBy": str(migration.relative_to(ROOT)),
                "acceptanceStatus": "WAITING_FOR_REAL_DATA",
            }
    return sorted(algorithms.values(), key=lambda value: (value["category"], value["code"]))


def build_inventory(asset_dir: Path) -> dict[str, Any]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    manifest_document = json.loads(MANIFESTS.read_text(encoding="utf-8"))
    runtime_manifests = manifest_document.get("manifests", {})
    lock_path = asset_dir / "assets-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else {}
    locked_assets = {entry["key"]: entry for entry in lock.get("assets", [])}
    physical = {entry["key"]: entry for entry in catalog.get("assets", [])}
    bundles = {entry["key"]: entry for entry in catalog.get("bundles", [])}
    asset_usage: dict[str, list[str]] = defaultdict(list)
    models: list[dict[str, Any]] = []
    violations: list[dict[str, str]] = []
    actual_hashes: dict[str, list[str]] = defaultdict(list)

    for logical in catalog.get("models", []):
        for declared_version in logical.get("versions", []):
            asset_key = declared_version.get("artifact")
            asset_usage[str(asset_key)].append(logical["code"])
            declared_asset = physical.get(asset_key) or bundles.get(asset_key) or {}
            asset = {**locked_assets.get(str(asset_key), {}), **declared_asset}
            file_name = asset.get("fileName")
            path = asset_dir / file_name if isinstance(file_name, str) else None
            exists = bool(path and path.is_file())
            size = path.stat().st_size if exists and path is not None else 0
            actual_sha = sha256(path) if exists and path is not None and size > 0 else None
            if actual_sha:
                actual_hashes[actual_sha].append(str(asset_key))
            expected_sha = asset.get("expectedSha256") or locked_assets.get(str(asset_key), {}).get("sha256")
            license_spdx = asset.get("licenseSpdx")
            source_url = asset.get("sourceRepository")
            source_revision = asset.get("sourceRevision")
            runtime_manifest = runtime_manifests.get(str(asset_key))
            suspicious_name = bool(
                file_name
                and any(marker in file_name.lower() for marker in PLACEHOLDER_MARKERS)
            )
            issues: list[str] = []
            if not source_url or not source_revision:
                issues.append("UNKNOWN_SOURCE")
            if not exists:
                issues.append("MODEL_FILE_MISSING")
            elif size == 0:
                issues.append("EMPTY_WEIGHT")
            elif path is not None and path.suffix.lower() in MODEL_SUFFIXES and size < 1024:
                issues.append("SUSPICIOUSLY_SMALL_WEIGHT")
            if suspicious_name:
                issues.append("MOCK_OR_TEST_MODEL_NAME")
            if runtime_manifest is None:
                issues.append("RUNTIME_MANIFEST_MISSING")
            if not expected_sha:
                issues.append("EXPECTED_SHA256_MISSING")
            elif actual_sha and actual_sha != expected_sha:
                issues.append("SHA256_MISMATCH")
            commercial = commercial_status(license_spdx)
            # License is inventory metadata, not a technical execution/acceptance gate.
            declared_input = asset.get("inputSize")
            if declared_input is None and runtime_manifest:
                preprocess = runtime_manifest.get("preprocess", {})
                width = preprocess.get("inputWidth")
                height = preprocess.get("inputHeight")
                if isinstance(width, int) and isinstance(height, int):
                    declared_input = [width, height]
            input_size = inspect_input(path) if exists and path is not None else {
                "width": declared_input[0] if isinstance(declared_input, list) and len(declared_input) == 2 else "UNKNOWN",
                "height": declared_input[1] if isinstance(declared_input, list) and len(declared_input) == 2 else "UNKNOWN",
                "shape": "DECLARED_NOT_VERIFIED" if declared_input else "UNKNOWN",
            }
            if (
                declared_input
                and input_size["width"] == "UNKNOWN"
                and input_size["height"] == "UNKNOWN"
            ):
                input_size = {
                    "width": declared_input[0],
                    "height": declared_input[1],
                    "shape": "DECLARED_NOT_VERIFIED",
                }
            if input_size["width"] == "UNKNOWN" or input_size["height"] == "UNKNOWN":
                issues.append("INPUT_SIZE_UNKNOWN")
            status = "EXISTING_OK" if not issues else "EXISTING_NEEDS_IMPROVEMENT"
            model = {
                "algorithmOrModelCode": logical["code"],
                "modelName": logical["code"],
                "modelVersion": declared_version.get("version"),
                "modelFile": file_name or "UNKNOWN",
                "modelPath": display_path(path),
                "source": source_url or "UNKNOWN",
                "sourceRevision": source_revision or "UNKNOWN",
                "downloadUrl": asset.get("url", "UNKNOWN"),
                "license": license_spdx or "UNKNOWN",
                "commercialUse": commercial,
                "sha256": actual_sha or expected_sha or "UNKNOWN",
                "sha256Verified": bool(actual_sha and expected_sha and actual_sha == expected_sha),
                "inputSize": input_size,
                "inferenceFramework": asset.get("runtimeCompatibility", ["UNKNOWN"]),
                "modelSizeBytes": size if exists else None,
                "deviceSupport": device_support(asset),
                "artifactKey": asset_key,
                "runtimeManifest": runtime_manifest or "MISSING",
                "fileState": "PRESENT" if exists else "MISSING",
                "status": status,
                "issues": issues,
            }
            models.append(model)
            violations.extend(
                {"model": logical["code"], "version": str(declared_version.get("version")), "code": issue}
                for issue in issues
            )

    duplicate_artifacts = [
        {"artifactKey": key, "logicalModels": sorted(set(values)), "classification": "DECLARED_SHARED"}
        for key, values in sorted(asset_usage.items())
        if len(set(values)) > 1
    ]
    duplicate_hashes = [
        {"sha256": digest, "artifactKeys": sorted(set(keys)), "classification": "REVIEW_REQUIRED"}
        for digest, keys in sorted(actual_hashes.items())
        if len(set(keys)) > 1
    ]
    algorithms = scan_algorithms()
    summary = {
        "declaredLogicalModels": len(catalog.get("models", [])),
        "declaredModelVersions": len(models),
        "physicalAssets": len(physical),
        "bundles": len(bundles),
        "presentModelFiles": sum(value["fileState"] == "PRESENT" for value in models),
        "algorithms": len(algorithms),
        "coreAlgorithms": sum(value["category"] == "CORE" for value in algorithms),
        "violations": len(violations),
        "violationCounts": dict(sorted(Counter(value["code"] for value in violations).items())),
    }
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "EXISTING_OK" if not violations else "EXISTING_NEEDS_IMPROVEMENT",
        "fieldAcceptance": "WAITING_FOR_REAL_DATA",
        "catalogVersion": catalog.get("catalogVersion"),
        "assetDirectory": str(asset_dir),
        "summary": summary,
        "models": models,
        "algorithms": algorithms,
        "declaredSharedArtifacts": duplicate_artifacts,
        "duplicateBinaryHashes": duplicate_hashes,
        "violations": violations,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# LInsight 统一模型与算法清单",
        "",
        f"- 生成时间：`{report['generatedAt']}`",
        f"- 代码状态：`{report['status']}`",
        f"- 现场状态：`{report['fieldAcceptance']}`",
        f"- 逻辑模型：{summary['declaredLogicalModels']}，模型版本：{summary['declaredModelVersions']}，算法：{summary['algorithms']}",
        f"- 本地模型文件：{summary['presentModelFiles']}，阻断项：{summary['violations']}",
        "",
        "真实权重、许可证和测试数据未齐全时，本报告不会把目录声明当作生产验收通过。",
        "",
        "## 模型版本",
        "",
        "| 模型 | 版本 | 文件 | 来源版本 | License/商用 | SHA256 | 输入 | 框架/设备 | 状态 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["models"]:
        input_size = item["inputSize"]
        devices = item["deviceSupport"]
        issues = ", ".join(item["issues"]) or "-"
        lines.append(
            f"| {item['modelName']} | {item['modelVersion']} | {item['modelFile']} "
            f"({item['modelSizeBytes'] or 0} B) | [{item['sourceRevision']}]({item['source']}) | "
            f"{item['license']} / {item['commercialUse']} | `{item['sha256']}` | "
            f"{input_size['width']}×{input_size['height']} | "
            f"{', '.join(item['inferenceFramework'])}; CPU={devices['cpu']}, GPU={devices['gpu']}, NPU={devices['npu']} | "
            f"{item['status']}: {issues} |"
        )
    lines.extend(
        [
            "",
            "## 算法清单",
            "",
            "所有算法当前统一标记 `WAITING_FOR_REAL_DATA`；逐算法 TP/FP/TN/FN 与时延报告由现场 Benchmark 生成。",
            "",
            "| ID | 算法名称 | 编码 | 类别 | 状态 |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| {item['id']} | {item['name']} | `{item['code']}` | {item['category']} | {item['acceptanceStatus']} |"
        for item in report["algorithms"]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--strict", action="store_true", help="return non-zero when any blocker exists")
    args = parser.parse_args()
    report = build_inventory(args.asset_dir.resolve())
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, ensure_ascii=False))
    return 1 if args.strict and report["status"] != "EXISTING_OK" else 0


if __name__ == "__main__":
    sys.exit(main())
