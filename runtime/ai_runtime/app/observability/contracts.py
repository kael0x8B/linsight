from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ai_runtime.app.model.environment import ModelEnvironment


class ProcessMetrics(BaseModel):
    pid: int
    cpu_percent: float = Field(alias="cpuPercent", ge=0)
    resident_memory_bytes: int = Field(alias="residentMemoryBytes", ge=0)
    open_file_count: int = Field(alias="openFileCount", ge=0)


class SystemMetrics(BaseModel):
    cpu_percent: float = Field(alias="cpuPercent", ge=0)
    load_average_1m: float = Field(alias="loadAverage1m", ge=0)
    load_average_5m: float = Field(alias="loadAverage5m", ge=0)
    load_average_15m: float = Field(alias="loadAverage15m", ge=0)
    memory_total_bytes: int = Field(alias="memoryTotalBytes", ge=0)
    memory_used_bytes: int = Field(alias="memoryUsedBytes", ge=0)
    memory_percent: float = Field(alias="memoryPercent", ge=0, le=100)
    disk_total_bytes: int = Field(alias="diskTotalBytes", ge=0)
    disk_used_bytes: int = Field(alias="diskUsedBytes", ge=0)
    disk_percent: float = Field(alias="diskPercent", ge=0, le=100)
    network_bytes_sent: int = Field(alias="networkBytesSent", ge=0)
    network_bytes_received: int = Field(alias="networkBytesReceived", ge=0)
    temperature_celsius: float | None = Field(default=None, alias="temperatureCelsius")


class TaskMetrics(BaseModel):
    total: int = Field(ge=0)
    running: int = Field(ge=0)
    failed: int = Field(ge=0)
    analysis_fps: float = Field(alias="analysisFps", ge=0)
    queue_depth: int = Field(alias="queueDepth", ge=0)
    inference_p95_millis: float = Field(alias="inferenceP95Millis", ge=0)
    preprocess_p50_millis: float = Field(alias="preprocessP50Millis", ge=0)
    preprocess_p95_millis: float = Field(alias="preprocessP95Millis", ge=0)
    preprocess_p99_millis: float = Field(alias="preprocessP99Millis", ge=0)
    inference_p50_millis: float = Field(alias="inferenceP50Millis", ge=0)
    inference_p99_millis: float = Field(alias="inferenceP99Millis", ge=0)
    postprocess_p50_millis: float = Field(alias="postprocessP50Millis", ge=0)
    postprocess_p95_millis: float = Field(alias="postprocessP95Millis", ge=0)
    postprocess_p99_millis: float = Field(alias="postprocessP99Millis", ge=0)
    total_latency_p50_millis: float = Field(alias="totalLatencyP50Millis", ge=0)
    total_latency_p95_millis: float = Field(alias="totalLatencyP95Millis", ge=0)
    total_latency_p99_millis: float = Field(alias="totalLatencyP99Millis", ge=0)
    confirmed_events: int = Field(alias="confirmedEvents", ge=0)


class StreamMetrics(BaseModel):
    active: int = Field(ge=0)
    subscriber_count: int = Field(alias="subscriberCount", ge=0)
    input_fps: float = Field(alias="inputFps", ge=0)
    frames: int = Field(ge=0)
    dropped_frames: int = Field(alias="droppedFrames", ge=0)
    reconnects: int = Field(ge=0)


class ModelMetrics(BaseModel):
    loaded: int = Field(ge=0)
    capacity: int = Field(ge=1)
    load_failures: int = Field(alias="loadFailures", ge=0)
    inference_errors: int = Field(alias="inferenceErrors", ge=0)


class DeliveryMetrics(BaseModel):
    pending_events: int = Field(alias="pendingEvents", ge=0)
    pending_transitions: int = Field(alias="pendingTransitions", ge=0)
    dead_letter_transitions: int = Field(alias="deadLetterTransitions", ge=0)
    retrying_events: int = Field(alias="retryingEvents", ge=0)
    retrying_transitions: int = Field(alias="retryingTransitions", ge=0)
    max_delivery_attempts: int = Field(alias="maxDeliveryAttempts", ge=0)
    total_retry_count: int = Field(alias="totalRetryCount", ge=0)
    oldest_event_age_seconds: int = Field(alias="oldestEventAgeSeconds", ge=0)
    evidence_backlog_bytes: int = Field(alias="evidenceBacklogBytes", ge=0)
    missing_media_files: int = Field(alias="missingMediaFiles", ge=0)
    capture_errors: int = Field(alias="captureErrors", ge=0)
    unfinalized_events: int = Field(alias="unfinalizedEvents", ge=0)


class RuntimeObservabilitySnapshot(BaseModel):
    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    generated_at: datetime = Field(alias="generatedAt")
    system: SystemMetrics
    process: ProcessMetrics
    tasks: TaskMetrics
    streams: StreamMetrics
    models: ModelMetrics
    delivery: DeliveryMetrics
    model_environment: ModelEnvironment | None = Field(default=None, alias="modelEnvironment")
