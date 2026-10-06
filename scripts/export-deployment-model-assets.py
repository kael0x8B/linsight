#!/usr/bin/env python3
"""Export current published model assets without deployment state or environment secrets."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("asset_sync", ROOT / "scripts/sync-builtin-model-assets.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def main() -> int:
    parser = argparse.ArgumentParser(description="导出当前发布模型为可离线初始化的源码交付目录")
    parser.add_argument("--output", type=Path, default=ROOT / "deploy/model-assets")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--catalog-version", required=True)
    args = parser.parse_args()
    registry = sync.LocalRegistry(sync.load_env(args.env_file), args.tenant_id)
    registry.preflight()
    rows = registry.mysql(f"""
SELECT JSON_OBJECT(
  'code',m.code,'name',m.name,'sourceType',m.source_type,'description',m.description,
  'version',v.version,'artifactName',v.artifact_name,'format',v.artifact_format,
  'size',v.artifact_size,'sha256',v.sha256,'sourceRepository',v.source_repository,
  'sourceRevision',v.source_revision,'licenseSpdx',v.license_spdx,
  'runtimeManifest',v.runtime_manifest,'artifactRef',v.artifact_ref,
  'objectPath',(SELECT f.path FROM infra_file f
     WHERE f.url=v.artifact_ref AND f.deleted=b'0' AND f.config_id={sync.MINIO_CONFIG_ID}
     ORDER BY f.id DESC LIMIT 1))
FROM ai_model m JOIN ai_model_version v ON v.id=m.current_version_id
WHERE m.tenant_id={args.tenant_id} AND m.deleted=b'0' AND m.status=0
  AND v.tenant_id={args.tenant_id} AND v.deleted=b'0' AND v.publish_status='PUBLISHED'
ORDER BY m.code;
""")
    models = [json.loads(row) for row in rows.splitlines() if row]
    if not models:
        raise RuntimeError("没有当前发布的模型，已停止导出")
    files = args.output / "files"
    files.mkdir(parents=True, exist_ok=True)
    sync.run([
        "docker", "exec", registry.minio_container, "mc", "alias", "set",
        "linsight-model-export", "http://127.0.0.1:9000",
        registry.minio_user, registry.minio_password,
    ], quiet=True)
    assets = {}
    manifests = {}
    catalog_models = []
    for model in models:
        object_path = model["objectPath"]
        if not object_path:
            reference = urlsplit(model["artifactRef"])
            prefix = f"/{sync.MINIO_BUCKET}/"
            # Older uploads stored signed URLs; export only the object key, never their query.
            if (reference.scheme in {"http", "https"} and not reference.username
                    and reference.path.startswith(prefix)):
                object_path = reference.path[len(prefix):]
        if not object_path or ".." in Path(object_path).parts or object_path.startswith("/"):
            raise ValueError(f"{model['code']}: 缺少可信的模型对象存储记录")
        key = model["sha256"]
        name = Path(model["artifactName"]).name
        filename = f"{key[:12]}-{name}"
        asset = {
            "key": key, "fileName": filename, "artifactName": name,
            "format": model["format"], "expectedSha256": key,
            "size": model["size"], "sourceRepository": model["sourceRepository"],
            "sourceRevision": model["sourceRevision"], "licenseSpdx": model["licenseSpdx"],
        }
        if key not in assets:
            path = files / filename
            with path.open("wb") as target:
                result = subprocess.run([
                    "docker", "exec", registry.minio_container, "mc", "cat",
                    f"linsight-model-export/{sync.MINIO_BUCKET}/{object_path}",
                ], stdout=target, stderr=subprocess.PIPE, check=False)
            if result.returncode or path.stat().st_size != model["size"] or sync.sha256_file(path) != key:
                raise ValueError(f"{model['code']}: 模型下载/大小/SHA256 校验失败")
            sync.validate_asset_content(asset, path)
            assets[key] = asset
        manifest_key = f"{model['code']}@{model['version']}"
        if not model["runtimeManifest"]:
            raise ValueError(f"{model['code']}: 缺少 Runtime 执行契约")
        manifests[manifest_key] = model["runtimeManifest"]
        catalog_models.append({
            "code": model["code"], "name": model["name"],
            "sourceType": model["sourceType"], "description": model["description"] or "",
            "versions": [{"version": model["version"], "artifact": key,
                          "manifestKey": manifest_key, "production": True}],
        })
        print(f"[export] {model['code']} / {model['version']}")
    catalog = {
        "schemaVersion": "1.0", "catalogVersion": args.catalog_version,
        "description": "Current published model weights for offline initialization. Target-node execution evidence is not copied.",
        "assets": list(assets.values()), "models": catalog_models,
    }
    sync.validate_catalog(catalog)
    (args.output / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "runtime-manifests.json").write_text(
        json.dumps({"schemaVersion": "1.0", "manifests": manifests}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"[ok] {len(catalog_models)} 个当前模型，{len(assets)} 个已校验文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
