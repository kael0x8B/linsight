"""Report deployment prerequisites from the Runtime environment, without loading models."""

import importlib.metadata
import platform
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ExecutionProvider(BaseModel):
    """A concrete inference backend proven available on this Runtime host."""

    code: str
    device_type: Literal["CPU", "GPU", "NPU", "ACCELERATOR"] = Field(alias="deviceType")
    vendor: str
    targets: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    runtime: str
    runtime_version: str | None = Field(default=None, alias="runtimeVersion")


class ModelEnvironment(BaseModel):
    schema_version: Literal["1.0"] = Field(default="1.0", alias="schemaVersion")
    formats: list[str] = Field(default_factory=list)
    rknn_targets: list[str] = Field(default_factory=list, alias="rknnTargets")
    providers: list[ExecutionProvider] = Field(default_factory=list)


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _rknpu_available(dev: Path, drm: Path) -> bool:
    if (dev / "rknpu").exists():
        return True
    for node in drm.glob("renderD*"):
        try:
            if "DRIVER=RKNPU" in (node / "device/uevent").read_text().splitlines():
                if (dev / "dri" / node.name).exists():
                    return True
        except OSError:
            continue
    return False


def model_environment(
    compatible: Path = Path("/proc/device-tree/compatible"),
    dev: Path = Path("/dev"),
    drm: Path = Path("/sys/class/drm"),
) -> ModelEnvironment:
    formats: list[str] = []
    targets: list[str] = []
    providers: list[ExecutionProvider] = []
    machine = platform.machine().lower()
    onnx_runtime = _version("onnxruntime")
    onnx_runtime_gpu = _version("onnxruntime-gpu")
    if onnx_runtime or onnx_runtime_gpu:
        formats.append("ONNX")
        providers.append(
            ExecutionProvider(
                code="onnxruntime",
                deviceType="CPU",
                vendor="generic",
                targets=[machine] if machine else [],
                formats=["ONNX"],
                runtime="onnxruntime-gpu" if onnx_runtime_gpu else "onnxruntime",
                runtimeVersion=onnx_runtime_gpu or onnx_runtime,
            )
        )
    # These formats use DependencyManager's existing isolated CPU profile, which
    # can be prepared on demand. Torch need not be installed in Runtime's venv.
    if platform.system() == "Linux" and machine in {"aarch64", "x86_64"}:
        formats.extend(["ARCHIVE", "TORCHSCRIPT", "PYTORCH"])
        providers.append(
            ExecutionProvider(
                code="python-cpu",
                deviceType="CPU",
                vendor="generic",
                targets=[machine],
                formats=["ARCHIVE", "TORCHSCRIPT", "PYTORCH"],
                runtime="dependency-manager",
                runtimeVersion=None,
            )
        )
    rknn_runtime = _version("rknn-toolkit-lite2")
    if (
        platform.system() == "Linux"
        and machine == "aarch64"
        and rknn_runtime == "2.3.2"
        and _rknpu_available(dev, drm)
    ):
        try:
            # A generic ARM CPU or render node does not prove the model's SoC target.
            targets = sorted(
                set(re.findall(rb"rockchip,(rk\d{4}[a-z]?)\x00", compatible.read_bytes()))
            )
            targets = [value.decode("ascii") for value in targets]
        except OSError:
            targets = []
        if targets:
            formats.append("RKNN")
            providers.append(
                ExecutionProvider(
                    code="rknpu2",
                    deviceType="NPU",
                    vendor="rockchip",
                    targets=targets,
                    # Some packaged face models use the same RKNPU backend.
                    formats=["RKNN", "ARCHIVE"],
                    runtime="rknn-toolkit-lite2",
                    runtimeVersion=rknn_runtime,
                )
            )
    return ModelEnvironment(formats=formats, rknnTargets=targets, providers=providers)
