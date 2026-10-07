#!/usr/bin/env python3
"""Restore the delivered snapshot twice into isolated MySQL/MinIO; verify real resources."""
import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pymysql
from cryptography.exceptions import InvalidTag

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import platform_snapshot as snapshot


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, default=snapshot.KEY_FILE)
    parser.add_argument("--keep", action="store_true", help="保留隔离环境供 API/浏览器验证；连接信息写入忽略目录")
    args = parser.parse_args()
    native = snapshot.native_module()
    env = native.sync.load_env(ROOT / ".env")
    suffix = uuid.uuid4().hex[:10]
    database, container = f"linsight_snapshotcheck_{suffix}", f"linsight-snapshotcheck-{suffix}"
    workspace = ROOT / "var/platform-snapshot" / suffix
    workspace.mkdir(parents=True)
    connection = pymysql.connect(host="127.0.0.1", port=int(env.get("MYSQL_PORT", "23306")),
                                 user="root", password=env["MYSQL_ROOT_PASSWORD"], autocommit=True)
    registry = None
    succeeded = False
    try:
        config = workspace / "test.env"
        secret = secrets.token_hex(24)
        config.write_text(f"MINIO_ROOT_USER=snapshot-check\nMINIO_ROOT_PASSWORD={secret}\n", encoding="utf-8")
        config.chmod(0o600)
        run(["docker", "run", "--rm", "-d", "--name", container, "--env-file", str(config),
             "-p", "127.0.0.1::9000", "minio/minio:RELEASE.2025-09-07T16-13-09Z", "server", "/data"])
        port = run(["docker", "port", container, "9000/tcp"], text=True).stdout.strip().rsplit(":", 1)[1]
        for _ in range(30):
            if subprocess.run(["docker", "exec", container, "curl", "-sf", "http://127.0.0.1:9000/minio/health/live"], capture_output=True).returncode == 0:
                break
            time.sleep(1)
        config.write_text(config.read_text(encoding="utf-8") +
                          f"MYSQL_HOST=127.0.0.1\nMYSQL_PORT={env.get('MYSQL_PORT','23306')}\n"
                          f"MYSQL_DATABASE={database}\nMYSQL_USER=root\nMYSQL_PASSWORD={env['MYSQL_ROOT_PASSWORD']}\n"
                          f"MINIO_ENDPOINT=http://127.0.0.1:{port}\nREDIS_PORT={env.get('REDIS_PORT','26379')}\nREDIS_DATABASE=13\n", encoding="utf-8")
        registry = native.NativeRegistry(native.sync.load_env(config), 1, create_database=True)
        registry.mysql((ROOT / "backend/sql/mysql/linsight.sql").read_text(encoding="utf-8"))
        native.apply_migrations(registry, ROOT / "backend/sql/mysql/migrations/ai-video")
        manifest = json.loads((snapshot.DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
        baseline_count = registry.mysql("SELECT COUNT(*) FROM ai_algorithm WHERE status=0 AND deleted=0")
        first_backup = None
        for attempt in (1, 2):
            backup = snapshot.restore_snapshot(registry, snapshot.DIRECTORY, args.key_file)
            first_backup = first_backup or backup
            assert registry.mysql("SELECT COUNT(*), COUNT(DISTINCT name) FROM ai_algorithm WHERE status=0 AND deleted=0") == "27\t24"
            assert registry.mysql("SELECT COUNT(*) FROM ai_rule WHERE deleted=0") == "18"
            assert registry.mysql("SELECT COUNT(*) FROM ai_task WHERE deleted=0") == "9"
            assert registry.mysql("SELECT COUNT(*) FROM ai_task WHERE desired_status!='STOPPED' OR actual_status!='STOPPED'") == "0"
            assert registry.mysql("SELECT COUNT(*) FROM ai_edge_node WHERE online_status!=0") == "0"
            ready = registry.mysql("SELECT COUNT(*) FROM ai_model m JOIN ai_model_version v ON v.model_id=m.id "
                                   "WHERE m.deleted=0 AND m.status=0 AND v.deleted=0 AND v.publish_status='PUBLISHED' AND v.execution_status='READY'")
            assert int(ready) >= 15
            for table, field, owner in (("ai_model", "current_version_id", "ai_model_version"),
                                       ("ai_algorithm", "current_pipeline_version_id", "ai_pipeline_version"),
                                       ("ai_rule", "current_version_id", "ai_rule_version"),
                                       ("ai_task", "pipeline_version_id", "ai_pipeline_version"),
                                       ("ai_task", "rule_version_id", "ai_rule_version"),
                                       ("ai_task", "model_version_id", "ai_model_version")):
                assert registry.mysql(f"SELECT COUNT(*) FROM {table} a LEFT JOIN {owner} b ON a.{field}=b.id "
                                      f"WHERE a.deleted=0 AND a.{field} IS NOT NULL AND b.id IS NULL") == "0", (table, field)
            for table, field in (("ai_model_version", "artifact_ref"), ("ai_pipeline_version", "package_artifact_ref")):
                with registry.connection.cursor() as cursor:
                    cursor.execute(f"SELECT `{field}` FROM `{table}` WHERE `{field}` IS NOT NULL")
                    assert all(row[0].startswith(registry.domain + "/deployment-snapshot/") for row in cursor.fetchall())
            print(f"[pass {attempt}] 24 个算法、18 条规则、9 个任务、{ready} 个可部署版本；关联完整，运行状态已重置")
        for item in manifest["resources"]:
            response = registry.storage.get_object("linsight-models", "deployment-snapshot/" + item["sha256"])
            try:
                content = response.read()
            finally:
                response.close(); response.release_conn()
            assert len(content) == item["size"] and hashlib.sha256(content).hexdigest() == item["sha256"]
        wrong = workspace / "wrong.key"
        wrong.write_text(base64.b64encode(os.urandom(32)).decode("ascii"), encoding="ascii")
        try:
            snapshot.restore_snapshot(registry, snapshot.DIRECTORY, wrong)
        except InvalidTag:
            pass
        else:
            raise AssertionError("Wrong key must fail")
        assert registry.mysql("SELECT COUNT(*) FROM ai_task WHERE deleted=0") == "9"
        wrong.unlink()
        snapshot.rollback_snapshot(registry, first_backup, args.key_file)
        assert registry.mysql("SELECT COUNT(*) FROM ai_algorithm WHERE status=0 AND deleted=0") == baseline_count
        snapshot.restore_snapshot(registry, snapshot.DIRECTORY, args.key_file)
        print(f"[ok] {len(manifest['resources'])} 个资源逐字节 SHA256 一致；错误密钥未改变业务数据")
        (workspace / "environment.json").write_text(json.dumps({"database": database, "container": container, "envFile": str(config)}), encoding="utf-8")
        succeeded = True
        if args.keep:
            print(f"[kept] {workspace}")
    finally:
        if registry:
            registry.connection.close()
        if not (args.keep and succeeded):
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        connection.close()


if __name__ == "__main__":
    main()
