#!/usr/bin/env python3
"""Exercise native TCP/S3 initialization twice using disposable test resources."""

import importlib.util
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pymysql


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("asset_sync", ROOT / "scripts/sync-builtin-model-assets.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, **kwargs)


def main():
    env = sync.load_env(ROOT / ".env")
    suffix = uuid.uuid4().hex[:12]
    database = f"linsight_nativecheck_{suffix}"
    container = f"linsight-nativecheck-{suffix}"
    connection = pymysql.connect(host="127.0.0.1", port=int(env.get("MYSQL_PORT", "23306")),
                                 user="root", password=env["MYSQL_ROOT_PASSWORD"], autocommit=True)
    try:
        with tempfile.TemporaryDirectory(prefix="linsight-nativecheck-") as temp:
            workspace = Path(temp)
            (workspace / "scripts").mkdir()
            for name in ("sync-builtin-model-assets.py", "initialize-model-assets-native.py"):
                shutil.copyfile(ROOT / "scripts" / name, workspace / "scripts" / name)
            (workspace / "deploy").mkdir()
            (workspace / "deploy/model-assets").symlink_to(ROOT / "deploy/model-assets", target_is_directory=True)
            # Verify the committed migration set, independent of other ongoing workspace changes.
            migrations = workspace / "backend/sql/mysql/migrations/ai-video"
            migrations.mkdir(parents=True)
            paths = [path for path in run(
                ["git", "ls-tree", "-r", "--name-only", "HEAD", "backend/sql/mysql/migrations/ai-video"],
                cwd=ROOT, text=True).stdout.splitlines()
                if Path(path).name.startswith("V") and path.endswith(".sql")]
            for path in paths:
                (migrations / Path(path).name).write_bytes(run(["git", "show", f"HEAD:{path}"], cwd=ROOT).stdout)
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            snapshot = run(["git", "show", "HEAD:backend/sql/mysql/linsight.sql"], cwd=ROOT).stdout
            run(["docker", "exec", "-i", "-e", f"MYSQL_PWD={env['MYSQL_ROOT_PASSWORD']}",
                 "linsight-mysql", "mysql", "--default-character-set=utf8mb4", "-uroot", database], input=snapshot)
            secret = secrets.token_hex(24)
            config = workspace / "test.env"
            config.write_text(f"MINIO_ROOT_USER=native-check\nMINIO_ROOT_PASSWORD={secret}\n", encoding="utf-8")
            config.chmod(0o600)
            run(["docker", "run", "--rm", "-d", "--name", container, "--env-file", str(config),
                 "-p", "127.0.0.1::9000", "minio/minio:RELEASE.2025-09-07T16-13-09Z", "server", "/data"])
            port = run(["docker", "port", container, "9000/tcp"], text=True).stdout.strip().rsplit(":", 1)[1]
            for _ in range(30):
                probe = subprocess.run(["docker", "exec", container, "curl", "-sf",
                                        "http://127.0.0.1:9000/minio/health/live"], capture_output=True)
                if probe.returncode == 0:
                    break
                time.sleep(1)
            config.write_text(config.read_text() +
                              f"MYSQL_HOST=127.0.0.1\nMYSQL_PORT={env.get('MYSQL_PORT', '23306')}\n"
                              f"MYSQL_DATABASE={database}\nMYSQL_USER=root\n"
                              f"MYSQL_PASSWORD={env['MYSQL_ROOT_PASSWORD']}\nMINIO_ENDPOINT=http://127.0.0.1:{port}\n",
                              encoding="utf-8")
            for attempt in (1, 2):
                result = subprocess.run([sys.executable, str(workspace / "scripts/initialize-model-assets-native.py"),
                                         "--env-file", str(config)], capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*),SUM(publish_status='PUBLISHED'),SUM(execution_status='READY') "
                                   f"FROM {database}.ai_model_version WHERE deleted=0")
                    assert tuple(int(value) for value in cursor.fetchone()) == (15, 15, 0)
                    cursor.execute(f"SELECT COUNT(*) FROM {database}.infra_schema_migration")
                    assert cursor.fetchone()[0] == len(paths)
                    cursor.execute(f"SELECT COUNT(*) FROM {database}.ai_model WHERE deleted=0 AND code IN "
                                   "('smoking-phone-detection','general-ocr','general-segmentation')")
                    assert cursor.fetchone()[0] == 0
                print(f"[pass {attempt}] native TCP/S3: migrated={len(paths)} versions=15 published=15 ready=0")
            from minio import Minio
            storage = Minio(f"127.0.0.1:{port}", "native-check", secret, secure=False)
            catalog = json.loads((ROOT / "deploy/model-assets/catalog.json").read_text(encoding="utf-8"))
            for asset in catalog["assets"]:
                actual = storage.stat_object("linsight-models", f"builtin/v1/{asset['fileName']}")
                assert actual.size == (ROOT / "deploy/model-assets/files" / asset["fileName"]).stat().st_size
            print("[ok] Native initialization, repeated import, retired placeholders and uploaded file sizes verified.")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {database}")
        connection.close()
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


if __name__ == "__main__":
    main()
