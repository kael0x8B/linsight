from typing import Any

import psutil


def collect_resources() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpuUsage": psutil.cpu_percent(interval=None),
        "memoryUsedBytes": memory.used,
        "memoryTotalBytes": memory.total,
        "diskUsedBytes": disk.used,
        "diskTotalBytes": disk.total,
        "gpuUsage": None,
        "gpuMemoryUsedBytes": None,
        "gpuMemoryTotalBytes": None,
    }
