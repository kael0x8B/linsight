"""Encrypted, restorable business configuration and its referenced object resources."""
from __future__ import annotations

import base64
import datetime
import gzip
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pymysql
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "deploy/platform-snapshot"
KEY_FILE = ROOT / "var/platform-snapshot/deployment.key"
AAD = b"linsight-platform-snapshot-v1"
TABLES = (
    "ai_camera_group", "ai_camera", "ai_edge_node", "ai_model", "ai_model_version",
    "ai_model_test", "ai_model_deployment", "ai_algorithm", "ai_pipeline_version",
    "ai_rule", "ai_rule_version", "ai_recognition_library", "ai_recognition_library_entry",
    "ai_face_reference", "ai_task", "ai_entry_access", "ai_global_settings_version",
    "ai_video_wall_layout", "ai_camera_display_preference", "ai_webhook_endpoint",
)


def native_module():
    spec = importlib.util.spec_from_file_location("native_snapshot", ROOT / "scripts/initialize-model-assets-native.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def key_bytes(path: Path) -> bytes:
    key = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    if len(key) != 32:
        raise ValueError("部署密钥必须为 32 字节")
    return key


def seal(content: bytes, key: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, gzip.compress(content, mtime=0), AAD)


def unseal(content: bytes, key: bytes) -> bytes:
    return gzip.decompress(AESGCM(key).decrypt(content[:12], content[12:], AAD))


def table_rows(connection, table: str, tenant_id: int = 1) -> tuple[list, list]:
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        columns = cursor.fetchall()
        json_columns = [column["Field"] for column in columns if column["Type"] == "json"]
        cursor.execute(f"SELECT * FROM `{table}` WHERE tenant_id=%s ORDER BY id", (tenant_id,))
        rows = list(cursor.fetchall())
    for row in rows:
        for name, value in row.items():
            if name in json_columns and value is not None:
                row[name] = json.loads(value)
            elif isinstance(value, bytes):
                row[name] = int.from_bytes(value, "big")
            elif isinstance(value, (datetime.date, datetime.datetime)):
                row[name] = value.isoformat(sep=" ") if isinstance(value, datetime.datetime) else value.isoformat()
    return rows, json_columns


def visit(value, transform):
    if isinstance(value, dict):
        return {key: visit(item, transform) for key, item in value.items()}
    if isinstance(value, list):
        return [visit(item, transform) for item in value]
    return transform(value) if isinstance(value, str) else value


def export_snapshot(registry, output: Path = DIRECTORY, key_file: Path = KEY_FILE):
    output.mkdir(parents=True, exist_ok=True)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        with key_file.open("x", encoding="ascii") as stream:
            stream.write(base64.b64encode(os.urandom(32)).decode("ascii") + "\n")
        key_file.chmod(0o600)
    key = key_bytes(key_file)
    tables, types = {}, {}
    for table in TABLES:
        tables[table], types[table] = table_rows(registry.connection, table, registry.tenant_id)
    # Deliver current configuration, including versions pinned by tasks and recognition libraries.
    tables["ai_task"] = [row for row in tables["ai_task"] if not row["deleted"]]
    pipelines = {row["current_pipeline_version_id"] for row in tables["ai_algorithm"] if not row["deleted"]}
    pipelines.update(row["pipeline_version_id"] for row in tables["ai_task"])
    tables["ai_pipeline_version"] = [row for row in tables["ai_pipeline_version"] if row["id"] in pipelines]
    for row in tables["ai_algorithm"]:
        if row["current_pipeline_version_id"] not in pipelines:
            row["current_pipeline_version_id"] = None
    versions = {row["current_version_id"] for row in tables["ai_model"] if row["current_version_id"] is not None}
    for row in tables["ai_task"]:
        versions.add(row["model_version_id"])
        versions.update(row["model_bindings"].values())
    versions.update(row["model_version_id"] for row in tables["ai_face_reference"])
    versions.update(row["model_version_id"] for row in tables["ai_entry_access"])
    tables["ai_model_version"] = [row for row in tables["ai_model_version"] if row["id"] in versions]
    for table in ("ai_model_test", "ai_model_deployment"):
        tables[table] = [row for row in tables[table] if row["model_version_id"] in versions]

    # References and credentials remain inside the encrypted payload, never the Git-visible manifest.
    source_domains = {registry.domain}
    with registry.connection.cursor() as cursor:
        cursor.execute("SELECT config FROM infra_file_config WHERE storage=20 AND deleted=0")
        for (raw,) in cursor.fetchall():
            configuration = json.loads(raw)
            if configuration.get("domain"):
                source_domains.add(configuration["domain"].rstrip("/"))
    references = {}

    def collect(value):
        # Stored objects survive workstation IP changes; resolve by bucket/key rather
        # than only the currently configured MinIO hostname.
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.path.startswith("/linsight-models/"):
            references[value] = unquote(parsed.path[len("/linsight-models/"):])
            return value
        for domain in source_domains:
            if value.startswith(domain + "/"):
                references[value] = unquote(urlsplit(value).path[len(urlsplit(domain).path):].lstrip("/"))
                break
        return value

    visit(tables, collect)
    for table, field in (("ai_model_version", "artifact_ref"), ("ai_pipeline_version", "package_artifact_ref")):
        if any(row.get(field) and row[field] not in references for row in tables[table]):
            raise ValueError(f"{table} 存在未纳入快照的资源引用")
    reused = {}
    for directory in (ROOT / "deploy/model-assets/files", ROOT / "deploy/algorithm-assets/files"):
        for path in directory.glob("*"):
            if path.is_file():
                reused[digest(path.read_bytes())] = path.relative_to(ROOT).as_posix()
    resources, aliases = {}, {}
    for reference, path in sorted(references.items()):
        response = registry.storage.get_object("linsight-models", path)
        try:
            content = response.read()
        finally:
            response.close()
            response.release_conn()
        checksum = digest(content)
        aliases[reference] = checksum
        if checksum in resources:
            continue
        record = {"sha256": checksum, "size": len(content),
                  "contentType": mimetypes.guess_type(path)[0] or "application/octet-stream"}
        if checksum in reused:
            record.update(source=reused[checksum], encrypted=False)
        else:
            encrypted = seal(content, key)
            parts = []
            for index, start in enumerate(range(0, len(encrypted), 32 * 1024 * 1024)):
                name = f"resources/{checksum}.{index:03d}.enc"
                target = output / name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(encrypted[start:start + 32 * 1024 * 1024])
                parts.append({"path": name, "sha256": digest(target.read_bytes())})
            record.update(parts=parts, encrypted=True)
        resources[checksum] = record
    for row in tables["ai_model_version"]:
        if row["sha256"] != aliases[row["artifact_ref"]]:
            raise ValueError("模型文件与发布记录摘要不一致")
    for row in tables["ai_pipeline_version"]:
        if row.get("package_artifact_ref") and row["dag"]["algorithmPackage"]["sha256"] != aliases[row["package_artifact_ref"]]:
            raise ValueError("算法包文件与发布记录摘要不一致")
    active_algorithms = [row for row in tables["ai_algorithm"] if not row["deleted"] and row["status"] == 0]
    counts = {"models": sum(not row["deleted"] and row["status"] == 0 for row in tables["ai_model"]),
              "algorithms": len({row["name"] for row in active_algorithms}),
              "algorithmRecords": len(active_algorithms),
              "rules": sum(not row["deleted"] for row in tables["ai_rule"]), "tasks": len(tables["ai_task"]),
              "cameras": sum(not row["deleted"] for row in tables["ai_camera"]),
              "nodes": sum(not row["deleted"] for row in tables["ai_edge_node"])}
    payload = {"schemaVersion": 1, "tenantId": registry.tenant_id, "tables": tables,
               "jsonColumns": types, "resources": aliases}
    encrypted = seal(encode(payload), key)
    (output / "configuration.enc").write_bytes(encrypted)
    manifest = {"schemaVersion": 1, "snapshotVersion": "2026.10.07.1", "counts": counts,
                "configurationSha256": digest(encrypted), "resources": list(resources.values())}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    referenced_parts = {part["path"] for record in resources.values() for part in record.get("parts", [])}
    for path in (output / "resources").glob("*.enc"):
        if path.relative_to(output).as_posix() not in referenced_parts:
            path.unlink()
    print(f"[ok] 业务快照: {counts}; 资源 {len(resources)} 个 / {sum(r['size'] for r in resources.values())} bytes")
    print(f"[key] 部署密钥单独交付: {key_file}")


def resource_content(record, directory, key):
    if record["encrypted"]:
        pieces = []
        for part in record["parts"]:
            path = (directory / part["path"]).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError("资源分片路径无效")
            content = path.read_bytes()
            if digest(content) != part["sha256"]:
                raise ValueError("资源分片校验失败")
            pieces.append(content)
        content = unseal(b"".join(pieces), key)
    else:
        path = (ROOT / record["source"]).resolve()
        if not path.is_relative_to((ROOT / "deploy").resolve()):
            raise ValueError("资源路径无效")
        content = path.read_bytes()
    if len(content) != record["size"] or digest(content) != record["sha256"]:
        raise ValueError("资源内容校验失败")
    return content


def restore_snapshot(registry, directory: Path, key_file: Path):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    key = key_bytes(key_file)
    encrypted = (directory / "configuration.enc").read_bytes()
    if digest(encrypted) != manifest["configurationSha256"]:
        raise ValueError("业务配置快照校验失败")
    payload = json.loads(unseal(encrypted, key))
    if payload["tenantId"] != registry.tenant_id or set(payload["tables"]) != set(TABLES):
        raise ValueError("目标租户或快照表清单不匹配")
    # Verify and stage all resources before changing target business data.
    with tempfile.TemporaryDirectory(prefix="linsight-snapshot-") as temporary:
        staging = Path(temporary)
        for record in manifest["resources"]:
            (staging / record["sha256"]).write_bytes(resource_content(record, directory, key))
        registry.preflight()
        for record in manifest["resources"]:
            registry.storage.fput_object("linsight-models", f"deployment-snapshot/{record['sha256']}",
                                         str(staging / record["sha256"]), content_type=record["contentType"])
    urls = {reference: f"{registry.domain}/deployment-snapshot/{sha}" for reference, sha in payload["resources"].items()}
    tables = visit(payload["tables"], lambda value: urls.get(value, value))
    # Live process/connection state must be established by the target platform's own agents.
    for row in tables["ai_task"]:
        row.update(desired_status="STOPPED", actual_status="STOPPED", active_run_id=None,
                   last_command_id=None, last_heartbeat_time=None, metrics_snapshot=None,
                   diagnostic_id=None, error_code=None, error_message=None)
    for row in tables["ai_edge_node"]:
        row.update(online_status=0, last_heartbeat_time=None, heartbeat_sequence=0, resource_snapshot=None)
    for row in tables["ai_camera"]:
        row.update(online_status=0, last_check_time=None, last_online_time=None,
                   last_error_code=None, last_error_message=None)
    backup = {"tenantId": registry.tenant_id, "jsonColumns": payload["jsonColumns"],
              "tables": {table: table_rows(registry.connection, table, registry.tenant_id)[0] for table in TABLES}}
    with registry.connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT id, config, master+0 AS master FROM infra_file_config")
        backup["fileConfigs"] = list(cursor.fetchall())
    backup_path = ROOT / "var/platform-snapshot" / (datetime.datetime.now().strftime("before-restore-%Y%m%d-%H%M%S-%f") + ".enc")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_bytes(seal(encode(backup), key))
    backup_path.chmod(0o600)
    try:
        registry.connection.begin()
        registry.configure_storage()
        with registry.connection.cursor() as cursor:
            for table in reversed(TABLES):
                cursor.execute(f"DELETE FROM `{table}` WHERE tenant_id=%s", (registry.tenant_id,))
            for table in TABLES:
                cursor.execute(f"SHOW COLUMNS FROM `{table}`")
                allowed = {column[0] for column in cursor.fetchall()}
                for row in tables[table]:
                    if not set(row) <= allowed or any(not re.fullmatch(r"[a-z_][a-z0-9_]*", name) for name in row):
                        raise ValueError(f"{table} 字段与目标数据库不兼容")
                    values = [json.dumps(value, ensure_ascii=False) if name in payload["jsonColumns"][table] and value is not None
                              else value for name, value in row.items()]
                    cursor.execute(f"INSERT INTO `{table}` ({','.join('`' + name + '`' for name in row)}) "
                                   f"VALUES ({','.join(['%s'] * len(values))})", values)
        # File metadata and business references commit together.
        for record in manifest["resources"]:
            registry.register_file({"fileName": record["sha256"], "size": record["size"], "format": "BINARY",
                                    "contentType": record["contentType"]},
                                   f"deployment-snapshot/{record['sha256']}")
        registry.connection.commit()
    except Exception:
        registry.connection.rollback()
        raise
    print(f"[ok] 已恢复业务配置与资源: {manifest['counts']}")
    print(f"[backup] 恢复前数据备份: {backup_path}")
    return backup_path


def rollback_snapshot(registry, backup_file: Path, key_file: Path):
    backup = json.loads(unseal(backup_file.read_bytes(), key_bytes(key_file)))
    if backup["tenantId"] != registry.tenant_id or set(backup["tables"]) != set(TABLES):
        raise ValueError("备份租户或表清单不匹配")
    try:
        registry.connection.begin()
        with registry.connection.cursor() as cursor:
            for table in reversed(TABLES):
                cursor.execute(f"DELETE FROM `{table}` WHERE tenant_id=%s", (registry.tenant_id,))
            for table in TABLES:
                cursor.execute(f"SHOW COLUMNS FROM `{table}`")
                allowed = {column[0] for column in cursor.fetchall()}
                for row in backup["tables"][table]:
                    if not set(row) <= allowed or any(not re.fullmatch(r"[a-z_][a-z0-9_]*", name) for name in row):
                        raise ValueError("备份字段与目标数据库不兼容")
                    values = [json.dumps(value, ensure_ascii=False) if name in backup["jsonColumns"][table] and value is not None
                              else value for name, value in row.items()]
                    cursor.execute(f"INSERT INTO `{table}` ({','.join('`'+name+'`' for name in row)}) "
                                   f"VALUES ({','.join(['%s']*len(values))})", values)
            cursor.execute("UPDATE infra_file_config SET master=0")
            for config in backup["fileConfigs"]:
                cursor.execute("UPDATE infra_file_config SET config=%s,master=%s WHERE id=%s",
                               (config["config"], config["master"], config["id"]))
        registry.connection.commit()
    except Exception:
        registry.connection.rollback()
        raise
    print("[ok] 已还原恢复前的业务配置；SQL 结构保留当前版本")
