import socket
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LINSIGHT_AGENT_", extra="ignore")

    control_plane_url: str = "http://127.0.0.1:48888"
    bootstrap_token: SecretStr | None = None
    credential_file: Path = Path("./var/edge-agent-credential.json")
    node_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    node_name: str = Field(min_length=1, max_length=100)
    agent_version: str = "0.1.0"
    host_name: str = Field(default_factory=socket.gethostname)
    heartbeat_interval_seconds: float = Field(default=10.0, ge=2.0, le=60.0)
    check_poll_interval_seconds: float = Field(default=2.0, ge=0.5, le=30.0)
    stream_probe_timeout_seconds: float = Field(default=25.0, ge=3.0, le=30.0)
    request_timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)
    ffprobe_binary: str = "ffprobe"
    runtime_url: str = "http://127.0.0.1:48900"
    runtime_api_key: SecretStr
    preview_tunnel_enabled: bool = True
    preview_tunnel_allow_insecure: bool = True
    preview_tunnel_max_media_bytes: int = Field(
        default=8 * 1024 * 1024, ge=1024 * 1024, le=32 * 1024 * 1024
    )
    preview_tunnel_concurrency: int = Field(default=4, ge=1, le=16)
    runtime_data_root: Path = Path("./var/runtime-data")
    command_poll_interval_seconds: float = Field(default=2.0, ge=0.5, le=30.0)
    task_report_interval_seconds: float = Field(default=10.0, ge=2.0, le=60.0)
    event_poll_interval_seconds: float = Field(default=1.0, ge=0.5, le=30.0)
    overlay_poll_interval_seconds: float = Field(default=0.1, ge=0.05, le=5.0)
    log_report_interval_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    log_repeat_window_seconds: float = Field(default=60.0, ge=10.0, le=600.0)
    log_buffer_capacity: int = Field(default=2000, ge=100, le=10000)
    upgrade_root: Path = Path("./var/edge-agent")
    upgrade_signing_key: SecretStr | None = None
    lifecycle_request_path: Path = Path("/run/linsight/node-power-request")
    disk_cleanup_status_file: Path = Path("/var/lib/linsight/disk-pressure/last-run.env")
