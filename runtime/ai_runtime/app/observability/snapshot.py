import os
from datetime import UTC, datetime

import psutil

from ai_runtime.app.model.environment import model_environment
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.observability.contracts import RuntimeObservabilitySnapshot
from ai_runtime.app.task.manager import TaskManager

PROMETHEUS_METRICS = {
    "system_cpu_percent": ("system", "cpu_percent"),
    "system_load_average_1m": ("system", "load_average_1m"),
    "system_load_average_5m": ("system", "load_average_5m"),
    "system_load_average_15m": ("system", "load_average_15m"),
    "system_memory_used_bytes": ("system", "memory_used_bytes"),
    "system_memory_total_bytes": ("system", "memory_total_bytes"),
    "system_disk_used_bytes": ("system", "disk_used_bytes"),
    "system_disk_total_bytes": ("system", "disk_total_bytes"),
    "system_network_sent_bytes_total": ("system", "network_bytes_sent"),
    "system_network_received_bytes_total": ("system", "network_bytes_received"),
    "ai_process_cpu_percent": ("process", "cpu_percent"),
    "ai_process_resident_memory_bytes": ("process", "resident_memory_bytes"),
    "ai_tasks_running": ("tasks", "running"),
    "ai_tasks_failed": ("tasks", "failed"),
    "ai_analysis_fps": ("tasks", "analysis_fps"),
    "ai_queue_depth": ("tasks", "queue_depth"),
    "ai_preprocess_p95_milliseconds": ("tasks", "preprocess_p95_millis"),
    "ai_inference_p50_milliseconds": ("tasks", "inference_p50_millis"),
    "ai_inference_p95_milliseconds": ("tasks", "inference_p95_millis"),
    "ai_inference_p99_milliseconds": ("tasks", "inference_p99_millis"),
    "ai_postprocess_p95_milliseconds": ("tasks", "postprocess_p95_millis"),
    "ai_total_latency_p50_milliseconds": ("tasks", "total_latency_p50_millis"),
    "ai_total_latency_p95_milliseconds": ("tasks", "total_latency_p95_millis"),
    "ai_total_latency_p99_milliseconds": ("tasks", "total_latency_p99_millis"),
    "ai_confirmed_events_total": ("tasks", "confirmed_events"),
    "model_load_failures_total": ("models", "load_failures"),
    "ai_inference_errors_total": ("models", "inference_errors"),
    "video_streams_active": ("streams", "active"),
    "video_stream_input_fps": ("streams", "input_fps"),
    "video_frames_total": ("streams", "frames"),
    "video_dropped_frames_total": ("streams", "dropped_frames"),
    "video_rtsp_reconnects_total": ("streams", "reconnects"),
    "offline_queue_events": ("delivery", "pending_events"),
    "offline_queue_transitions": ("delivery", "pending_transitions"),
    "offline_queue_failed": ("delivery", "dead_letter_transitions"),
    "offline_queue_retrying": ("delivery", "retrying_events"),
    "offline_queue_retry_total": ("delivery", "total_retry_count"),
    "offline_queue_oldest_event_age_seconds": ("delivery", "oldest_event_age_seconds"),
    "offline_evidence_backlog_bytes": ("delivery", "evidence_backlog_bytes"),
    "offline_missing_media_files": ("delivery", "missing_media_files"),
}


class RuntimeObservabilityService:
    def __init__(self, task_manager: TaskManager, model_pool: ModelPool) -> None:
        self._task_manager = task_manager
        self._model_pool = model_pool
        self._process = psutil.Process()

    def snapshot(self) -> RuntimeObservabilitySnapshot:
        try:
            open_files = len(self._process.open_files())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            open_files = 0
        memory = self._process.memory_info()
        system_memory = psutil.virtual_memory()
        disk = psutil.disk_usage(self._task_manager.settings.runtime_data_root)
        network = psutil.net_io_counters()
        try:
            load_1m, load_5m, load_15m = os.getloadavg()
        except (AttributeError, OSError):
            load_1m = load_5m = load_15m = 0.0
        temperature = _maximum_temperature()
        values = self._task_manager.observability_metrics()
        return RuntimeObservabilitySnapshot.model_validate(
            {
                "schemaVersion": "1.0",
                "generatedAt": datetime.now(UTC),
                "modelEnvironment": model_environment(),
                "system": {
                    "cpuPercent": psutil.cpu_percent(interval=None),
                    "loadAverage1m": load_1m,
                    "loadAverage5m": load_5m,
                    "loadAverage15m": load_15m,
                    "memoryTotalBytes": system_memory.total,
                    "memoryUsedBytes": system_memory.used,
                    "memoryPercent": system_memory.percent,
                    "diskTotalBytes": disk.total,
                    "diskUsedBytes": disk.used,
                    "diskPercent": disk.percent,
                    "networkBytesSent": network.bytes_sent,
                    "networkBytesReceived": network.bytes_recv,
                    "temperatureCelsius": temperature,
                },
                "process": {
                    "pid": self._process.pid,
                    "cpuPercent": self._process.cpu_percent(interval=None),
                    "residentMemoryBytes": memory.rss,
                    "openFileCount": open_files,
                },
                "tasks": values["tasks"],
                "streams": values["streams"],
                "models": {
                    "loaded": self._model_pool.size,
                    "capacity": self._model_pool.capacity,
                    "loadFailures": self._model_pool.load_failures,
                    "inferenceErrors": self._model_pool.inference_errors,
                },
                "delivery": values["delivery"],
            }
        )

    def prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# TYPE linsight_runtime_start_time_seconds gauge",
            f"linsight_runtime_start_time_seconds {self._process.create_time():g}",
        ]
        for suffix, (group, field) in PROMETHEUS_METRICS.items():
            value = getattr(getattr(snapshot, group), field)
            if value is None:
                continue
            name = f"linsight_{suffix}"
            lines.extend((f"# TYPE {name} gauge", f"{name} {float(value):g}"))
        if snapshot.system.temperature_celsius is not None:
            lines.extend(
                (
                    "# TYPE linsight_system_temperature_celsius gauge",
                    f"linsight_system_temperature_celsius {snapshot.system.temperature_celsius:g}",
                )
            )
        return "\n".join(lines) + "\n"


def _maximum_temperature() -> float | None:
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        return None
    current = [
        float(entry.current)
        for entries in sensors.values()
        for entry in entries
        if entry.current is not None and -50 <= float(entry.current) <= 200
    ]
    return max(current, default=None)
