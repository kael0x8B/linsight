"""Publisher verifies its output using the device verifier before reporting success."""

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from edge_agent.app.upgrade import system as system_module
from edge_agent.app.upgrade.bundle import sha256, verify
from edge_agent.app.upgrade.system import LinuxSystem

spec = importlib.util.spec_from_file_location(
    "box_builder", Path(__file__).resolve().parents[2] / "scripts/build-box-release.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    for name in (
        "pyproject.toml",
        "ai_runtime/app/main.py",
        "edge_agent/app/main.py",
        "edge_agent/app/upgrade/bootstrap.py",
    ):
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test fixture\n")
    console = runtime / "gateway-console"
    console.mkdir()
    (console / "manifest.json").write_text(json.dumps({"artifact": {"fileName": "console.zip"}}))
    (console / "console.zip").write_bytes(b"console")
    # Console artifact itself has dedicated validation tests; keep this builder fixture minimal.
    monkeypatch.setattr("ai_runtime.app.gateway.console_artifact.install_artifact", lambda *_: None)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "test.whl").write_bytes(b"wheel")
    (wheels / "manifest.json").write_text(
        json.dumps(
            {
                "architecture": "aarch64",
                "pythonVersion": "3.12",
                "pyprojectSha256": sha256(runtime / "pyproject.toml"),
                "files": {"test.whl": sha256(wheels / "test.whl")},
            }
        )
    )
    python = tmp_path / "python.tar.gz"
    python.write_bytes(b"python")
    key = tmp_path / "private.pem"
    key.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
    )
    output = tmp_path / "out"
    return argparse.Namespace(
        runtime=runtime,
        wheels=wheels,
        python=python,
        python_sha256=sha256(python),
        signing_key=key,
        key_id="test",
        version="1.0.0",
        arch="aarch64",
        devices=["generic"],
        notes=None,
        min_glibc="2.34",
        backward_compatible=True,
        output=output,
        result_file=tmp_path / "result.json",
    )


def test_result_matches_verified_bundle_and_exports_only_public_key(inputs, tmp_path):
    builder.build(inputs)
    result = json.loads(inputs.result_file.read_text())
    bundle = Path(result["package"])
    trust = tmp_path / "trust"
    trust.mkdir()
    (trust / "test.pem").write_bytes((inputs.output / "release-public.pem").read_bytes())
    assert verify(bundle, trust)["version"] == "1.0.0"
    assert result["sha256"] == sha256(bundle)
    assert result["size"] == bundle.stat().st_size
    assert len(result["sourceSha256"]) == 64
    assert b"PRIVATE" not in (inputs.output / "release-public.pem").read_bytes()
    with pytest.raises(ValueError, match="已存在"):
        builder.build(inputs)
    assert result["sha256"] == sha256(bundle)


def test_tampered_dependency_is_not_published(inputs):
    (inputs.wheels / "test.whl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="已被修改"):
        builder.build(inputs)
    assert not inputs.result_file.exists()


def test_one_signed_bundle_passes_both_rk_hosts_and_rejects_incompatible_hosts(
    inputs, tmp_path, monkeypatch
):
    inputs.devices = ["rk3566", "rk3568", "rk3588"]
    builder.build(inputs)
    result = json.loads(inputs.result_file.read_text())
    trust = tmp_path / "trust"
    trust.mkdir()
    (trust / "test.pem").write_bytes((inputs.output / "release-public.pem").read_bytes())
    manifest = verify(Path(result["package"]), trust)
    assert manifest["devices"] == inputs.devices
    assert len(list(inputs.output.glob("*.lup"))) == 1

    host = LinuxSystem(tmp_path / "host.log")
    commands = []
    monkeypatch.setattr(host, "run", lambda args, **_: commands.append(args))
    monkeypatch.setattr(system_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(system_module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(system_module.platform, "libc_ver", lambda: ("glibc", "2.36"))
    monkeypatch.setattr(
        system_module.shutil, "disk_usage", lambda _: SimpleNamespace(free=10 * 1024**3)
    )
    monkeypatch.setattr(system_module.shutil, "which", lambda name: "/usr/bin/" + name)
    hardware = [b"rockchip,rk3566\0"]
    original_exists, original_read = Path.exists, Path.read_bytes
    monkeypatch.setattr(
        Path,
        "exists",
        lambda p: True if str(p) == "/proc/device-tree/compatible" else original_exists(p),
    )
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda p: hardware[0] if str(p) == "/proc/device-tree/compatible" else original_read(p),
    )
    for soc in ("rk3566", "rk3568", "rk3588"):
        hardware[0] = f"rockchip,{soc}\0".encode()
        host.preflight(manifest, result["size"], tmp_path)
    assert len(commands) == 3
    hardware[0] = b"rockchip,rk3399\0"
    with pytest.raises(ValueError, match="型号"):
        host.preflight(manifest, result["size"], tmp_path)
    hardware[0] = b"rockchip,rk3588\0"
    monkeypatch.setattr(system_module.platform, "libc_ver", lambda: ("glibc", "2.31"))
    with pytest.raises(ValueError, match="运行库"):
        host.preflight(manifest, result["size"], tmp_path)
    monkeypatch.setattr(system_module.platform, "machine", lambda: "x86_64")
    with pytest.raises(ValueError, match="CPU"):
        host.preflight(manifest, result["size"], tmp_path)
    assert len(commands) == 3


def test_source_change_while_archiving_is_not_published(inputs, monkeypatch):
    original = builder.canonical
    changed = False

    def mutate(manifest):
        nonlocal changed
        if not changed:
            changed = True
            (inputs.runtime / "ai_runtime/app/main.py").write_text("changed contents")
        return original(manifest)

    monkeypatch.setattr(builder, "canonical", mutate)
    with pytest.raises(ValueError):
        builder.build(inputs)
    assert not list(inputs.output.glob("*.lup"))
    assert not inputs.result_file.exists()
