"""Signed, bounded application bundles. The trust anchor never comes from the bundle."""

import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

MAX_BUNDLE = 2 * 1024**3
MAX_EXPANDED = 8 * 1024**3
MAX_FILES = 30000
CHUNK_SIZE = 256 * 1024
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("升级清单包含重复字段")
        result[key] = value
    return result


def read_json(content: bytes) -> dict:
    value = json.loads(content, object_pairs_hook=_unique)
    if not isinstance(value, dict):
        raise ValueError("升级清单格式错误")
    return value


def safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or "\\" in name
        or "\x00" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
        or not name.startswith("payload/")
    ):
        raise ValueError("升级包包含不安全的路径")


def verify(path: Path, keys: Path, destination: Path | None = None) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BUNDLE:
        raise ValueError("升级包大小或文件类型不符合要求")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(entries) > MAX_FILES or len(set(names)) != len(names):
            raise ValueError("升级包文件数量超限或存在重复路径")
        if sum(item.file_size for item in entries) > MAX_EXPANDED:
            raise ValueError("升级包解压大小超限")
        for name, limit in (("manifest.json", 6 * 1024**2), ("manifest.sig", 64)):
            if name not in names or archive.getinfo(name).file_size > limit:
                raise ValueError("升级包缺少有效清单或签名")
        manifest = read_json(archive.read("manifest.json"))
        key_id = manifest.get("keyId", "")
        if not isinstance(key_id, str) or not VERSION.fullmatch(key_id):
            raise ValueError("发布密钥编号无效")
        try:
            key = load_pem_public_key((keys / f"{key_id}.pem").read_bytes())
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError("发布公钥类型错误")
            key.verify(archive.read("manifest.sig"), canonical(manifest))
        except (OSError, InvalidSignature) as error:
            raise ValueError("发布签名不可信或升级包已被修改") from error
        required = {
            "schemaVersion",
            "artifactType",
            "version",
            "keyId",
            "architecture",
            "devices",
            "minGlibc",
            "dataSchema",
            "minUpdater",
            "pythonVersion",
            "files",
            "notes",
        }
        if (
            set(manifest) != required
            or manifest["schemaVersion"] != 1
            or manifest["artifactType"] != "linsight-box"
            or manifest["dataSchema"] != 1
            or manifest["minUpdater"] != 1
            or manifest["pythonVersion"] != "3.12"
            or manifest["architecture"] not in {"aarch64", "x86_64"}
            or not isinstance(manifest["version"], str)
            or not VERSION.fullmatch(manifest["version"])
            or not isinstance(manifest["notes"], str)
            or len(manifest["notes"]) > 8000
            or not re.fullmatch(r"[0-9]+\.[0-9]+", str(manifest["minGlibc"]))
            or not isinstance(manifest["devices"], list)
            or not manifest["devices"]
            or any(x not in {"rk3566", "rk3568", "rk3588", "generic"} for x in manifest["devices"])
        ):
            raise ValueError("不支持的升级清单、数据格式或安装器版本")
        inventory = manifest["files"]
        if not isinstance(inventory, dict) or set(names) != set(inventory) | {
            "manifest.json",
            "manifest.sig",
        }:
            raise ValueError("升级包内容与已签名清单不一致")
        required_files = {
            "payload/python.tar.gz",
            "payload/runtime/pyproject.toml",
            "payload/runtime/ai_runtime/app/main.py",
            "payload/runtime/edge_agent/app/main.py",
            "payload/runtime/gateway-console/manifest.json",
        }
        if not required_files <= set(inventory) or not any(
            name.startswith("payload/wheels/") and name.endswith(".whl") for name in inventory
        ):
            raise ValueError("升级包缺少程序、网页、Python 或离线依赖")
        for name, entry in inventory.items():
            safe_name(name)
            item = archive.getinfo(name)
            mode = item.external_attr >> 16
            if (
                not isinstance(entry, dict)
                or set(entry) != {"size", "sha256"}
                or not isinstance(entry["size"], int)
                or entry["size"] < 0
                or not isinstance(entry["sha256"], str)
                or not DIGEST.fullmatch(entry["sha256"])
                or entry["size"] != item.file_size
                or item.is_dir()
                or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                or item.flag_bits & 1
            ):
                raise ValueError("升级包文件类型或大小异常")
            digest = hashlib.sha256()
            target = None
            if destination:
                target = destination / name.removeprefix("payload/")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ValueError("升级解压目标已存在")
            output = target.open("xb") if target else None
            try:
                with archive.open(item) as stream:
                    size = 0
                    while chunk := stream.read(1024 * 1024):
                        size += len(chunk)
                        if size > entry["size"]:
                            raise ValueError("升级文件解压超限")
                        digest.update(chunk)
                        if output:
                            output.write(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise ValueError("升级文件摘要不匹配")
                if output:
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                if output:
                    output.close()
    return manifest
