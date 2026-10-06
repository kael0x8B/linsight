"""Linux host adapter. All commands, paths and service names are installer-owned."""

import json
import os
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

SERVICES = ("linsight-ai-runtime.service", "linsight-edge-agent.service")


class LinuxSystem:
    def __init__(self, log: Path, timeout: float = 180):
        self.log, self.timeout = log, timeout
        self._key = ""

    @staticmethod
    def public_error(error: Exception) -> str:
        # subprocess output stays in the root-only log, never returned through the API.
        if isinstance(error, subprocess.SubprocessError):
            return "本机安装或服务检查失败，请查看升级诊断日志"
        if isinstance(error, (ValueError, TimeoutError)):
            return str(error)[:400]
        return "本机升级失败（" + type(error).__name__ + "），请检查设备诊断日志"

    def run(self, args: list[str], *, cwd: Path | None = None, timeout=180):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": "/root",
            "LANG": "C.UTF-8",
            "PIP_CONFIG_FILE": "/dev/null",
            "PIP_NO_INDEX": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        with self.log.open("ab") as output:
            os.chmod(self.log, 0o600)
            subprocess.run(  # noqa: S603 - fixed commands and signed release paths
                args,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=output,  # noqa: S603
                check=True,
                timeout=timeout,
            )

    @staticmethod
    def flush():
        os.sync()

    def preflight(self, manifest: dict, package_size: int, root: Path):
        if platform.system() != "Linux" or platform.machine() != manifest["architecture"]:
            raise ValueError("升级包 CPU 架构与当前盒子不一致")
        libc, version = platform.libc_ver()
        if libc != "glibc" or tuple(map(int, version.split("."))) < tuple(
            map(int, manifest["minGlibc"].split("."))
        ):
            raise ValueError("盒子系统运行库低于此升级包的要求")
        compatible = Path("/proc/device-tree/compatible")
        hardware = compatible.read_bytes().decode(errors="replace") if compatible.exists() else ""
        device = next((soc for soc in ("rk3588", "rk3568", "rk3566") if soc in hardware), "generic")
        if device not in manifest["devices"]:
            raise ValueError("升级包不支持当前盒子型号")
        # Wheels and Python expand a second time. Leave a persistent free-space reserve.
        expanded = sum(entry["size"] for entry in manifest["files"].values())
        required = expanded * 4 + package_size + 512 * 1024**2
        if shutil.disk_usage(root).free < required:
            raise ValueError(f"空间不足，本次升级至少需要 {required // 1024**2} MiB 可用空间")
        for binary in ("ffmpeg", "ffprobe", "systemctl"):
            if shutil.which(binary) is None:
                raise ValueError(f"盒子缺少已有系统能力 {binary}，升级未开始")
        self.run(["/usr/bin/systemctl", "is-active", "--quiet", *SERVICES], timeout=15)

    def prepare_release(self, target: Path, manifest: dict):
        python_root = target / "python"
        python_root.mkdir()
        with tarfile.open(target / "python.tar.gz", "r:gz") as archive:
            entries = archive.getmembers()
            if len(entries) > 50000 or sum(entry.size for entry in entries) > 2 * 1024**3:
                raise ValueError("独立 Python 解压大小异常")
            for entry in entries:
                if (
                    not entry.name.startswith("python/")
                    or ".." in PurePosixPath(entry.name).parts
                    or entry.isdev()
                    or entry.isfifo()
                ):
                    raise ValueError("独立 Python 安装包内容异常")
            # data filter checks symlink/hardlink targets as well as member paths.
            archive.extractall(target, filter="data")  # noqa: S202
        python = target / "python/bin/python3"
        runtime = target / "runtime"
        if not python.is_file() or not python.resolve().is_relative_to(python_root):
            raise ValueError("独立 Python 缺少有效解释器")
        self.run([str(python), "-I", "-c", "import sys; assert sys.version_info[:2] == (3, 12)"])
        self.run(
            [
                str(python),
                "-I",
                str(runtime / "ai_runtime/app/core/environment.py"),
                str(target / "venv"),
            ]
        )
        venv_python = str(target / "venv/bin/python")
        wheels = sorted(str(path) for path in (target / "wheels").glob("*.whl"))
        if not wheels:
            raise ValueError("升级包没有离线依赖")
        self.run(
            [
                venv_python,
                "-I",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                "--no-deps",
                "--no-cache-dir",
                "--disable-pip-version-check",
                *wheels,
            ],
            timeout=900,
        )
        self.run([venv_python, "-I", "-m", "pip", "check"])
        self.run(
            [
                venv_python,
                "-I",
                str(runtime / "ai_runtime/app/gateway/console_artifact.py"),
                "install",
                "--bundle-dir",
                str(runtime / "gateway-console"),
                "--target",
                str(runtime / "gateway-console/current"),
            ]
        )
        self.run(
            [venv_python, "-c", "import ai_runtime.app.main, edge_agent.app.main"],
            cwd=runtime,
            timeout=60,
        )
        if manifest["devices"] != ["generic"]:
            self.run([venv_python, "-c", "from rknnlite.api import RKNNLite"], cwd=runtime)

    @staticmethod
    def _pid(service: str) -> str:
        pid = (
            subprocess.check_output(  # noqa: S603
                ["/usr/bin/systemctl", "show", service, "--property=MainPID", "--value"], timeout=10
            )
            .decode()
            .strip()
        )
        if not pid.isdigit() or int(pid) < 1:
            raise ValueError("应用服务尚未启动")
        return pid

    def _environment(self, service: str) -> dict:
        raw = Path("/proc", self._pid(service), "environ").read_bytes()
        return dict(entry.decode().split("=", 1) for entry in raw.split(b"\0") if b"=" in entry)

    def _request(self, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            "http://127.0.0.1:48900" + path,
            data=data,
            headers={"X-Runtime-Key": self._key, "Content-Type": "application/json"},
        )
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=5
        ) as r:
            return json.load(r)

    def capture(self) -> dict:
        self._key = self._environment(SERVICES[0]).get("LINSIGHT_RUNTIME_API_KEY", "")
        if not self._key:
            raise ValueError("无法读取现有 Runtime 的健康检查凭据")
        response = self._request("/v1/gateway/rpc", {"action": "snapshot", "payload": {}})
        if not response.get("ok"):
            raise ValueError("无法确认现有任务状态，原版本未切换")
        return {
            "tasks": [
                {
                    "id": task["config"]["taskId"],
                    "enabled": task["enabled"],
                    "revision": task["revision"],
                    "healthy": task.get("status", {}).get("status") == "RUNNING",
                    "processing": task.get("status", {}).get("metrics", {}).get("analyzedFrames", 0)
                    > 0,
                }
                for task in response["data"]["tasks"]
            ]
        }

    def stop(self):
        self.run(["/usr/bin/systemctl", "stop", SERVICES[1], SERVICES[0]], timeout=90)

    def start(self):
        self.run(["/usr/bin/systemctl", "start", *SERVICES], timeout=90)

    def wait_healthy(self, release_id: str, baseline: dict):
        deadline = time.monotonic() + self.timeout
        consecutive = 0
        first_frames = {}
        while time.monotonic() < deadline:
            try:
                for service in SERVICES:
                    env = self._environment(service)
                    if env.get("LINSIGHT_APP_RELEASE") != release_id:
                        raise ValueError("运行进程版本与目标版本不一致")
                    if service == SERVICES[0]:
                        self._key = env.get("LINSIGHT_RUNTIME_API_KEY", "")
                self._request("/v1/health")
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open("http://127.0.0.1:48901/gateway-health", timeout=5) as response:
                    if json.load(response).get("owner") != "runtime":
                        raise ValueError("本地管理入口不健康")
                with opener.open("http://127.0.0.1:48901/", timeout=5) as response:
                    if not response.read(1024):
                        raise ValueError("本地管理网页为空")
                snapshot = self._request("/v1/gateway/rpc", {"action": "snapshot", "payload": {}})
                if not snapshot.get("ok"):
                    raise ValueError("新版本无法读取任务配置")
                tasks = {task["config"]["taskId"]: task for task in snapshot["data"]["tasks"]}
                for old in baseline.get("tasks", []):
                    task = tasks.get(old["id"])
                    if (
                        task is None
                        or task["enabled"] != old["enabled"]
                        or task["revision"] != old["revision"]
                        or (
                            old["healthy"]
                            and old["enabled"]
                            and task.get("status", {}).get("status") != "RUNNING"
                        )
                    ):
                        raise ValueError("原有任务尚未恢复")
                    if old.get("processing") and old["enabled"] and old["healthy"]:
                        frames = task.get("status", {}).get("metrics", {}).get("analyzedFrames", 0)
                        first = first_frames.setdefault(old["id"], frames)
                        if frames <= first:
                            raise ValueError("原有识别任务尚未处理新帧")
                consecutive += 1
                if consecutive >= 3:
                    return
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                consecutive = 0
            time.sleep(2)
        raise TimeoutError("新版本或原有任务未在规定时间内恢复")
