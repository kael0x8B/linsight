#!/usr/bin/env python3
"""Capture local business configuration and required resources for keyless Git delivery."""
from platform_snapshot import export_snapshot, native_module

native = native_module()
env = native.sync.load_env(native.ROOT / ".env")
env.update(MYSQL_HOST="127.0.0.1", MYSQL_DATABASE="linsight", MYSQL_USER="root",
           MYSQL_PASSWORD=env["MYSQL_ROOT_PASSWORD"],
           MINIO_ENDPOINT=f"http://127.0.0.1:{env.get('MINIO_API_PORT', '29000')}")
registry = native.NativeRegistry(env, 1)
try:
    export_snapshot(registry)
finally:
    registry.connection.close()
