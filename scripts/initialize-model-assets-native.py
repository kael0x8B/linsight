#!/usr/bin/env python3
"""Apply tracked migrations and register packaged weights on existing MySQL/MinIO.

Works from Windows PowerShell, Linux or macOS without Bash, Make or Docker.
The existing SQL snapshot must already be imported into the selected database.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("asset_sync", ROOT / "scripts/sync-builtin-model-assets.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class NativeRegistry(sync.LocalRegistry):
    def __init__(self, env: dict[str, str], tenant_id: int, *, create_database: bool = False) -> None:
        required = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD",
                    "MINIO_ENDPOINT", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD")
        missing = [key for key in required if not env.get(key) or env[key] == "CHANGE_ME"]
        if missing:
            raise ValueError("请在环境文件填写: " + ", ".join(missing))
        try:
            import pymysql
            from minio import Minio
            from pymysql.constants import CLIENT
        except ImportError as error:
            raise RuntimeError("缺少依赖，请运行 python -m pip install -r scripts/requirements-model-assets.txt") from error

        endpoint = env["MINIO_ENDPOINT"].rstrip("/")
        parsed = urlsplit(endpoint)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("MINIO_ENDPOINT 必须为 MinIO API 的 http(s)://主机:端口，不是控制台地址")
        super().__init__(env, tenant_id, env.get("LINSIGHT_MODEL_PUBLIC_ENDPOINT") or endpoint)
        self.database = env["MYSQL_DATABASE"]
        self.storage_endpoint = endpoint
        self.connection = pymysql.connect(
            host=env["MYSQL_HOST"], port=int(env["MYSQL_PORT"]), database=None if create_database else self.database,
            user=env["MYSQL_USER"], password=env["MYSQL_PASSWORD"], charset="utf8mb4",
            autocommit=True, client_flag=CLIENT.MULTI_STATEMENTS, connect_timeout=10,
            read_timeout=120, write_timeout=120,
            **({"ssl_ca": env["MYSQL_SSL_CA"], "ssl_verify_cert": True, "ssl_verify_identity": True}
               if env.get("MYSQL_SSL_CA") else {}),
        )
        if create_database:
            with self.connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database.replace('`', '``')}` "
                               "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            self.connection.select_db(self.database)
        self.storage = Minio(parsed.netloc, access_key=self.minio_user,
                             secret_key=self.minio_password, secure=parsed.scheme == "https",
                             region="us-east-1")

    def mysql(self, sql: str) -> str:
        rows = []
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
            while True:
                if cursor.description:
                    rows.extend(cursor.fetchall())
                if not cursor.nextset():
                    break
        return "\n".join("\t".join("NULL" if value is None else str(value) for value in row)
                         for row in rows)

    def preflight(self) -> None:
        old_index = self.mysql(
            "SELECT COUNT(*) FROM information_schema.statistics "
            f"WHERE table_schema={sync.sql_quote(self.database)} AND table_name='ai_model_version' "
            "AND index_name='uk_ai_model_version_tenant_sha_deleted';"
        )
        if old_index != "0":
            raise RuntimeError("共享资产迁移尚未执行")
        if not self.storage.bucket_exists(sync.MINIO_BUCKET):
            self.storage.make_bucket(sync.MINIO_BUCKET)

    def upload(self, artifact: dict) -> str:
        object_path = artifact.get("objectPath", f"builtin/v1/{artifact['fileName']}")
        self.storage.fput_object(sync.MINIO_BUCKET, object_path, artifact["path"],
                                 content_type="application/zip" if artifact["format"] == "ARCHIVE"
                                 else "application/octet-stream")
        return object_path

    def cleanup(self) -> None:
        # Native uploads stream from local files; no container staging directory exists.
        pass


def apply_migrations(registry: NativeRegistry, directory: Path) -> None:
    baseline = registry.mysql(
        "SELECT COUNT(*) FROM information_schema.tables "
        f"WHERE table_schema={sync.sql_quote(registry.database)} AND table_name='system_users';"
    )
    if baseline != "1":
        raise RuntimeError("目标数据库缺少基础快照，请先导入 backend/sql/mysql/linsight.sql")
    registry.mysql("""
CREATE TABLE IF NOT EXISTS infra_schema_migration (
  version varchar(32) NOT NULL,
  filename varchar(255) NOT NULL,
  checksum char(64) NOT NULL,
  applied_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (version), UNIQUE KEY uk_infra_schema_migration_filename (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
""")
    for path in sorted(directory.glob("V*.sql")):
        match = re.fullmatch(r"V(\d+)__[^']+\.sql", path.name)
        if not match:
            raise ValueError(f"迁移文件名不合法: {path.name}")
        version = match.group(1)
        # Match the repository's LF checksum even on a Windows CRLF checkout.
        content = path.read_bytes().replace(b"\r\n", b"\n")
        checksum = hashlib.sha256(content).hexdigest()
        recorded = registry.mysql(
            f"SELECT checksum FROM infra_schema_migration WHERE version={sync.sql_quote(version)};"
        )
        if recorded:
            if recorded != checksum:
                raise RuntimeError(f"迁移 {path.name} 已执行但校验和发生变化，已停止")
            print(f"[skip] {path.name}")
            continue
        print(f"[apply] {path.name}")
        registry.mysql(content.decode("utf-8"))
        registry.mysql(
            "INSERT INTO infra_schema_migration (version,filename,checksum) VALUES "
            f"({sync.sql_quote(version)},{sync.sql_quote(path.name)},{sync.sql_quote(checksum)});"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="连接现有 MySQL/MinIO，补齐 SQL 迁移并导入 15 个交付模型")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.native")
    parser.add_argument("--tenant-id", type=int, default=1)
    args = parser.parse_args()
    if not args.env_file.is_file():
        raise ValueError("缺少环境文件，请复制 deploy/model-assets/native.env.example 为 .env.native 并填写连接信息")
    env = sync.load_env(args.env_file)
    registry = NativeRegistry(env, args.tenant_id)
    try:
        print(f"[target] MySQL {env['MYSQL_HOST']}:{env['MYSQL_PORT']}/{registry.database}, tenant={args.tenant_id}")
        # Validate object storage credentials before any SQL migration is applied.
        registry.storage.bucket_exists(sync.MINIO_BUCKET)
        apply_migrations(registry, ROOT / "backend/sql/mysql/migrations/ai-video")
        return sync.main(argparse.Namespace(
            register=True, catalog=sync.DEFAULT_CATALOG, manifests=sync.DEFAULT_MANIFESTS,
            output=sync.DEFAULT_OUTPUT, asset_source=sync.DEFAULT_ASSET_SOURCE,
            env_file=args.env_file, tenant_id=args.tenant_id, public_endpoint=None,
        ), registry=registry)
    finally:
        registry.connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Client errors omit SQL payloads and configuration values from console output.
        print(f"[error] {error}", file=sys.stderr)
        raise SystemExit(1)
