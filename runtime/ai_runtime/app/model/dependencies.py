"""Bounded, platform-owned dependency preparation; never install into the live venv."""

import asyncio
import os
import platform
import shutil
import site
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DependencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_format: Literal["ONNX", "PYTORCH", "TORCHSCRIPT", "ARCHIVE", "RKNN"] = Field(
        alias="artifactFormat"
    )


class DependencyStatus(BaseModel):
    profile: str
    status: Literal["RUNNING", "READY", "FAILED"]
    stage: str
    error_code: str | None = Field(default=None, alias="errorCode")
    error_message: str | None = Field(default=None, alias="errorMessage")


# Only this reviewed profile can install software. No model-supplied requirement,
# repository, extra, URL or shell command is ever passed to pip.
PROFILE = (
    f"torch-cpu-2.14-ultralytics-8.4.142-py{sys.version_info.major}{sys.version_info.minor}"
    f"-{platform.machine()}-v1"
)
CHECK = (
    "import torch, torchvision, ultralytics; "
    "assert torch.__version__.split('+')[0] == '2.14.0'; "
    "assert torchvision.__version__.split('+')[0] == '0.29.0'; "
    "assert ultralytics.__version__ == '8.4.142'; "
    "assert torch.version.cuda is None; "
    "torchvision.ops.nms(torch.zeros((0, 4)), torch.zeros(0), 0.5)"
)


class DependencyFailure(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DependencyManager:
    def __init__(self, root: Path):
        self.root = root.resolve() / "dependencies"
        self._task: asyncio.Task | None = None
        self._status = DependencyStatus(profile=PROFILE, status="RUNNING", stage="CHECKING_ENV")
        self._python: Path | None = None

    def start(self, request: DependencyRequest) -> DependencyStatus:
        if request.artifact_format == "RKNN":
            from ai_runtime.app.model.rknn import require_rknn_sdk

            try:
                require_rknn_sdk()
            except ValueError as error:
                return DependencyStatus(
                    profile="rknn-base-2.3.2", status="FAILED", stage="CHECKING_ENV",
                    errorCode="RKNN_SDK_UNAVAILABLE", errorMessage=str(error),
                )
            return DependencyStatus(profile="rknn-base-2.3.2", status="READY", stage="ENV_READY")
        if request.artifact_format == "ONNX":
            return DependencyStatus(profile="onnx-base", status="READY", stage="ENV_READY")
        # All concurrent callers join the same preparation. A new POST after a
        # terminal failure is an explicit retry; GET never restarts installation.
        if self._task is None or (self._task.done() and self._status.status == "FAILED"):
            self._status = DependencyStatus(profile=PROFILE, status="RUNNING", stage="CHECKING_ENV")
            self._task = asyncio.create_task(self._prepare())
        return self._status.model_copy()

    def status(self, profile: str) -> DependencyStatus:
        if profile == "rknn-base-2.3.2":
            return self.start(DependencyRequest(artifactFormat="RKNN"))
        if profile != PROFILE:
            raise KeyError("Unknown dependency profile")
        return self._status.model_copy()

    async def ensure(self, artifact_format: str) -> Path:
        status = self.start(DependencyRequest(artifactFormat=artifact_format))
        if artifact_format in {"ONNX", "RKNN"}:
            if status.status != "READY":
                raise DependencyFailure(status.error_code, status.error_message)
            return Path(sys.executable)
        if self._task is not None:
            await asyncio.shield(self._task)
        if self._python is None:
            raise DependencyFailure(
                self._status.error_code or "DEPENDENCY_NOT_READY",
                self._status.error_message or "模型运行环境尚未就绪",
            )
        return self._python

    def _stage(self, stage: str) -> None:
        self._status.stage = stage

    async def _prepare(self) -> None:
        try:
            async with asyncio.timeout(1200):
                await self._install()
            self._status.status = "READY"
            self._stage("ENV_READY")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._status.status = "FAILED"
            self._status.error_code = (
                error.code if isinstance(error, DependencyFailure) else "DEPENDENCY_PREPARE_FAILED"
            )
            self._status.error_message = (
                str(error)
                if isinstance(error, DependencyFailure)
                else "运行环境准备失败或超时，请检查节点磁盘、网络后重新部署"
            )

    async def _install(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        # Reuse compatible pre-provisioned environments without any mutation.
        if await self._check(Path(sys.executable)):
            self._python = Path(sys.executable)
            return
        if platform.system() != "Linux" or platform.machine() not in {"aarch64", "x86_64"}:
            raise DependencyFailure(
                "DEPENDENCY_PLATFORM_UNSUPPORTED", "该节点架构不支持自动准备 CPU 推理环境"
            )
        environment = self.root / PROFILE
        python = environment / "bin" / "python"
        if python.exists() and await self._check(python):
            self._python = python
            return
        if shutil.disk_usage(self.root).free < 1500 * 1024 * 1024:
            raise DependencyFailure(
                "DEPENDENCY_DISK_LOW", "准备推理环境至少需要 1.5 GiB 可用磁盘空间"
            )
        self._stage("INSTALLING_DEPS")
        # Read-only inheritance avoids duplicating Runtime's base libraries. Pip
        # writes only to this profile; active inference keeps its original process.
        # Vendor Python may omit ensurepip. Use the same offline seed as initial
        # deployment, including retries of a partially created model environment.
        from ai_runtime.app.core import environment as environment_bootstrap

        await self._run(
            [sys.executable, "-I", str(environment_bootstrap.__file__), str(environment)]
        )
        # Nested venvs do not inherit the invoking venv's site-packages. Explicit
        # read-only fallback is appended after the profile's own site-packages.
        packages = (
            environment
            / "lib"
            / (f"python{sys.version_info.major}.{sys.version_info.minor}")
            / "site-packages"
        )
        packages.mkdir(parents=True, exist_ok=True)
        (packages / "linsight-runtime-base.pth").write_text(
            "\n".join(site.getsitepackages()) + "\n", encoding="utf-8"
        )
        wheels = self.root / "wheels"
        wheels.mkdir(exist_ok=True)
        pip = [
            str(python),
            "-m",
            "pip",
            "--isolated",
            "install",
            "--no-input",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--progress-bar",
            "off",
            "--cache-dir",
            str(self.root / "pip-cache"),
            "--retries",
            "5",
            "--timeout",
            "60",
            "--find-links",
            str(wheels),
        ]
        # A provisioned wheel cache also works on completely offline gateways.
        try:
            await self._run(
                [
                    *pip,
                    "--no-index",
                    "torch==2.14.0+cpu",
                    "torchvision==0.29.0+cpu",
                    "ultralytics==8.4.142",
                ]
            )
            self._stage("VERIFYING_ENV")
            if await self._check(python):
                self._python = python
                return
        except DependencyFailure:
            pass  # Cache misses proceed to the fixed official repositories below.
        for attempt in range(3):
            try:
                self._stage("DOWNLOADING_DEPS" if attempt == 0 else "RETRYING_DEPS")
                await self._run(
                    [
                        *pip,
                        "--index-url",
                        "https://download.pytorch.org/whl/cpu",
                        "torch==2.14.0+cpu",
                        "torchvision==0.29.0+cpu",
                    ]
                )
                await self._run(
                    [*pip, "--index-url", "https://pypi.org/simple", "ultralytics==8.4.142"]
                )
                break
            except DependencyFailure:
                if attempt == 2:
                    raise
                await asyncio.sleep(5 * (attempt + 1))
        self._stage("VERIFYING_ENV")
        if not await self._check(python):
            raise DependencyFailure(
                "DEPENDENCY_VERIFY_FAILED", "依赖安装后导入或版本校验失败，原运行环境未修改"
            )
        self._python = python

    async def _check(self, python: Path) -> bool:
        try:
            await self._run([str(python), "-c", CHECK], limit_seconds=120)
            return True
        except DependencyFailure:
            return False

    async def _run(self, args: list[str], limit_seconds: int = 900) -> None:
        # Do not inherit pip/proxy overrides or runtime/node credentials.
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"}
        }
        env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", YOLO_AUTOINSTALL="false")
        process = await asyncio.create_subprocess_exec(
            *args, env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        try:
            code = await asyncio.wait_for(process.wait(), limit_seconds)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if code != 0:
            raise DependencyFailure(
                "DEPENDENCY_INSTALL_FAILED",
                "依赖下载或安装失败，请检查节点外网连接与磁盘空间后重试",
            )

    async def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
