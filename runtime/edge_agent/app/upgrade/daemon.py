"""Installer-owned Unix socket. No TCP listener and no caller-selected commands or paths."""

import base64
import json
import os
import socket
import socketserver
import threading
import time
from pathlib import Path
from uuid import UUID

from edge_agent.app.upgrade.application import ApplicationUpdater, atomic_json, read
from edge_agent.app.upgrade.bundle import CHUNK_SIZE, MAX_BUNDLE
from edge_agent.app.upgrade.system import LinuxSystem

SOCKET = Path("/run/linsight-updater/control.sock")
STATE = Path("/var/lib/linsight-updater")
ROOT = Path("/opt/linsight")
KEYS = Path("/etc/linsight/upgrade-keys")
ACTIONS = {"status", "upload.begin", "upload.chunk", "upload.finish", "install", "rollback"}
MAX_REQUEST = 400 * 1024


def request(action: str, payload: dict | None = None, socket_path: Path = SOCKET) -> dict:
    if action not in ACTIONS:
        raise ValueError("不支持的应用升级操作")
    message = json.dumps({"action": action, "payload": payload or {}}).encode() + b"\n"
    if len(message) > MAX_REQUEST:
        raise ValueError("升级请求过大")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(20)
        try:
            connection.connect(str(socket_path))
            connection.sendall(message)
            with connection.makefile("rb") as stream:
                response = json.loads(stream.readline(MAX_REQUEST + 1))
        except (OSError, ValueError) as error:
            raise ValueError("应用升级器暂不可用，请先完成首次迁移或检查安装器服务") from error
    if not response.get("ok"):
        raise ValueError(response.get("message", "升级请求失败"))
    return response["data"]


class UpgradeControl:
    def __init__(self, updater: ApplicationUpdater):
        self.updater = updater
        self.guard = threading.Lock()
        self.worker: threading.Thread | None = None

    def _start(self, function, *args):
        if self.worker and self.worker.is_alive():
            raise ValueError("升级操作正在执行，请查看当前进度")
        (self.updater.state / "last-error.json").unlink(missing_ok=True)

        def work():
            try:
                function(*args)
            except Exception as error:
                # Usually a lock/phase rejection before a transaction starts; preserve its journal.
                atomic_json(
                    self.updater.state / "last-error.json",
                    {"message": self.updater.system.public_error(error), "at": time.time()},
                )

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def invoke(self, action: str, payload: dict) -> dict:
        if action not in ACTIONS or not isinstance(payload, dict):
            raise ValueError("不支持的应用升级操作")
        with self.guard:
            if action == "status":
                return self.updater.status()
            if self.worker and self.worker.is_alive():
                raise ValueError("升级操作正在执行，请等待完成")
            allowed = {
                "upload.begin": {"id", "size"},
                "upload.chunk": {"id", "offset", "data"},
                "upload.finish": {"id"},
                "install": {"id"},
                "rollback": {"id"},
            }
            if set(payload) != allowed[action]:
                raise ValueError("升级参数不符合协议")
            identifier = str(UUID(str(payload["id"])))
            meta_path = self.updater.state / "upload.json"
            package = self.updater.state / "upload.lup"
            if action == "install":
                job = read(self.updater.state / "job.json")
                if job["id"] != identifier or job["phase"] not in {
                    "READY",
                    "SUCCEEDED",
                    "ROLLED_BACK",
                }:
                    raise ValueError("升级任务尚未准备完成或已变化")
                self._start(self.updater.install, identifier)
                return {"id": identifier, "accepted": True}
            if action == "rollback":
                self.updater.require_idle(allow_ready=True)
                if not self.updater.status()["rollbackAvailable"]:
                    raise ValueError("没有可回退版本")
                self._start(self.updater.rollback, identifier)
                return {"id": identifier, "accepted": True}
            self.updater.require_idle(allow_ready=True)
            if action == "upload.begin":
                size = payload["size"]
                if type(size) is not int or not 0 < size <= MAX_BUNDLE:
                    raise ValueError("升级包必须为 1 字节到 2 GiB")
                if meta_path.exists():
                    previous = read(meta_path)
                    if previous["id"] == identifier:
                        if previous["size"] != size:
                            raise ValueError("同一上传编号的文件大小发生变化")
                        return {"id": identifier, "offset": package.stat().st_size}
                import shutil

                if shutil.disk_usage(self.updater.state).free < size + 512 * 1024**2:
                    raise ValueError("磁盘空间不足，无法接收升级包")
                with package.open("wb") as stream:
                    os.chmod(package, 0o600)
                    stream.flush()
                    os.fsync(stream.fileno())
                atomic_json(meta_path, {"id": identifier, "size": size})
                return {"id": identifier, "offset": 0}
            meta = read(meta_path)
            if meta["id"] != identifier:
                raise ValueError("上传任务已变更，请重新选择升级包")
            if action == "upload.chunk":
                offset = payload["offset"]
                data = base64.b64decode(payload["data"], validate=True)
                if type(offset) is not int or offset < 0 or not 0 < len(data) <= CHUNK_SIZE:
                    raise ValueError("升级分块大小或位置无效")
                with package.open("r+b") as stream:
                    current = os.fstat(stream.fileno()).st_size
                    if offset + len(data) > meta["size"] or offset > current:
                        raise ValueError("升级分块位置与服务端不一致")
                    stream.seek(offset)
                    if offset < current:
                        if stream.read(len(data)) != data:
                            raise ValueError("重传分块内容不一致，请重新上传")
                    else:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                return {"id": identifier, "offset": package.stat().st_size}
            if package.stat().st_size != meta["size"]:
                raise ValueError("升级包尚未完整上传")
            self._start(self.updater.prepare, identifier, package)
            return {"id": identifier, "accepted": True}


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    block_on_close = False
    control: UpgradeControl


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(20)
        try:
            message = self.rfile.readline(MAX_REQUEST + 1)
            if len(message) > MAX_REQUEST or not message.endswith(b"\n"):
                raise ValueError("升级请求超出限制")
            value = json.loads(message)
            if set(value) != {"action", "payload"}:
                raise ValueError("升级请求格式错误")
            data = self.server.control.invoke(value["action"], value["payload"])
            result = {"ok": True, "data": data}
        except Exception as error:
            result = {"ok": False, "message": LinuxSystem.public_error(error)}
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b"\n")


def main():
    if os.geteuid() != 0:
        raise SystemExit("安装器服务需要 root")
    config = read(STATE / "config.json")
    updater = ApplicationUpdater(
        ROOT, STATE, KEYS, Path("/run/linsight-deploy.lock"), LinuxSystem(STATE / "installer.log")
    )
    updater.recover_before_services()
    SOCKET.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(SOCKET.parent, 0, config["gid"])
    SOCKET.unlink(missing_ok=True)
    maintenance = SOCKET.parent / "maintenance.lock"
    maintenance.touch(exist_ok=True)
    os.chown(maintenance, 0, config["gid"])
    os.chmod(maintenance, 0o640)
    with Server(str(SOCKET), Handler) as server:
        server.control = UpgradeControl(updater)
        os.chown(SOCKET, 0, config["gid"])
        os.chmod(SOCKET, 0o660)
        notify = os.environ.get("NOTIFY_SOCKET")
        if notify:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as connection:
                connection.connect("\0" + notify[1:] if notify.startswith("@") else notify)
                connection.sendall(b"READY=1")

        def recovery():
            job = updater.status().get("job")
            if job and job["phase"] == "RECOVERY_PENDING":
                # READY has released systemd ordering. This also handles daemon restarts mid-switch.
                time.sleep(1)
                updater.system.stop()
                updater.system.start()
                updater.confirm_recovery()

        server.control._start(recovery)
        server.serve_forever(poll_interval=0.25)


if __name__ == "__main__":
    main()
