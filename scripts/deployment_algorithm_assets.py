"""Portable algorithm catalog: stable model codes, immutable packages, no field evidence."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "deploy/algorithm-assets/catalog.json"


def quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def document(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rows(registry, query: str) -> list[dict]:
    return [json.loads(line) for line in registry.mysql(query).splitlines() if line]


def model_references(value, models: dict, *, exporting: bool):
    """Resolve modelId/modelIds in nested DAGs without preserving database primary keys."""
    if isinstance(value, list):
        return [model_references(item, models, exporting=exporting) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    single, multiple = ("modelId", "modelIds") if exporting else ("modelCode", "modelCodes")
    target_single, target_multiple = ("modelCode", "modelCodes") if exporting else ("modelId", "modelIds")
    for key, item in value.items():
        if key in (single, multiple):
            references = item if key == multiple else [item]
            missing = [ref for ref in references if ref not in models]
            if missing:
                raise ValueError(f"编排引用了未交付的模型: {missing}")
            result[target_multiple if key == multiple else target_single] = (
                [models[ref] for ref in references] if key == multiple else models[item]
            )
        else:
            result[key] = model_references(item, models, exporting=exporting)
    return result


def export_catalog(registry, output: Path, catalog_version: str) -> None:
    model_catalog = json.loads((ROOT / "deploy/model-assets/catalog.json").read_text(encoding="utf-8"))
    delivered = {model["code"] for model in model_catalog["models"]}
    models = rows(registry, "SELECT JSON_OBJECT('id',id,'code',code) FROM ai_model "
                  f"WHERE tenant_id={registry.tenant_id} AND deleted=0;")
    model_codes = {model["id"]: model["code"] for model in models if model["code"] in delivered}
    algorithms = rows(registry, f"""
SELECT JSON_OBJECT('code',a.code,'name',a.name,'category',a.category,'sceneGroup',a.scene_group,
 'implementationType',a.implementation_type,'description',a.description,'capabilityKey',a.capability_key,
 'requiredCapabilities',a.required_capabilities,'eventType',a.event_type,'defaultModelId',a.default_model_id,
 'parameterSchema',a.parameter_schema,'defaultParameters',a.default_parameters,'dag',p.dag,
 'artifactRef',p.package_artifact_ref,
 'objectPath',(SELECT f.path FROM infra_file f WHERE f.url=p.package_artifact_ref AND f.deleted=0
               AND f.config_id=71000 ORDER BY f.id DESC LIMIT 1))
FROM ai_algorithm a JOIN ai_pipeline_version p ON p.id=a.current_pipeline_version_id
WHERE a.tenant_id={registry.tenant_id} AND p.tenant_id={registry.tenant_id}
 AND a.status=0 AND a.deleted=0 AND p.deleted=0 AND p.validation_status='PUBLISHED'
ORDER BY a.code;
""")
    if not algorithms:
        raise ValueError("没有已发布且启用的算法，停止导出")
    files = output / "files"
    files.mkdir(parents=True, exist_ok=True)
    registry.mysql("SELECT 1;")
    subprocess.run(["docker", "exec", registry.minio_container, "mc", "alias", "set",
                    "linsight-algorithm-export", "http://127.0.0.1:9000",
                    registry.minio_user, registry.minio_password],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for algorithm in algorithms:
        default_id = algorithm.pop("defaultModelId")
        if default_id is not None and default_id not in model_codes:
            raise ValueError(f"{algorithm['code']}: 默认模型不在交付清单中")
        algorithm["defaultModelCode"] = model_codes.get(default_id)
        dag = copy.deepcopy(algorithm["dag"])
        # Acceptance and evidence describe the source environment and cannot certify a new site.
        dag["acceptance"] = {"status": "PENDING", "note": "当前环境尚未完成现场验收"}
        dag.pop("deploymentCatalog", None)
        algorithm["dag"] = model_references(dag, model_codes, exporting=True)
        reference = algorithm.pop("artifactRef")
        object_path = algorithm.pop("objectPath")
        descriptor = dag.get("algorithmPackage")
        if descriptor:
            if not reference:
                raise ValueError(f"{algorithm['code']}: 算法包文件缺失")
            if not object_path:
                parsed = urlsplit(reference)
                prefix = "/linsight-models/"
                if parsed.scheme in ("http", "https") and parsed.path.startswith(prefix):
                    object_path = parsed.path[len(prefix):]
            if not object_path or object_path.startswith("/") or ".." in Path(object_path).parts:
                raise ValueError(f"{algorithm['code']}: 算法包对象路径无效")
            digest = descriptor["sha256"]
            filename = f"{digest[:12]}-{algorithm['code']}.zip"
            target = files / filename
            with target.open("wb") as stream:
                subprocess.run(["docker", "exec", registry.minio_container, "mc", "cat",
                                f"linsight-algorithm-export/linsight-models/{object_path}"],
                               stdout=stream, stderr=subprocess.PIPE, check=True)
            artifact = {"fileName": filename, "sha256": digest, "size": target.stat().st_size}
            validate_package(artifact, target, descriptor)
            algorithm["artifact"] = artifact
    retired = rows(registry, "SELECT JSON_OBJECT('code',code) FROM ai_algorithm "
                   f"WHERE tenant_id={registry.tenant_id} AND status=1 AND category IN ('CORE','EXTENSION') "
                   "AND creator='system' ORDER BY code;")
    catalog = {"schemaVersion": "1.0", "catalogVersion": catalog_version,
               "visibleAlgorithmCount": len({item["name"] for item in algorithms}),
               "retiredSeedCodes": [item["code"] for item in retired], "algorithms": algorithms}
    (output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] 导出 {len(algorithms)} 条算法定义，界面合并同名后 {catalog['visibleAlgorithmCount']} 个算法")


def validate_package(artifact: dict, path: Path, descriptor: dict) -> None:
    if Path(artifact["fileName"]).name != artifact["fileName"]:
        raise ValueError("算法包文件名不能包含路径")
    if (not path.is_file() or path.stat().st_size != artifact["size"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]
            or artifact["sha256"] != descriptor["sha256"]):
        raise ValueError(f"算法包大小或 SHA256 校验失败: {artifact['fileName']}")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"算法包损坏: {artifact['fileName']}")
        if json.loads(archive.read("algorithm.json")) != descriptor["manifest"]:
            raise ValueError(f"算法包 manifest 与发布记录不一致: {artifact['fileName']}")


def synchronize(registry, catalog_path: Path = DEFAULT_CATALOG) -> None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    algorithms = catalog["algorithms"]
    codes = [item["code"] for item in algorithms]
    if not codes or len(codes) != len(set(codes)):
        raise ValueError("算法目录为空或编码重复")
    models = rows(registry, "SELECT JSON_OBJECT('id',id,'code',code) FROM ai_model "
                  f"WHERE tenant_id={registry.tenant_id} AND deleted=0;")
    model_ids = {model["code"]: model["id"] for model in models}
    prepared = []
    # Validate every package and model reference before uploading or changing algorithm defaults.
    for item in algorithms:
        item = copy.deepcopy(item)
        dag = model_references(item["dag"], model_ids, exporting=False)
        model_code = item["defaultModelCode"]
        if model_code is not None and model_code not in model_ids:
            raise ValueError(f"默认模型不存在: {model_code}")
        digest = hashlib.sha256(document(item["dag"]).encode("utf-8")).hexdigest()
        dag["deploymentCatalog"] = {"sha256": digest}
        if item.get("artifact"):
            artifact = item["artifact"]
            validate_package(artifact, catalog_path.parent / "files" / artifact["fileName"], dag["algorithmPackage"])
        prepared.append((item, dag, digest, model_ids.get(model_code)))

    for item, dag, digest, model_id in prepared:
        artifact_ref = "NULL"
        if item.get("artifact"):
            artifact = {**item["artifact"], "format": "ARCHIVE",
                        "path": str(catalog_path.parent / "files" / item["artifact"]["fileName"]),
                        "objectPath": f"ai-video/algorithm/deployment/{item['artifact']['fileName']}"}
            path = registry.upload(artifact)
            artifact_ref = quote(registry.register_file(artifact, path))
        code = quote(item["code"])
        existing = rows(registry, "SELECT JSON_OBJECT('id',p.id,'version',p.version,'dag',p.dag) "
                        "FROM ai_pipeline_version p JOIN ai_algorithm a ON a.id=p.algorithm_id "
                        f"WHERE a.tenant_id={registry.tenant_id} AND p.tenant_id={registry.tenant_id} "
                        f"AND a.code={code} AND a.deleted=0 AND p.deleted=0 ORDER BY p.version;")
        current = next((row for row in existing if row["dag"].get("deploymentCatalog", {}).get("sha256") == digest), None)
        if current:
            comparable = copy.deepcopy(current["dag"])
            comparable["acceptance"] = dag["acceptance"]
            if comparable != dag:
                raise ValueError(f"{item['code']}: 已导入的编排版本被修改，停止覆盖")
        next_version = max((row["version"] for row in existing), default=0) + 1
        columns = {"name": item["name"], "code": item["code"], "category": item["category"],
                   "scene_group": item["sceneGroup"], "implementation_type": item["implementationType"],
                   "description": item["description"], "capability_key": item["capabilityKey"],
                   "event_type": item["eventType"]}
        values = {key: "NULL" if value is None else quote(value) for key, value in columns.items()}
        for key, field in (("required_capabilities", "requiredCapabilities"), ("parameter_schema", "parameterSchema"),
                           ("default_parameters", "defaultParameters")):
            values[key] = "NULL" if item[field] is None else quote(document(item[field]))
        values["default_model_id"] = str(model_id) if model_id is not None else "NULL"
        values.update(status="0", creator="'system'", updater="'system'", tenant_id=str(registry.tenant_id))
        upsert = f"INSERT INTO ai_algorithm ({','.join(values)}) VALUES ({','.join(values.values())}) "
        upsert += "ON DUPLICATE KEY UPDATE " + ",".join(f"{key}=VALUES({key})" for key in values if key not in ("code", "creator", "tenant_id")) + ";"
        pipeline_sql = (
            f"SET @pipeline_id={int(current['id'])}; UPDATE ai_pipeline_version SET package_artifact_ref={artifact_ref} WHERE id=@pipeline_id;"
            if current else
            "INSERT INTO ai_pipeline_version (algorithm_id,version,dag,validation_status,package_artifact_ref,"
            "published_time,creator,updater,tenant_id) VALUES "
            f"(@algorithm_id,{next_version},{quote(document(dag))},'PUBLISHED',{artifact_ref},NOW(),'system','system',{registry.tenant_id}); "
            "SET @pipeline_id=LAST_INSERT_ID();"
        )
        registry.mysql(f"START TRANSACTION; {upsert} "
                       f"SET @algorithm_id=(SELECT id FROM ai_algorithm WHERE tenant_id={registry.tenant_id} AND code={code} AND deleted=0); "
                       f"{pipeline_sql} UPDATE ai_algorithm SET current_pipeline_version_id=@pipeline_id WHERE id=@algorithm_id; COMMIT;")
        print(f"[algorithm] {item['code']}")
    retired = set(catalog["retiredSeedCodes"]) - set(codes)
    if retired:
        registry.mysql(f"UPDATE ai_algorithm SET status=1,updater='system' WHERE tenant_id={registry.tenant_id} "
                       "AND deleted=0 AND creator='system' AND category IN ('CORE','EXTENSION') "
                       f"AND code IN ({','.join(quote(code) for code in sorted(retired))});")
    print(f"[ok] 已同步 {len(algorithms)} 条算法定义，交付目录显示 {catalog['visibleAlgorithmCount']} 个算法")
