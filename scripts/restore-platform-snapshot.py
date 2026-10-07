#!/usr/bin/env python3
"""Restore the delivered local configuration snapshot into the configured target environment."""
import argparse
import importlib.util
import json
from pathlib import Path
from urllib.parse import quote

from platform_snapshot import DIRECTORY, ROOT, load_backup, load_snapshot, native_module, restore_snapshot, rollback_snapshot


def write_backend_configuration(env):
    url = (f"jdbc:mysql://{env['MYSQL_HOST']}:{int(env['MYSQL_PORT'])}/{quote(env['MYSQL_DATABASE'])}"
           "?useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&nullCatalogMeansCurrent=true&rewriteBatchedStatements=true")
    datasource = {"url": env.get("DB_URL") or url, "username": env["MYSQL_USER"], "password": env["MYSQL_PASSWORD"]}
    config = {"spring": {"datasource": {"dynamic": {"datasource": {"master": datasource, "slave": datasource}}},
                         "data": {"redis": {"host": env.get("REDIS_HOST", "127.0.0.1"),
                                            "port": int(env.get("REDIS_PORT", "6379")),
                                            "database": int(env.get("REDIS_DATABASE", "0")),
                                            "password": env.get("REDIS_PASSWORD", "")}}}}
    if not env.get("REDIS_PASSWORD"):
        # Redisson distinguishes an absent password from an empty AUTH password.
        del config["spring"]["data"]["redis"]["password"]
    path = ROOT / "var/application-native-local.yaml"
    # JSON is valid YAML and safely quotes passwords, backslashes and connection URLs.
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    print(f"[ok] IDEA 后端数据库/Redis 配置已写入: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.native")
    parser.add_argument("--key-file", type=Path, help="仅用于回退旧版 .enc 备份；当前恢复不需要")
    parser.add_argument("--rollback-backup", type=Path, help="还原指定的 before-restore 备份")
    args = parser.parse_args()
    # Validate the package before opening or migrating the target database.
    if args.rollback_backup:
        load_backup(args.rollback_backup, args.key_file)
    else:
        load_snapshot(DIRECTORY)
    native = native_module()
    env = native.sync.load_env(args.env_file)
    registry = native.NativeRegistry(env, 1, create_database=True)
    try:
        if args.rollback_backup:
            rollback_snapshot(registry, args.rollback_backup, args.key_file)
            return
        print(f"[target] {registry.database}; 将恢复交付快照，已有业务配置会先备份")
        exists = registry.mysql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='system_users';")
        if exists == "0":
            registry.mysql((ROOT / "backend/sql/mysql/linsight.sql").read_text(encoding="utf-8"))
        native.apply_migrations(registry, ROOT / "backend/sql/mysql/migrations/ai-video")
        restore_snapshot(registry, DIRECTORY)
        write_backend_configuration(env)
        spec = importlib.util.spec_from_file_location("publisher", ROOT / "scripts/prepare-application-release.py")
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        publisher.prepare()
    finally:
        registry.connection.close()


if __name__ == "__main__":
    main()
