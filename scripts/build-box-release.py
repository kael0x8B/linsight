#!/usr/bin/env python3
"""Build a signed offline application bundle and a trusted first-migration zipapp."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)
from edge_agent.app.upgrade.bundle import VERSION, canonical, sha256, verify


def build(args):
    if not VERSION.fullmatch(args.version) or not VERSION.fullmatch(args.key_id):
        raise ValueError("版本或密钥编号无效")
    if not args.backward_compatible:
        raise ValueError("发布者必须确认新版本保持已有配置、模型和事件数据格式向后兼容")
    key = load_pem_private_key(args.signing_key.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("需要 Ed25519 发布私钥")
    runtime = args.runtime.resolve()
    wheel_manifest = json.loads((args.wheels / "manifest.json").read_text())
    if (
        wheel_manifest.get("architecture") != args.arch
        or wheel_manifest.get("pythonVersion") != "3.12"
        or wheel_manifest.get("pyprojectSha256") != sha256(runtime / "pyproject.toml")
    ):
        raise ValueError("离线依赖与源码、架构或 Python 版本不匹配")
    from ai_runtime.app.gateway.console_artifact import install_artifact

    with tempfile.TemporaryDirectory() as temporary:
        install_artifact(runtime / "gateway-console", Path(temporary) / "console")
    files = {
        "payload/python.tar.gz": args.python.resolve(),
        "payload/runtime/pyproject.toml": runtime / "pyproject.toml",
    }
    for directory in (
        "ai_runtime",
        "edge_agent",
        "algorithm_packages",
        "algorithm_presets",
    ):
        for path in sorted((runtime / directory).rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            ):
                if path.is_symlink():
                    raise ValueError("Runtime 源码包含链接")
                files["payload/runtime/" + path.relative_to(runtime).as_posix()] = path
    console = json.loads((runtime / "gateway-console/manifest.json").read_text())
    for name in ("manifest.json", console["artifact"]["fileName"]):
        files["payload/runtime/gateway-console/" + name] = (
            runtime / "gateway-console" / name
        )
    for name, digest in wheel_manifest["files"].items():
        if Path(name).name != name or not name.endswith(".whl"):
            raise ValueError("离线依赖清单路径异常")
        path = args.wheels / name
        if sha256(path) != digest:
            raise ValueError("离线依赖文件已被修改：" + name)
        files["payload/wheels/" + name] = path
    if sha256(args.python) != args.python_sha256:
        raise ValueError("独立 Python 与固定发布摘要不一致")
    manifest = {
        "schemaVersion": 1,
        "artifactType": "linsight-box",
        "version": args.version,
        "keyId": args.key_id,
        "architecture": args.arch,
        "devices": args.devices,
        "minGlibc": args.min_glibc,
        "pythonVersion": "3.12",
        "dataSchema": 1,
        "minUpdater": 1,
        "notes": args.notes.read_text() if args.notes else "",
        "files": {
            name: {"size": path.stat().st_size, "sha256": sha256(path)}
            for name, path in sorted(files.items())
        },
    }
    if (
        sum(item["size"] for item in manifest["files"].values())
        > 2 * 1024**3 - 16 * 1024**2
    ):
        raise ValueError("升级包超过 2 GiB 大小限制")
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / f"linsight-box-{args.version}-{args.arch}.lup"
    if target.exists():
        raise ValueError("发布文件已存在，不覆盖已发布版本")
    # Deterministic ZIP metadata; nested wheels are already compressed.
    with tempfile.NamedTemporaryFile(
        prefix=target.name + ".", suffix=".partial", dir=args.output, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in (
                ("manifest.json", canonical(manifest)),
                ("manifest.sig", key.sign(canonical(manifest))),
            ):
                archive.writestr(zipfile.ZipInfo(name), data)
            for name, path in sorted(files.items()):
                with (
                    archive.open(
                        zipfile.ZipInfo(name), "w", force_zip64=True
                    ) as output,
                    path.open("rb") as source,
                ):
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
        os.link(
            temporary, target
        )  # Atomic no-clobber publication, including concurrent CLI builders.
    finally:
        temporary.unlink(missing_ok=True)
    public_key = key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    with tempfile.TemporaryDirectory() as trust:
        (Path(trust) / f"{args.key_id}.pem").write_bytes(public_key)
        try:
            verify(target, Path(trust))
        except Exception:
            target.unlink(missing_ok=True)
            raise
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory)
        package = source / "edge_agent/app/upgrade"
        package.mkdir(parents=True)
        for parent in (package, package.parent, package.parent.parent):
            (parent / "__init__.py").write_text("")
        # Bootstrap and runtime must originate from the same verified source snapshot.
        prefix = "payload/runtime/edge_agent/app/upgrade/"
        with zipfile.ZipFile(target) as archive:
            for name in manifest["files"]:
                if (
                    name.startswith(prefix)
                    and name.removeprefix(prefix).endswith(".py")
                    and "/" not in name.removeprefix(prefix)
                ):
                    (package / name.removeprefix(prefix)).write_bytes(
                        archive.read(name)
                    )
        zipapp.create_archive(
            source,
            args.output / "linsight-bootstrap.pyz",
            main="edge_agent.app.upgrade.bootstrap:main",
        )
    (args.output / "release-public.pem").write_bytes(public_key)
    result = {
        "package": str(target),
        "sha256": sha256(target),
        "bootstrapSha256": sha256(args.output / "linsight-bootstrap.pyz"),
        "fileName": target.name,
        "size": target.stat().st_size,
        "sourceSha256": hashlib.sha256(
            canonical(
                {
                    name: entry
                    for name, entry in manifest["files"].items()
                    if name.startswith("payload/runtime/")
                }
            )
        ).hexdigest(),
        "keyId": args.key_id,
    }
    if getattr(args, "result_file", None):
        args.result_file.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=ROOT / "runtime")
    parser.add_argument("--version", required=True)
    parser.add_argument("--arch", choices=("aarch64", "x86_64"), required=True)
    parser.add_argument(
        "--devices",
        nargs="+",
        choices=("rk3566", "rk3568", "rk3588", "generic"),
        required=True,
    )
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--python-sha256", required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--min-glibc", default="2.34")
    parser.add_argument("--backward-compatible", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result-file", type=Path)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
