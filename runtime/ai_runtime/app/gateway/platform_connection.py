"""Device-owned control-plane endpoint override shared by Runtime and Edge Agent."""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_HOST_PORT = re.compile(r"^(?:\[[0-9A-Fa-f:]+\]|[^/:\s]+)(?::[0-9]{1,5})?$")


def connection_path(runtime_data_root: Path) -> Path:
    return runtime_data_root / "gateway" / "platform-connection.json"


def normalize_platform_url(value: str) -> str:
    """Accept a convenient IP/host input but persist one unambiguous HTTP(S) base URL."""
    candidate = value.strip().rstrip("/")
    if not candidate or len(candidate) > 512 or any(ord(char) < 32 for char in candidate):
        raise ValueError("平台地址不能为空或过长")
    if "://" not in candidate:
        if not _HOST_PORT.fullmatch(candidate):
            raise ValueError("请输入平台 IP、域名或完整 HTTP(S) 地址")
        candidate = f"http://{candidate}"
        if urlsplit(candidate).port is None:
            candidate += ":48888"
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("平台地址仅支持 HTTP 或 HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("平台地址不能包含账号密码")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("平台地址只能填写根地址，不能包含路径、参数或片段")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("平台端口无效") from error
    if port is not None and port < 1:
        raise ValueError("平台端口无效")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def read_platform_connection(runtime_data_root: Path, deployed_url: str) -> dict:
    path = connection_path(runtime_data_root)
    fallback = normalize_platform_url(deployed_url)
    if not path.is_file():
        return {"platformUrl": fallback, "source": "DEPLOYMENT", "updatedAt": None}
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != "1.0":
        raise ValueError("unsupported platform connection schema")
    return {
        "platformUrl": normalize_platform_url(str(document["platformUrl"])),
        "source": "LOCAL_OVERRIDE",
        "updatedAt": document.get("updatedAt"),
    }


def write_platform_connection(runtime_data_root: Path, platform_url: str) -> dict:
    path = connection_path(runtime_data_root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    document = {
        "schemaVersion": "1.0",
        "platformUrl": normalize_platform_url(platform_url),
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(document, output, ensure_ascii=False, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "platformUrl": document["platformUrl"],
        "source": "LOCAL_OVERRIDE",
        "updatedAt": document["updatedAt"],
    }
