import hashlib
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "native_asset_sync", Path(__file__).parents[1] / "initialize-model-assets-native.py",
)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class MigrationRegistry:
    database = "linsight"

    def __init__(self, checksum=""):
        self.checksum = checksum
        self.executed = []

    def mysql(self, sql):
        self.executed.append(sql)
        if "information_schema.tables" in sql:
            return "1"
        if "SELECT checksum" in sql:
            return self.checksum
        return ""


def test_windows_crlf_matches_existing_lf_migration(tmp_path):
    content = b"SELECT 1;\n"
    (tmp_path / "V202610060001__sample.sql").write_bytes(content.replace(b"\n", b"\r\n"))
    registry = MigrationRegistry(hashlib.sha256(content).hexdigest())
    native.apply_migrations(registry, tmp_path)
    assert "SELECT 1;\n" not in registry.executed
    assert not any("INSERT INTO infra_schema_migration" in sql for sql in registry.executed)


def test_changed_recorded_migration_stops_before_execution(tmp_path):
    (tmp_path / "V202610060001__sample.sql").write_text("SELECT 1;\n")
    registry = MigrationRegistry("0" * 64)
    with pytest.raises(RuntimeError, match="校验和发生变化"):
        native.apply_migrations(registry, tmp_path)
    assert "SELECT 1;\n" not in registry.executed


def test_failed_migration_is_not_recorded(tmp_path):
    (tmp_path / "V202610060001__sample.sql").write_text("INVALID SQL;\n")
    registry = MigrationRegistry()
    original = registry.mysql

    def execute(sql):
        if sql == "INVALID SQL;\n":
            raise RuntimeError("migration failed")
        return original(sql)

    registry.mysql = execute
    with pytest.raises(RuntimeError, match="migration failed"):
        native.apply_migrations(registry, tmp_path)
    assert not any("INSERT INTO infra_schema_migration" in sql for sql in registry.executed)


def test_unconfigured_connections_stop_before_network_access():
    with pytest.raises(ValueError, match="MYSQL_HOST"):
        native.NativeRegistry({}, 1)
