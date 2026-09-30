from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LINSIGHT_RUNTIME_", extra="ignore", populate_by_name=True
    )

    api_key: str = Field(min_length=24)
    ffprobe_binary: str = "ffprobe"
    ffmpeg_binary: str = "ffmpeg"
    max_probe_seconds: float = Field(default=15.0, ge=3.0, le=60.0)
    preview_root: Path = Path("./var/preview")
    # Smart-codec cameras can legally delay the first decodable IDR by more
    # than eight seconds.  Keep startup bounded, but allow one long GOP so a
    # healthy stream is not repeatedly torn down before it becomes usable.
    preview_startup_seconds: float = Field(default=20.0, ge=2.0, le=30.0)
    preview_idle_seconds: float = Field(default=30.0, ge=10.0, le=300.0)
    # HEVC preview is decoded once and encoded as H.264 for browser WebRTC.
    # Bound the software encoder independently of the analysis frame rate.
    preview_hevc_fps: float = Field(default=12.0, ge=1.0, le=25.0)
    preview_hevc_max_width: int = Field(default=1280, ge=320, le=3840)
    preview_hevc_max_height: int = Field(default=720, ge=240, le=2160)
    preview_hls_segment_seconds: int = Field(default=1, ge=1, le=4)
    preview_hls_list_size: int = Field(default=6, ge=3, le=20)
    model_pool_size: int = Field(default=4, ge=1, le=32)
    model_memory_safety_ratio: float = Field(default=0.05, ge=0.0, le=0.50)
    model_memory_min_reserve_mib: int = Field(default=512, ge=128, le=16_384)
    onnx_intra_op_threads: int = Field(default=2, ge=1, le=32)
    runtime_data_root: Path = Field(
        default=Path("./var/runtime-data"),
        validation_alias=AliasChoices(
            "LINSIGHT_RUNTIME_DATA_ROOT",
            "LINSIGHT_RUNTIME_RUNTIME_DATA_ROOT",
        ),
    )
    task_capture_fps: float = Field(default=4.0, ge=0.5, le=25.0)
    task_capture_jpeg_quality: int = Field(default=2, ge=2, le=31)
    task_startup_seconds: float = Field(default=20.0, ge=2.0, le=30.0)
    rockchip_hardware_decode: bool = True
    rockchip_gstreamer_python: Path = Path("/usr/bin/python3")
    # Unset limits follow the verified SoC: RK3588 retains up to 4K for OCR
    # crops; other boards keep the existing 1080p memory budget.
    rockchip_capture_max_width: int | None = Field(default=None, ge=320, le=7680)
    rockchip_capture_max_height: int | None = Field(default=None, ge=240, le=4320)
    evidence_pre_seconds: float = Field(default=10.0, ge=0.0, le=120.0)
    evidence_post_seconds: float = Field(default=20.0, ge=0.0, le=120.0)
    evidence_video_fps: float = Field(default=5.0, ge=0.5, le=25.0)

    gateway_history_days: int = Field(default=7, ge=1, le=365)
    gateway_console_enabled: bool = True
    gateway_console_host: str = "0.0.0.0"  # noqa: S104 - authenticated LAN management entrance
    gateway_console_port: int = Field(default=48901, ge=0, le=65535)
    gateway_event_tcp_host: str = "0.0.0.0"  # noqa: S104 - authenticated subscriber entrance
    gateway_event_tcp_port: int = Field(default=48902, ge=0, le=65535)
    platform_url: str = "http://127.0.0.1:48888"

    gateway_runtime_url: str = Field(
        default="http://127.0.0.1:48900", pattern=r"^http://127\.0\.0\.1:[0-9]{1,5}$"
    )
