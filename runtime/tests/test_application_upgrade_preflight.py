from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from edge_agent.app.upgrade import bootstrap as bootstrap_module
from edge_agent.app.upgrade import cli as cli_module
from edge_agent.app.upgrade import system as system_module
from edge_agent.app.upgrade.system import LinuxSystem


@pytest.mark.parametrize("command", ["check", "install"])
def test_cli_check_does_not_submit_install(command, tmp_path, monkeypatch):
    package = tmp_path / "test.lup"
    package.write_bytes(b"test")
    actions = []
    job = {}

    def request(action, payload=None):
        actions.append(action)
        if action == "upload.begin":
            job.update(id=payload["id"], phase="READY")
            return {"offset": 0}
        if action == "upload.chunk":
            return {"offset": package.stat().st_size}
        if action == "install":
            job["phase"] = "SUCCEEDED"
        if action == "status":
            return {"job": job.copy()}
        return {"accepted": True}

    monkeypatch.setattr(cli_module, "request", request)
    monkeypatch.setattr("sys.argv", ["linsight-upgrade", command, str(package)])
    cli_module.main()
    assert "upload.finish" in actions
    assert actions.count("install") == (1 if command == "install" else 0)
    assert job["phase"] == ("SUCCEEDED" if command == "install" else "READY")


def test_architecture_and_space_fail_before_service_command(tmp_path, monkeypatch):
    host = LinuxSystem(tmp_path / "log")
    manifest = {
        "architecture": "aarch64",
        "minGlibc": "2.34",
        "devices": ["generic"],
        "files": {"app": {"size": 100}},
    }
    monkeypatch.setattr(system_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(system_module.platform, "machine", lambda: "x86_64")
    with pytest.raises(ValueError, match="CPU"):
        host.preflight(manifest, 100, tmp_path)
    monkeypatch.setattr(system_module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(system_module.platform, "libc_ver", lambda: ("glibc", "2.36"))
    monkeypatch.setattr(system_module.shutil, "disk_usage", lambda _: SimpleNamespace(free=10))
    with pytest.raises(ValueError, match="空间"):
        host.preflight(manifest, 100, tmp_path)
    assert not host.log.exists()


@pytest.fixture
def migration(tmp_path, monkeypatch):
    root, state = tmp_path / "app", tmp_path / "state"
    (root / "venv/bin").mkdir(parents=True)
    (root / "venv/bin/python").touch()
    credential = tmp_path / "credential.json"
    credential.write_text("synthetic identity")
    bundle, key = tmp_path / "app.lup", tmp_path / "key.pem"
    bundle.write_bytes(b"placeholder")
    key.write_bytes(b"placeholder")
    env = {
        "LINSIGHT_RUNTIME_DATA_ROOT": str(tmp_path / "data"),
        "LINSIGHT_AGENT_RUNTIME_DATA_ROOT": str(tmp_path / "data"),
        "LINSIGHT_AGENT_CREDENTIAL_FILE": str(credential),
    }
    monkeypatch.setattr(bootstrap_module, "ROOT", root)
    monkeypatch.setattr(bootstrap_module, "STATE", state)
    monkeypatch.setattr(bootstrap_module, "BASE", tmp_path / "installer")
    monkeypatch.setattr(bootstrap_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap_module, "exclusive", lambda _: nullcontext())
    monkeypatch.setattr(
        bootstrap_module, "show", lambda _, p: "root" if p == "User" else "/opt/linsight/runtime"
    )
    monkeypatch.setattr(bootstrap_module.subprocess, "check_output", lambda *a, **k: b"")
    monkeypatch.setattr(LinuxSystem, "_environment", lambda *_: env)
    monkeypatch.setattr(LinuxSystem, "preflight", lambda *_: None)
    monkeypatch.setattr(LinuxSystem, "capture", lambda *_: {})
    monkeypatch.setattr(bootstrap_module, "verify", lambda *_: {"version": "test"})
    return bundle, key, state, env


def test_bootstrap_check_does_not_install_or_replace_legacy(migration):
    bundle, key, state, _ = migration
    assert bootstrap_module.bootstrap(bundle, key, "test", check_only=True)["ready"]
    assert not (state / "config.json").exists()
    assert not (bootstrap_module.ROOT / "current").exists()
    assert not bootstrap_module.BASE.exists()


def test_bootstrap_rejects_relative_identity_or_unconfirmed_old_deployment(migration, monkeypatch):
    bundle, key, _, env = migration
    env["LINSIGHT_AGENT_CREDENTIAL_FILE"] = "./var/credential.json"
    with pytest.raises(ValueError, match="绝对路径"):
        bootstrap_module.bootstrap(bundle, key, "test", check_only=True)
    monkeypatch.setattr(
        bootstrap_module.subprocess, "check_output", lambda *a, **k: b"pending.timer"
    )
    with pytest.raises(ValueError, match="计时器"):
        bootstrap_module.bootstrap(bundle, key, "test", check_only=True)
