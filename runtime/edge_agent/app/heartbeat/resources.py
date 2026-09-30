import math
import re
from pathlib import Path
from typing import Any, Final

import psutil

_PERCENT_PATTERN: Final = re.compile(r"(?<![-\d.])(\d+(?:\.\d+)?)\s*%")
_DEVFREQ_LOAD_PATTERN: Final = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*@")
_DISK_ACTIONS_PATTERN: Final = re.compile(r"^[a-z_,]+$")


def _normalize_usage(value: float) -> float | None:
    return min(100.0, value) if math.isfinite(value) and value >= 0 else None


def _parse_usage(raw: str) -> float | None:
    percentages = [float(value) for value in _PERCENT_PATTERN.findall(raw)]
    if percentages:
        return _normalize_usage(sum(percentages) / len(percentages))
    match = _DEVFREQ_LOAD_PATTERN.match(raw)
    if match:
        return _normalize_usage(float(match.group(1)))
    stripped = raw.strip()
    try:
        value = float(stripped)
    except ValueError:
        return None
    return _normalize_usage(value)


def _read_usage(paths: list[Path]) -> float | None:
    for path in paths:
        try:
            usage = _parse_usage(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
        if usage is not None:
            return usage
    return None


def _devfreq_load_paths(devfreq_root: Path, device_type: str) -> list[Path]:
    paths: list[Path] = []
    try:
        entries = sorted(devfreq_root.iterdir(), key=lambda path: path.name)
    except OSError:
        return paths
    for entry in entries:
        try:
            resolved_name = entry.resolve(strict=False).name
        except (OSError, RuntimeError):
            resolved_name = ""
        names = f"{entry.name} {resolved_name}".lower()
        if device_type in names:
            paths.append(entry / "load")
    return paths


def collect_accelerator_usage(
    devfreq_root: Path = Path("/sys/class/devfreq"),
    debugfs_root: Path = Path("/sys/kernel/debug"),
) -> tuple[float | None, float | None]:
    """Return GPU and NPU utilization without requiring a vendor SDK."""
    gpu_usage = _read_usage(_devfreq_load_paths(devfreq_root, "gpu"))
    npu_usage = _read_usage(
        [debugfs_root / "rknpu" / "load", *_devfreq_load_paths(devfreq_root, "npu")]
    )
    return gpu_usage, npu_usage


def collect_disk_cleanup_status(path: Path) -> dict[str, Any]:
    """Read the root helper's non-sensitive, atomically written cleanup receipt."""
    result: dict[str, Any] = {
        "diskCleanupStatus": None,
        "diskCleanupLastRunEpochSeconds": None,
        "diskCleanupBeforePercent": None,
        "diskCleanupAfterPercent": None,
        "diskCleanupFreedBytes": None,
        "diskCleanupActions": None,
    }
    try:
        values = dict(
            line.split("=", 1)
            for line in path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        status = values.get("STATUS")
        if status not in {"RECLAIMED", "STILL_HIGH"}:
            return result
        last_run = int(values["LAST_RUN_EPOCH_SECONDS"])
        before = int(values["BEFORE_PERCENT"])
        after = int(values["AFTER_PERCENT"])
        freed = int(values["FREED_BYTES"])
        actions = values.get("ACTIONS", "none")
        if (
            last_run < 0
            or not 0 <= before <= 100
            or not 0 <= after <= 100
            or freed < 0
            or len(actions) > 255
            or _DISK_ACTIONS_PATTERN.fullmatch(actions) is None
        ):
            return result
    except (OSError, UnicodeError, ValueError, KeyError):
        return result
    return {
        "diskCleanupStatus": status,
        "diskCleanupLastRunEpochSeconds": last_run,
        "diskCleanupBeforePercent": before,
        "diskCleanupAfterPercent": after,
        "diskCleanupFreedBytes": freed,
        "diskCleanupActions": actions,
    }


def collect_resources(
    disk_cleanup_status_file: Path = Path("/var/lib/linsight/disk-pressure/last-run.env"),
) -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    gpu_usage, npu_usage = collect_accelerator_usage()
    return {
        "cpuUsage": psutil.cpu_percent(interval=None),
        "memoryUsedBytes": memory.used,
        "memoryTotalBytes": memory.total,
        "diskUsedBytes": disk.used,
        "diskTotalBytes": disk.total,
        "gpuUsage": gpu_usage,
        "gpuMemoryUsedBytes": None,
        "gpuMemoryTotalBytes": None,
        "npuUsage": npu_usage,
        **collect_disk_cleanup_status(disk_cleanup_status_file),
    }
