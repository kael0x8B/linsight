#!/usr/bin/env python3
"""Verify packaged weights and optionally register LInsight deployment model assets.

The catalog deliberately separates physical assets from logical models. One verified
file can therefore back several model entries without being downloaded repeatedly.
Registration targets the configured MySQL and MinIO containers and is idempotent
for unchanged versions. Legacy upstream catalogs still support URL downloads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PROJECT_DIR / "deploy/model-assets/catalog.json"
DEFAULT_MANIFESTS = PROJECT_DIR / "deploy/model-assets/runtime-manifests.json"
DEFAULT_ASSET_SOURCE = PROJECT_DIR / "deploy/model-assets/files"
DEFAULT_OUTPUT = PROJECT_DIR / "var/model-assets/v1"
DEFAULT_ENV = PROJECT_DIR / ".env"
MINIO_CONFIG_ID = 71000
MINIO_BUCKET = "linsight-models"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步 LInsight V1 内置模型资产")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--download-only", action="store_true", help="只下载并校验到本地（默认）")
    mode.add_argument("--register", action="store_true", help="下载后上传 MinIO 并登记模型版本")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFESTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--asset-source", type=Path, default=DEFAULT_ASSET_SOURCE,
                        help="优先使用已随仓库交付的权重目录，无需联网下载")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument(
        "--public-endpoint",
        help="节点可访问的 MinIO 地址，例如 http://192.168.2.10:29000；默认仅限本机",
    )
    return parser.parse_args()


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, input_text: str | None = None, quiet: bool = False) -> str:
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"命令失败 ({result.returncode}): {command[0]}: {detail}")
    if not quiet and result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.stdout


def validate_catalog(catalog: dict[str, Any]) -> None:
    assets = {item["key"] for item in catalog["assets"]}
    bundles = {item["key"] for item in catalog.get("bundles", [])}
    if len(assets) != len(catalog["assets"]) or len(bundles) != len(catalog.get("bundles", [])):
        raise ValueError("资产或组合包 key 重复")
    for bundle in catalog.get("bundles", []):
        missing = set(bundle["members"]) - assets
        if missing:
            raise ValueError(f"组合包 {bundle['key']} 引用了不存在的资产: {sorted(missing)}")
    models = catalog["models"]
    model_codes = [item["code"] for item in models]
    if not models or len(set(model_codes)) != len(models):
        raise ValueError("逻辑模型目录为空或存在重复 code")
    available = assets | bundles
    for model in models:
        if not model.get("versions"):
            raise ValueError(f"模型 {model['code']} 没有任何版本")
        for version in model["versions"]:
            if version["artifact"] not in available:
                raise ValueError(f"模型 {model['code']} 引用了不存在的资产 {version['artifact']}")


def validate_asset_content(asset: dict[str, Any], path: Path) -> None:
    """Reject truncated ONNX even when its hash matches a broken upstream release.

    This checks protobuf framing, not model correctness. Deployment and single-image
    inference remain mandatory before a model is marked execution-ready.
    """
    if asset.get("format") != "ONNX":
        return
    content = path.read_bytes()
    offset = 0
    fields = set()

    def varint() -> int:
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            if offset >= len(content):
                raise ValueError("truncated protobuf varint")
            byte = content[offset]
            offset += 1
            if shift == 63 and byte > 1:
                raise ValueError("invalid protobuf varint")
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
        raise ValueError("invalid protobuf varint")

    try:
        while offset < len(content):
            tag = varint()
            field, wire = tag >> 3, tag & 7
            if not 0 < field < 2**29:
                raise ValueError("invalid protobuf field")
            fields.add((field, wire))
            if wire == 0:
                varint()
                continue
            if wire == 2:
                size = varint()
            elif wire in (1, 5):
                size = 8 if wire == 1 else 4
            else:
                raise ValueError("unsupported protobuf wire type")
            if size > len(content) - offset:
                raise ValueError("truncated protobuf field")
            offset += size
        if not {(1, 0), (7, 2)} <= fields:
            raise ValueError("missing ONNX model fields")
    except ValueError as error:
        raise ValueError(f"{asset['key']}: invalid ONNX artifact ({error})") from error


def download_asset(
    asset: dict[str, Any], output: Path, asset_source: Path | None = None
) -> dict[str, Any]:
    path = output / asset["fileName"]
    expected = asset.get("expectedSha256")
    if path.exists():
        actual = sha256_file(path)
        if expected is None or actual == expected:
            validate_asset_content(asset, path)
            print(f"[skip] {asset['key']} ({path.stat().st_size} bytes)")
            return {**asset, "path": str(path), "size": path.stat().st_size, "sha256": actual}
        quarantine = path.with_name(f"{path.name}.invalid-{actual[:12]}")
        path.replace(quarantine)
        print(f"[warn] 校验不一致，原文件保留为 {quarantine.name}")

    partial = path.with_suffix(path.suffix + ".part")
    source = asset_source / asset["fileName"] if asset_source else None
    if source is not None and source.is_file():
        print(f"[copy] {asset['key']} -> {path.name}")
        shutil.copyfile(source, partial)
    elif asset.get("url"):
        print(f"[download] {asset['key']} -> {path.name}")
        run([
            "curl", "--fail", "--location", "--retry", "8", "--retry-all-errors",
            "--retry-delay", "2", "--connect-timeout", "20",
            "--continue-at", "-", "--output", str(partial), asset["url"],
        ])
    else:
        raise RuntimeError(f"缺少交付权重 {asset['fileName']}，请完整拉取 deploy/model-assets/files")
    partial.replace(path)
    actual = sha256_file(path)
    if expected and actual != expected:
        quarantine = path.with_name(f"{path.name}.invalid-{actual[:12]}")
        path.replace(quarantine)
        raise RuntimeError(
            f"{asset['key']} SHA256 不一致: expected={expected}, actual={actual}; "
            f"下载结果保留在 {quarantine}"
        )
    validate_asset_content(asset, path)
    return {**asset, "path": str(path), "size": path.stat().st_size, "sha256": actual}


def build_bundle(
    bundle: dict[str, Any], assets: dict[str, dict[str, Any]], output: Path, catalog_version: str
) -> dict[str, Any]:
    path = output / bundle["fileName"]
    member_records = [assets[key] for key in bundle["members"]]
    manifest = {
        "schemaVersion": "1.0",
        "catalogVersion": catalog_version,
        "bundleKey": bundle["key"],
        "licenseSpdx": bundle["licenseSpdx"],
        "runtimeCompatibility": bundle.get("runtimeCompatibility", []),
        "members": [
            {
                "key": item["key"],
                "fileName": item["fileName"],
                "sha256": item["sha256"],
                "size": item["size"],
                "sourceRepository": item["sourceRepository"],
                "sourceRevision": item["sourceRevision"],
                "licenseSpdx": item["licenseSpdx"],
            }
            for item in member_records
        ],
    }
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo("bundle-manifest.json", date_time=(2026, 9, 2, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, payload)
        for item in member_records:
            info = zipfile.ZipInfo(f"models/{item['fileName']}", date_time=(2026, 9, 2, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            with Path(item["path"]).open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    result = {
        **bundle,
        "format": "ARCHIVE",
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "sourceRepository": "linsight:builtin-model-assets-v1",
        "sourceRevision": catalog_version,
    }
    print(f"[bundle] {bundle['key']} ({result['size']} bytes)")
    return result


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


class LocalRegistry:
    def __init__(
        self, env: dict[str, str], tenant_id: int, public_endpoint: str | None = None
    ) -> None:
        self.mysql_container = os.environ.get("LINSIGHT_MYSQL_CONTAINER", "linsight-mysql")
        self.minio_container = os.environ.get("LINSIGHT_MINIO_CONTAINER", "linsight-minio")
        self.database = os.environ.get("LINSIGHT_MIGRATION_DATABASE", "linsight")
        self.mysql_password = env.get("MYSQL_ROOT_PASSWORD", "linsight_dev")
        self.minio_user = env.get("MINIO_ROOT_USER", "linsight")
        self.minio_password = env.get("MINIO_ROOT_PASSWORD", "linsight_minio_dev")
        self.minio_port = env.get("MINIO_API_PORT", "29000")
        self.storage_endpoint = f"http://127.0.0.1:{self.minio_port}"
        self.tenant_id = tenant_id
        external_endpoint = (public_endpoint or env.get("LINSIGHT_MODEL_PUBLIC_ENDPOINT")
                             or f"http://127.0.0.1:{self.minio_port}")
        if not external_endpoint.startswith(("http://", "https://")):
            raise ValueError("--public-endpoint 必须是 http:// 或 https:// URL")
        self.domain = f"{external_endpoint.rstrip('/')}/{MINIO_BUCKET}"

    def mysql(self, sql: str) -> str:
        command = [
            "docker", "exec", "-i", "-e", f"MYSQL_PWD={self.mysql_password}",
            self.mysql_container, "mysql", "--default-character-set=utf8mb4", "--batch",
            "--skip-column-names", "--raw", "-uroot", self.database,
        ]
        return run(command, input_text=sql, quiet=True).strip()

    def preflight(self) -> None:
        for container in (self.mysql_container, self.minio_container):
            running = run(["docker", "inspect", "-f", "{{.State.Running}}", container], quiet=True).strip()
            if running != "true":
                raise RuntimeError(f"容器 {container} 未运行")
        old_index = self.mysql(
            "SELECT COUNT(*) FROM information_schema.statistics "
            f"WHERE table_schema={sql_quote(self.database)} AND table_name='ai_model_version' "
            "AND index_name='uk_ai_model_version_tenant_sha_deleted';\n"
        )
        if old_index != "0":
            raise RuntimeError("共享资产迁移尚未执行，请先运行 make migrate")

    def configure_storage(self) -> None:
        config = {
            "@class": "com.linsight.module.infra.framework.file.core.client.s3.S3FileClientConfig",
            "endpoint": self.storage_endpoint,
            "domain": self.domain,
            "bucket": MINIO_BUCKET,
            "accessKey": self.minio_user,
            "accessSecret": self.minio_password,
            "enablePathStyleAccess": True,
            "enablePublicAccess": False,
            "region": "us-east-1",
        }
        sql = f"""
UPDATE infra_file_config SET master=b'0' WHERE master=b'1';
INSERT INTO infra_file_config
(id,name,storage,remark,master,config,creator,updater,deleted)
VALUES ({MINIO_CONFIG_ID},'LINsight 模型资产 MinIO',20,'内置模型资产私有存储',b'1',
        {sql_quote(json.dumps(config, ensure_ascii=False, separators=(',', ':')))},'system','system',b'0')
ON DUPLICATE KEY UPDATE name=VALUES(name),storage=VALUES(storage),remark=VALUES(remark),
  master=VALUES(master),config=VALUES(config),deleted=b'0',updater='system';
"""
        self.mysql(sql)

    def upload(self, artifact: dict[str, Any]) -> str:
        object_path = artifact.get("objectPath", f"builtin/v1/{artifact['fileName']}")
        temp_dir = "/tmp/linsight-model-import-v1"
        run(["docker", "exec", self.minio_container, "mkdir", "-p", temp_dir], quiet=True)
        run(["docker", "cp", artifact["path"], f"{self.minio_container}:{temp_dir}/{artifact['fileName']}"], quiet=True)
        run([
            "docker", "exec", self.minio_container, "mc", "alias", "set", "linsight-local",
            "http://127.0.0.1:9000", self.minio_user, self.minio_password,
        ], quiet=True)
        run(["docker", "exec", self.minio_container, "mc", "mb", "--ignore-existing", f"linsight-local/{MINIO_BUCKET}"], quiet=True)
        run([
            "docker", "exec", self.minio_container, "mc", "cp",
            f"{temp_dir}/{artifact['fileName']}", f"linsight-local/{MINIO_BUCKET}/{object_path}",
        ], quiet=True)
        return object_path

    def cleanup(self) -> None:
        run(["docker", "exec", self.minio_container, "rm", "-rf",
             "/tmp/linsight-model-import-v1"], quiet=True)

    def register_file(self, artifact: dict[str, Any], object_path: str) -> str:
        url = f"{self.domain}/{object_path}"
        content_type = {
            "ONNX": "application/octet-stream",
            "TORCHSCRIPT": "application/octet-stream",
            "PYTORCH": "application/octet-stream",
            "ARCHIVE": "application/zip",
        }.get(artifact["format"], "application/octet-stream")
        content_type = artifact.get("contentType", content_type)
        sql = f"""
UPDATE infra_file
SET name={sql_quote(artifact['fileName'])},url={sql_quote(url)},type={sql_quote(content_type)},
    size={artifact['size']},updater='system'
WHERE config_id={MINIO_CONFIG_ID} AND path={sql_quote(object_path)} AND deleted=b'0';
INSERT INTO infra_file (config_id,name,path,url,type,size,creator,updater,deleted)
SELECT {MINIO_CONFIG_ID},{sql_quote(artifact['fileName'])},{sql_quote(object_path)},
       {sql_quote(url)},{sql_quote(content_type)},{artifact['size']},'system','system',b'0'
WHERE NOT EXISTS (SELECT 1 FROM infra_file WHERE config_id={MINIO_CONFIG_ID}
                  AND path={sql_quote(object_path)} AND deleted=b'0');
"""
        self.mysql(sql)
        return url

    def register_version(
        self,
        model_code: str,
        version: dict[str, Any],
        artifact: dict[str, Any],
        url: str,
        runtime_manifest: dict[str, Any] | None,
    ) -> None:
        model_id = self.mysql(
            "SELECT id FROM ai_model "
            f"WHERE tenant_id={self.tenant_id} AND code={sql_quote(model_code)} AND deleted=b'0' LIMIT 1;\n"
        )
        if not model_id:
            raise RuntimeError(f"数据库缺少逻辑模型: {model_code}; 请先运行 make migrate")
        existing = self.mysql(
            "SELECT JSON_OBJECT('sha256',sha256,'runtimeManifest',runtime_manifest) "
            f"FROM ai_model_version WHERE model_id={model_id} "
            f"AND version={sql_quote(version['version'])} AND tenant_id={self.tenant_id} "
            "AND deleted=b'0' LIMIT 1;\n"
        )
        if existing:
            current = json.loads(existing)
            if current["sha256"] != artifact["sha256"] or current["runtimeManifest"] != runtime_manifest:
                raise RuntimeError(f"{model_code} / {version['version']} 已存在且权重或执行契约不同；请使用新版本号")
        manifest_sql = (
            sql_quote(json.dumps(runtime_manifest, ensure_ascii=False, separators=(",", ":")))
            if runtime_manifest
            else "NULL"
        )
        artifact_name = artifact.get("artifactName", artifact["fileName"])
        sql = f"""
UPDATE ai_model_version
SET artifact_ref={sql_quote(url)},
    runtime_manifest={manifest_sql},
    updater='system'
WHERE model_id={model_id} AND version={sql_quote(version['version'])}
  AND sha256={sql_quote(artifact['sha256'])} AND tenant_id={self.tenant_id} AND deleted=b'0';
INSERT IGNORE INTO ai_model_version
(model_id,version,source_repository,source_revision,artifact_ref,artifact_name,artifact_format,
 runtime_manifest,artifact_size,sha256,license_spdx,validation_status,publish_status,
 creator,updater,deleted,tenant_id)
VALUES
({model_id},{sql_quote(version['version'])},{sql_quote(artifact['sourceRepository'])},
 {sql_quote(artifact['sourceRevision'])},{sql_quote(url)},{sql_quote(artifact_name)},
 {sql_quote(artifact['format'])},
 {manifest_sql},
 {artifact['size']},{sql_quote(artifact['sha256'])},
 {sql_quote(artifact['licenseSpdx'])},'VERIFIED','DRAFT','system','system',b'0',{self.tenant_id});
"""
        self.mysql(sql)

    def register_model(self, model: dict[str, Any]) -> None:
        """Restore logical assets by code; deployment IDs and execution evidence are not portable."""
        if not model.get("name"):
            return  # Legacy download catalogs rely on migration-created logical assets.
        sql = f"""
INSERT INTO ai_model (name,code,source_type,description,status,creator,updater,tenant_id)
VALUES ({sql_quote(model['name'])},{sql_quote(model['code'])},
        {sql_quote(model.get('sourceType', 'PRESET'))},
        {sql_quote(model.get('description', ''))},0,'system','system',{self.tenant_id})
ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description),status=0,
  updater='system';
"""
        self.mysql(sql)

    def promote_version(self, model_code: str, version: str) -> None:
        """Select the catalog's single production candidate without claiming execution readiness."""
        sql = f"""
SET @model_id = (SELECT id FROM ai_model WHERE tenant_id={self.tenant_id}
  AND code={sql_quote(model_code)} AND deleted=b'0' LIMIT 1);
SET @version_id = (SELECT id FROM ai_model_version WHERE tenant_id={self.tenant_id}
  AND model_id=@model_id AND version={sql_quote(version)} AND deleted=b'0' LIMIT 1);
UPDATE ai_model_version SET publish_status='SUPERSEDED',updater='system'
WHERE tenant_id={self.tenant_id} AND model_id=@model_id AND id<>@version_id
  AND publish_status='PUBLISHED' AND deleted=b'0';
UPDATE ai_model_version SET publish_status='PUBLISHED',published_time=COALESCE(published_time,NOW()),
  updater='system' WHERE id=@version_id;
UPDATE ai_model SET current_version_id=@version_id,updater='system' WHERE id=@model_id;
"""
        self.mysql(sql)


def main(args: argparse.Namespace | None = None, registry: LocalRegistry | None = None) -> int:
    args = args or parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    manifest_document = json.loads(args.manifests.read_text(encoding="utf-8"))
    manifests = manifest_document.get("manifests", {})
    validate_catalog(catalog)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.register:
        registry = registry or LocalRegistry(load_env(args.env_file), args.tenant_id, args.public_endpoint)
        registry.preflight()

    used_keys = {
        version["artifact"]
        for model in catalog["models"]
        for version in model["versions"]
    }
    selected_bundles = [
        bundle for bundle in catalog.get("bundles", []) if bundle["key"] in used_keys
    ]
    required_asset_keys = {
        key for bundle in selected_bundles for key in bundle["members"]
    } | used_keys
    downloaded: dict[str, dict[str, Any]] = {}
    for asset in catalog["assets"]:
        if asset["key"] not in required_asset_keys:
            continue
        downloaded[asset["key"]] = download_asset(asset, args.output, args.asset_source)

    artifacts = dict(downloaded)
    for bundle in selected_bundles:
        artifacts[bundle["key"]] = build_bundle(
            bundle, downloaded, args.output, catalog["catalogVersion"]
        )

    lock = {
        "schemaVersion": catalog["schemaVersion"],
        "catalogVersion": catalog["catalogVersion"],
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "assets": [
            {
                key: item[key]
                for key in (
                    "key", "fileName", "format", "size", "sha256", "sourceRepository",
                    "sourceRevision", "licenseSpdx", "runtimeCompatibility",
                )
                if key in item
            }
            for item in artifacts.values()
        ],
    }
    lock_path = args.output / "assets-lock.json"
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total_size = sum(item["size"] for item in downloaded.values())
    print(f"[ok] {len(downloaded)} 个上游文件已落盘，共 {total_size} bytes")
    print(f"[ok] 锁定清单: {lock_path}")

    if not args.register:
        return 0

    registry.configure_storage()
    urls: dict[str, str] = {}
    for key in sorted(used_keys):
        artifact = artifacts[key]
        print(f"[upload] {key}")
        object_path = registry.upload(artifact)
        urls[key] = registry.register_file(artifact, object_path)
    for model in catalog["models"]:
        registry.register_model(model)
        for version in model["versions"]:
            artifact = artifacts[version["artifact"]]
            registry.register_version(
                model["code"],
                version,
                artifact,
                urls[version["artifact"]],
                manifests.get(version.get("manifestKey", version["artifact"])),
            )
            if version.get("production") is True:
                registry.promote_version(model["code"], version["version"])
            print(f"[register] {model['code']} / {version['version']}")
    if args.catalog.resolve() == DEFAULT_CATALOG.resolve():
        spec = importlib.util.spec_from_file_location(
            "deployment_algorithm_assets", PROJECT_DIR / "scripts/deployment_algorithm_assets.py")
        algorithms = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(algorithms)
        algorithms.synchronize(registry)
    registry.cleanup()
    count = registry.mysql(
        f"SELECT COUNT(*) FROM ai_model_version WHERE tenant_id={args.tenant_id} AND deleted=b'0';\n"
    )
    print(f"[ok] 数据库现有模型版本记录: {count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"[error] {error}", file=sys.stderr)
        raise SystemExit(1)
