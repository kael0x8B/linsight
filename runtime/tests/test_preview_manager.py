import asyncio
from pathlib import Path

import pytest
from pydantic import SecretStr

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.stream.preview import (
    PreviewCreateRequest,
    PreviewManager,
    PreviewState,
    StreamWorker,
)


class FakeWorker:
    def __init__(
        self,
        camera_id: int,
        source_url: SecretStr,
        output_dir: Path,
        _settings: RuntimeSettings,
    ) -> None:
        self.camera_id = camera_id
        self.source_url = source_url
        self.output_dir = output_dir
        self.state = PreviewState.READY
        self.diagnostic_id = "diagnostic-1"
        self.subscribers: set[str] = set()
        self.start_count = 0
        self.stop_count = 0

    async def ensure_started(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1


def test_sessions_share_one_camera_stream_worker_and_release_last_owner(
    tmp_path: Path,
) -> None:
    workers: list[FakeWorker] = []

    def factory(
        camera_id: int,
        source_url: SecretStr,
        output_dir: Path,
        settings: RuntimeSettings,
    ) -> FakeWorker:
        worker = FakeWorker(camera_id, source_url, output_dir, settings)
        workers.append(worker)
        return worker

    settings = RuntimeSettings(
        api_key="a-secure-runtime-key-for-tests",
        preview_root=tmp_path,
    )
    manager = PreviewManager(settings, worker_factory=factory)  # type: ignore[arg-type]
    request = PreviewCreateRequest(
        cameraId=7,
        sourceUrl=SecretStr("rtsp://operator:secret@192.0.2.10/live"),
    )

    async def scenario() -> None:
        first = await manager.create_session(request)
        second = await manager.create_session(request)

        assert manager.active_stream_count == 1
        assert first.session_id != second.session_id
        assert first.subscriber_count == 1
        assert second.subscriber_count == 2
        assert len(workers) == 1

        await manager.release_session(first.session_id)
        assert manager.active_stream_count == 1
        assert workers[0].stop_count == 0

        await manager.release_session(second.session_id)
        assert manager.active_stream_count == 0
        assert workers[0].stop_count == 1

    asyncio.run(scenario())


def test_main_and_sub_streams_use_independent_workers(tmp_path: Path) -> None:
    workers: list[FakeWorker] = []

    def factory(
        camera_id: int,
        source_url: SecretStr,
        output_dir: Path,
        settings: RuntimeSettings,
    ) -> FakeWorker:
        worker = FakeWorker(camera_id, source_url, output_dir, settings)
        workers.append(worker)
        return worker

    settings = RuntimeSettings(
        api_key="a-secure-runtime-key-for-tests",
        preview_root=tmp_path,
    )
    manager = PreviewManager(settings, worker_factory=factory)  # type: ignore[arg-type]

    async def scenario() -> None:
        main = await manager.create_session(
            PreviewCreateRequest(
                cameraId=7,
                sourceUrl=SecretStr("rtsp://192.0.2.10/main"),
                streamType="MAIN",
            )
        )
        sub = await manager.create_session(
            PreviewCreateRequest(
                cameraId=7,
                sourceUrl=SecretStr("rtsp://192.0.2.10/sub"),
                streamType="SUB",
            )
        )

        assert manager.active_stream_count == 2
        assert len(workers) == 2
        assert workers[0].output_dir.name == "camera-7-main"
        assert workers[1].output_dir.name == "camera-7-sub"

        await manager.release_session(main.session_id)
        assert manager.active_stream_count == 1
        assert workers[0].stop_count == 1
        assert workers[1].stop_count == 0

        await manager.release_session(sub.session_id)
        assert manager.active_stream_count == 0
        assert workers[1].stop_count == 1

    asyncio.run(scenario())


def test_session_response_never_contains_source_secret(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        api_key="a-secure-runtime-key-for-tests",
        preview_root=tmp_path,
    )
    manager = PreviewManager(settings, worker_factory=FakeWorker)  # type: ignore[arg-type]

    async def scenario() -> str:
        response = await manager.create_session(
            PreviewCreateRequest(
                cameraId=9,
                sourceUrl=SecretStr("rtsp://operator:secret@192.0.2.11/private"),
            )
        )
        return response.model_dump_json(by_alias=True)

    serialized = asyncio.run(scenario())
    assert "operator" not in serialized
    assert "secret" not in serialized
    assert "/private" not in serialized


def test_media_name_allowlist_rejects_path_traversal(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        api_key="a-secure-runtime-key-for-tests",
        preview_root=tmp_path,
    )
    manager = PreviewManager(settings, worker_factory=FakeWorker)  # type: ignore[arg-type]

    async def scenario() -> None:
        response = await manager.create_session(
            PreviewCreateRequest(cameraId=10, sourceUrl=SecretStr("rtsp://192.0.2.12/live"))
        )
        with pytest.raises(FileNotFoundError):
            await manager.get_media(response.session_id, "segment-../../secret.ts")

    asyncio.run(scenario())


def test_ffmpeg_forces_keyframes_at_hls_segment_boundary(tmp_path: Path) -> None:
    settings = RuntimeSettings(
        api_key="a-secure-runtime-key-for-tests",
        preview_root=tmp_path,
        preview_hls_segment_seconds=1,
    )
    worker = StreamWorker(
        11,
        SecretStr("rtsp://operator:secret@192.0.2.13/live"),
        tmp_path / "camera-11",
        settings,
    )

    args = worker._build_ffmpeg_args()  # noqa: SLF001

    assert args[args.index("-force_key_frames") + 1] == "expr:gte(t,n_forced*1)"
