import asyncio
import base64
import io
import shutil
import subprocess
from datetime import UTC, datetime

import pytest
from PIL import Image
from pydantic import SecretStr, ValidationError

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.event.store import OfflineEventStore
from ai_runtime.app.model.contracts import ModelTestResult
from ai_runtime.app.task.contracts import (
    TaskGlobalSettings,
    TaskInferenceParameters,
    TaskOverlayFrame,
    TaskStartRequest,
)
from ai_runtime.app.task.manager import (
    CapturedFrame,
    SharedCameraStream,
    TaskManager,
    TaskRunner,
    _validate_pipeline,
)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")
def test_continuous_capture_preserves_jpeg_detail_after_rate_control_warmup(tmp_path) -> None:
    # A textured scene exceeds FFmpeg's default MJPEG bitrate. Without fixed quality,
    # identical input frames become heavily quantized after several seconds.
    import numpy as np

    pixels = np.random.default_rng(42).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    source_image = tmp_path / "detail.png"
    Image.fromarray(pixels).save(source_image)
    source_video = tmp_path / "detail.mkv"
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    subprocess.run(  # noqa: S603 -- fixed encoder arguments and pytest-owned fixture paths
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-framerate",
            "5",
            "-i",
            str(source_image),
            "-t",
            "8",
            "-c:v",
            "ffv1",
            str(source_video),
        ],
        check=True,
        timeout=30,
    )

    async def capture() -> bytes:
        stream = SharedCameraStream(
            1,
            SecretStr(str(source_video)),
            RuntimeSettings(api_key="a-secure-runtime-key-for-tests", task_capture_fps=5),
        )
        process = await stream._create_process()
        try:
            assert process.stdout is not None
            data = await asyncio.wait_for(process.stdout.read(), 20)
            assert await asyncio.wait_for(process.wait(), 5) == 0
            return data
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    data = asyncio.run(capture())
    frames = [part + b"\xff\xd9" for part in data.split(b"\xff\xd9")[:-1]]
    assert len(frames) == 40
    quantization_means = []
    for frame in (frames[0], frames[20], frames[-1]):
        with Image.open(io.BytesIO(frame)) as image:
            assert image.size == (640, 480)
            table = image.quantization[0]
            quantization_means.append(sum(table) / len(table))
    assert max(quantization_means) < 16
    assert max(quantization_means) <= min(quantization_means) * 1.2


class FakeModelPool:
    def __init__(self) -> None:
        self.checked: list[int] = []

    def is_loaded(self, _model_version_id: int, _device: str | None = None) -> bool:
        self.checked.append(_model_version_id)
        return True

    async def acquire(self, model_ids, registry=None):
        ids = sorted(set(model_ids))
        if any(not self.is_loaded(value) for value in ids):
            raise KeyError("one or more model versions are not loaded")
        return tuple((value, "CPU") for value in ids)

    async def release(self, lease):
        pass


def test_delayed_inference_overlay_keeps_exact_input_image_and_capture_timestamp(
    tmp_path, monkeypatch
) -> None:
    async def scenario() -> None:
        entered, release = asyncio.Event(), asyncio.Event()
        published = asyncio.Event()

        def publish(**values):
            result = TaskOverlayFrame(**values)
            published.set()
            return result

        monkeypatch.setattr("ai_runtime.app.task.manager.TaskOverlayFrame", publish)

        class DelayedPool(FakeModelPool):
            async def test(self, value):
                entered.set()
                await release.wait()
                return ModelTestResult(
                    sourceWidth=80,
                    sourceHeight=60,
                    objects=[],
                    backend="TEST",
                    device="CPU",
                    preprocessMillis=0,
                    inferenceMillis=10,
                    postprocessMillis=0,
                )

        settings = RuntimeSettings(
            api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path
        )
        manager = TaskManager(settings, DelayedPool(), FakeSharedStream)
        await manager.start_task(request(1, "11111111-1111-1111-1111-111111111111"))
        runner = manager._tasks[1]
        stream = io.BytesIO()
        Image.new("RGB", (80, 60), "red").save(stream, format="JPEG")
        original = stream.getvalue()
        capture_time = 1788690000123
        runner.queue.put_nowait(CapturedFrame(original, capture_time))
        await asyncio.wait_for(entered.wait(), 1)
        # A newer frame arrives while this inference is still running.
        runner.queue.put_nowait(CapturedFrame(b"newer-frame", capture_time + 200))
        release.set()
        await asyncio.wait_for(published.wait(), 2)
        result = runner._latest_overlay
        assert result.timestamp.timestamp() * 1000 == pytest.approx(capture_time)
        assert base64.b64decode(result.image_base64) == original
        assert result.frame_id.endswith(":1")
        await manager.close()

    asyncio.run(scenario())


class FakeSharedStream:
    instances = 0

    def __init__(self, camera_id, source_url, _settings) -> None:
        type(self).instances += 1
        self.camera_id = camera_id
        self.source_url = source_url
        self.subscribers = {}
        self.frames = 0
        self.dropped_frames = 0
        self.reconnects = 0
        self.started_monotonic = 1.0

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class FakeVehiclePlateModelPool(FakeModelPool):
    def __init__(self) -> None:
        super().__init__()
        self.ocr_crop_size: tuple[int, int] | None = None

    async def test(self, request):
        common = {
            "sourceWidth": 200,
            "sourceHeight": 100,
            "backend": "FAKE",
            "device": "CPU",
            "preprocessMillis": 1,
            "inferenceMillis": 2,
            "postprocessMillis": 1,
        }
        if request.model_version_id == 40:
            objects = [
                {
                    "class": "car",
                    "confidence": 0.9,
                    "bbox": {"x": 0.2, "y": 0.2, "width": 0.7, "height": 0.7},
                    "attributes": {},
                }
            ]
        elif request.model_version_id == 41:
            objects = [
                {
                    "class": "license_plate",
                    "confidence": 0.92,
                    "bbox": {"x": 0.5, "y": 0.65, "width": 0.2, "height": 0.12},
                    "attributes": {
                        "corner1X": 0.50,
                        "corner1Y": 0.65,
                        "corner2X": 0.70,
                        "corner2Y": 0.63,
                        "corner3X": 0.70,
                        "corner3Y": 0.77,
                        "corner4X": 0.50,
                        "corner4Y": 0.77,
                    },
                }
            ]
        else:
            with Image.open(request.image_path) as crop:
                self.ocr_crop_size = crop.size
                common["sourceWidth"], common["sourceHeight"] = crop.size
            objects = [
                {
                    "class": "license_plate",
                    "confidence": 0.98,
                    "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                    "attributes": {
                        "plateText": "皖A12345",
                        "ocrConfidence": 0.98,
                        "ocrCharset": "CHINESE_MAINLAND",
                    },
                }
            ]
        return ModelTestResult.model_validate({**common, "objects": objects})


def request(task_id: int, run_id: str) -> TaskStartRequest:
    return TaskStartRequest.model_validate(
        {
            "taskId": task_id,
            "runId": run_id,
            "configVersion": 1,
            "cameraId": 10,
            "sourceUrl": "rtsp://camera.invalid/live",
            "algorithmId": 20,
            "pipelineVersionId": 30,
            "pipeline": {
                "schemaVersion": "1.0",
                "nodes": [
                    {
                        "id": "person-detector",
                        "type": "DETECTOR",
                        "capabilityKey": "detector.person",
                    }
                ],
                "edges": [],
            },
            "modelVersionId": 40,
            "parameters": {"schemaVersion": "1.0", "sampleFps": 1.0},
        }
    )


def test_tasks_on_same_camera_share_one_decode_owner(tmp_path) -> None:
    async def scenario() -> None:
        FakeSharedStream.instances = 0
        settings = RuntimeSettings(
            api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path
        )
        manager = TaskManager(settings, FakeModelPool(), FakeSharedStream)  # type: ignore[arg-type]
        first = await manager.start_task(request(1, "11111111-1111-1111-1111-111111111111"))
        second = await manager.start_task(request(2, "22222222-2222-2222-2222-222222222222"))

        assert first.status == "RUNNING"
        assert second.status == "RUNNING"
        assert manager.active_stream_count == 1
        assert FakeSharedStream.instances == 1
        assert len(manager.statuses()) == 2
        metrics = manager.observability_metrics()
        assert metrics["tasks"]["total"] == 2
        assert metrics["tasks"]["running"] == 2
        assert metrics["streams"]["active"] == 1
        assert metrics["streams"]["subscriberCount"] == 2
        assert metrics["delivery"]["pendingEvents"] == 0

        await manager.stop_task(1, first.run_id)
        assert manager.active_stream_count == 1
        await manager.stop_task(2, second.run_id)
        assert manager.active_stream_count == 0

    asyncio.run(scenario())


def test_task_start_validates_every_distinct_model_binding(tmp_path) -> None:
    async def scenario() -> None:
        settings = RuntimeSettings(
            api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path
        )
        pool = FakeModelPool()
        manager = TaskManager(settings, pool, FakeSharedStream)  # type: ignore[arg-type]
        value = request(1, "11111111-1111-1111-1111-111111111111")
        value.model_bindings = {
            "person-detector": 40,
            "face-recognizer": 41,
            "secondary-alias": 41,
        }

        started = await manager.start_task(value)

        assert started.status == "RUNNING"
        assert pool.checked == [40, 41]
        assert manager._tasks[1].request.model_bindings["face-recognizer"] == 41
        await manager.close()

    asyncio.run(scenario())


def test_vehicle_plate_pipeline_crops_before_ocr_and_merges_attributes(tmp_path) -> None:
    async def scenario() -> None:
        settings = RuntimeSettings(
            api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path
        )
        value = request(1, "11111111-1111-1111-1111-111111111111")
        value.pipeline = {
            "schemaVersion": "1.0",
            "nodes": [
                {"id": "vehicle", "type": "DETECTOR", "capabilityKey": "detector.vehicle"},
                {"id": "plate", "type": "DETECTOR", "capabilityKey": "detector.license-plate"},
                {"id": "ocr", "type": "OCR", "capabilityKey": "ocr.license-plate"},
                {"id": "tracker", "type": "TRACKER", "capabilityKey": "tracker.iou"},
            ],
            "edges": [
                {"from": "vehicle", "to": "tracker"},
                {"from": "plate", "to": "ocr"},
                {"from": "ocr", "to": "tracker"},
            ],
        }
        value.model_bindings = {"vehicle": 40, "plate": 41, "ocr": 42}
        stream = FakeSharedStream(value.camera_id, value.source_url, settings)
        pool = FakeVehiclePlateModelPool()
        store = OfflineEventStore(tmp_path / "events.sqlite3")
        runner = TaskRunner(value, asyncio.Queue(), stream, pool, settings, store)  # type: ignore[arg-type]
        runner.frame_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (200, 100), color=(20, 30, 40)).save(runner.frame_path)

        results, objects = await runner._infer_frame()

        assert len(results) == 3
        assert len(objects) == 2
        assert pool.ocr_crop_size is not None
        assert pool.ocr_crop_size[0] < 200 and pool.ocr_crop_size[1] < 100
        plate = next(item for item in objects if item.class_name == "license_plate")
        assert plate.attributes["plateText"] == "皖A12345"
        assert not list(runner.frame_path.parent.glob("plate-crop-*.jpg"))
        store.close()

    asyncio.run(scenario())


def test_versioned_global_settings_hot_apply_to_running_task(tmp_path) -> None:
    async def scenario() -> None:
        settings = RuntimeSettings(
            api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path
        )
        manager = TaskManager(settings, FakeModelPool(), FakeSharedStream)  # type: ignore[arg-type]
        started = await manager.start_task(request(1, "11111111-1111-1111-1111-111111111111"))
        applied = await manager.apply_task_settings(
            1,
            TaskGlobalSettings.model_validate(
                {
                    "schemaVersion": "1.0",
                    "recordBeforeSeconds": 15,
                    "recordAfterSeconds": 25,
                    "defaultConfidence": 0.72,
                    "defaultFps": 2.5,
                    "evidenceStorageMode": "OBJECT_STORAGE",
                    "evidenceRetentionDays": 30,
                    "notificationsEnabled": True,
                    "nodeOfflineThresholdSeconds": 60,
                }
            ),
        )

        runner = manager._tasks[1]
        assert started.status == "RUNNING"
        assert applied.status == "RUNNING"
        assert runner.request.parameters.confidence == 0.72
        assert runner.request.parameters.sample_fps == 2.5
        assert runner._evidence.pre_seconds == 15
        assert runner._evidence.post_seconds == 25
        await manager.close()

    asyncio.run(scenario())


def test_overlay_delivery_keeps_only_latest_frame_per_task(tmp_path) -> None:
    async def scenario() -> None:
        settings = RuntimeSettings(
            api_key="a-secure-runtime-key-for-tests", runtime_data_root=tmp_path
        )
        manager = TaskManager(settings, FakeModelPool(), FakeSharedStream)  # type: ignore[arg-type]
        await manager.start_task(request(1, "11111111-1111-1111-1111-111111111111"))
        manager._tasks[1]._latest_overlay = TaskOverlayFrame.model_validate(
            {
                "taskId": 1,
                "runId": "11111111-1111-1111-1111-111111111111",
                "cameraId": 10,
                "frameId": "frame-7",
                "timestamp": datetime.now(UTC),
                "sourceWidth": 1920,
                "sourceHeight": 1080,
                "objects": [
                    {
                        "trackId": "track-1",
                        "class": "person",
                        "confidence": 0.93,
                        "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                        "attributes": {},
                    }
                ],
            }
        )

        delivered = manager.drain_overlay_frames()

        assert len(delivered) == 1
        assert delivered[0].objects[0].class_name == "person"
        assert manager.drain_overlay_frames() == []
        await manager.close()

    asyncio.run(scenario())


def test_task_request_masks_stream_secret() -> None:
    value = request(1, "11111111-1111-1111-1111-111111111111")
    assert isinstance(value.source_url, SecretStr)
    assert "camera.invalid" not in str(value)


def test_area_intrusion_pipeline_requires_controlled_chain_and_rule_binding() -> None:
    pipeline = {
        "schemaVersion": "1.0",
        "nodes": [
            {"id": "detector", "type": "DETECTOR", "capabilityKey": "detector.person"},
            {"id": "tracker", "type": "TRACKER", "capabilityKey": "tracker.iou"},
            {"id": "rule", "type": "RULE", "capabilityKey": "rule.area-intrusion"},
        ],
        "edges": [
            {"from": "detector", "to": "tracker"},
            {"from": "tracker", "to": "rule"},
        ],
    }

    _validate_pipeline(pipeline, has_rule=True)
    try:
        _validate_pipeline(pipeline, has_rule=False)
    except ValueError as error:
        assert "bound rule" in str(error)
    else:
        raise AssertionError("area intrusion pipeline accepted without a bound rule")


def test_generic_coco_count_pipeline_is_controlled_and_requires_rule() -> None:
    pipeline = {
        "schemaVersion": "1.0",
        "nodes": [
            {"id": "detector", "type": "DETECTOR", "capabilityKey": "detector.coco"},
            {"id": "tracker", "type": "TRACKER", "capabilityKey": "tracker.iou"},
            {"id": "rule", "type": "RULE", "capabilityKey": "rule.count"},
        ],
        "edges": [
            {"from": "detector", "to": "tracker"},
            {"from": "tracker", "to": "rule"},
        ],
        "acceptance": {"status": "PASS"},
    }

    _validate_pipeline(pipeline, has_rule=True)
    try:
        _validate_pipeline(pipeline, has_rule=False)
    except ValueError as error:
        assert "bound rule" in str(error)
    else:
        raise AssertionError("generic count pipeline accepted without a bound rule")


def test_pipeline_with_external_acceptance_block_cannot_start() -> None:
    blocked = {
        "schemaVersion": "1.0",
        "nodes": [{"id": "helmet", "type": "CLASSIFIER", "capabilityKey": "ppe.helmet"}],
        "edges": [],
        "acceptance": {"status": "BLOCKED_EXTERNAL_ASSETS"},
    }

    try:
        _validate_pipeline(blocked)
    except ValueError as error:
        assert "production acceptance" in str(error)
    else:
        raise AssertionError("blocked pipeline was accepted for execution")


def test_pipeline_with_pending_acceptance_cannot_start() -> None:
    pending = {
        "schemaVersion": "1.0",
        "nodes": [{"id": "flame", "type": "DETECTOR", "capabilityKey": "detector.flame"}],
        "edges": [],
        "acceptance": {"status": "PENDING"},
    }

    try:
        _validate_pipeline(pending)
    except ValueError as error:
        assert "production acceptance" in str(error)
    else:
        raise AssertionError("pending pipeline was accepted for execution")


@pytest.mark.parametrize("status", ["PENDING", "BLOCKED_EXTERNAL_ASSETS"])
def test_field_validation_is_explicit_and_preserves_acceptance(status) -> None:
    pipeline = {
        "schemaVersion": "1.0",
        "nodes": [{"id": "detector", "type": "DETECTOR", "capabilityKey": "detector.person"}],
        "edges": [],
        "acceptance": {"status": status},
    }
    parameters = TaskInferenceParameters.model_validate(
        {"schemaVersion": "1.0", "validationOnly": True}
    )
    _validate_pipeline(pipeline, parameters=parameters)
    assert pipeline["acceptance"]["status"] == status
    with pytest.raises(ValueError, match="production acceptance"):
        _validate_pipeline(
            pipeline, parameters=parameters.model_copy(update={"validation_only": False})
        )
    pipeline["acceptance"]["status"] = "BLOCKED_RUNTIME_ADAPTER"
    with pytest.raises(ValueError, match="production acceptance"):
        _validate_pipeline(pipeline, parameters=parameters)


def test_validation_mode_rejects_string_coercion() -> None:
    with pytest.raises(ValidationError):
        TaskInferenceParameters.model_validate({"schemaVersion": "1.0", "validationOnly": "true"})


def test_story_eleven_pipeline_requires_complete_controlled_chain() -> None:
    incomplete = {
        "schemaVersion": "1.0",
        "nodes": [
            {"id": "person", "type": "DETECTOR", "capabilityKey": "detector.person"},
            {"id": "helmet", "type": "CLASSIFIER", "capabilityKey": "ppe.helmet"},
            {"id": "tracker", "type": "TRACKER", "capabilityKey": "tracker.iou"},
        ],
        "edges": [{"from": "person", "to": "helmet"}],
    }

    try:
        _validate_pipeline(incomplete)
    except ValueError as error:
        assert "controlled chain" in str(error)
    else:
        raise AssertionError("incomplete PPE chain was accepted")


def test_behavior_pipeline_rejects_single_frame_confirmation() -> None:
    behavior = {
        "schemaVersion": "1.0",
        "nodes": [
            {
                "id": "smoking",
                "type": "CLASSIFIER",
                "capabilityKey": "behavior.smoking",
            },
            {"id": "tracker", "type": "TRACKER", "capabilityKey": "tracker.iou"},
        ],
        "edges": [{"from": "smoking", "to": "tracker"}],
    }
    values = TaskInferenceParameters.model_validate(
        {
            "schemaVersion": "1.0",
            "temporalN": 1,
            "temporalM": 1,
            "durationSeconds": 0,
        }
    )

    try:
        _validate_pipeline(behavior, parameters=values)
    except ValueError as error:
        assert "single-frame" in str(error)
    else:
        raise AssertionError("single-frame behavior confirmation was accepted")


def test_independent_npu_models_overlap_with_same_frame_and_order(tmp_path):
    async def scenario():
        second_entered = asyncio.Event()
        completed = []
        source = Image.new('RGB', (200, 100), 'red')

        class NpuPool(FakeModelPool):
            async def test(self, value, image=None):
                assert image is source
                if value.model_version_id == 40:
                    await asyncio.wait_for(second_entered.wait(), 1)
                else:
                    second_entered.set()
                completed.append(value.model_version_id)
                return ModelTestResult(sourceWidth=200, sourceHeight=100, objects=[],
                    backend=str(value.model_version_id), device='RKNPU',
                    preprocessMillis=0, inferenceMillis=1, postprocessMillis=0)

        settings = RuntimeSettings(
            api_key='a-secure-runtime-key-for-tests', runtime_data_root=tmp_path
        )
        value = request(1, '11111111-1111-1111-1111-111111111111')
        value.model_bindings = {'first': 40, 'second': 41, 'alias': 41}
        store = OfflineEventStore(tmp_path / 'events.sqlite3')
        runner = TaskRunner(
            value, asyncio.Queue(), FakeSharedStream(value.camera_id, value.source_url, settings),
            NpuPool(), settings, store
        )
        try:
            results, objects = await runner._infer_frame(source)
            assert completed == [41, 40]  # Completion order does not reorder output bindings.
            assert [item.backend for item in results] == ['40', '41']
            assert objects == []
        finally:
            await runner.stop()
            store.close()
    asyncio.run(scenario())


def test_timeline_jpegs_are_sampled_without_reusing_another_frames_picture(tmp_path):
    settings = RuntimeSettings(api_key='a-secure-runtime-key-for-tests', runtime_data_root=tmp_path)
    value = request(1, '11111111-1111-1111-1111-111111111111')
    store = OfflineEventStore(tmp_path / 'events.sqlite3')
    runner = TaskRunner(
        value, asyncio.Queue(), FakeSharedStream(value.camera_id, value.source_url, settings),
        FakeModelPool(), settings, store
    )
    try:
        first = CapturedFrame(b'first', 1, 'epoch-a', 90_000)
        assert base64.b64decode(runner._overlay_image(first)) == b'first'
        assert runner._overlay_image(CapturedFrame(b'next', 2, 'epoch-a', 108_000)) is None
        assert base64.b64decode(runner._overlay_image(
            CapturedFrame(b'after-two-seconds', 3, 'epoch-a', 270_000))) == b'after-two-seconds'
        assert base64.b64decode(runner._overlay_image(
            CapturedFrame(b'reconnected', 4, 'epoch-b', 0))) == b'reconnected'
        assert base64.b64decode(runner._overlay_image(CapturedFrame(b'legacy', 5))) == b'legacy'
        assert runner._overlay_image(CapturedFrame(b'x' * 262_145, 6)) is None
    finally:
        store.close()


@pytest.mark.parametrize('behavior,positive', [('behavior.phone-call', 'phone_call'),
                                               ('behavior.phone-call', 'calling')])
def test_person_behavior_uses_individual_crops_and_ignores_texting(tmp_path, behavior, positive):
    from ai_runtime.app.model.contracts import DetectionObject

    async def scenario():
        sizes = []

        class Pool:
            async def test(self, value, *, image=None):
                if value.model_version_id == 40:
                    objects = [DetectionObject.model_validate({
                        'class': 'person', 'confidence': 0.95,
                        'bbox': {'x': x, 'y': 0, 'width': 0.4, 'height': 1},
                    }) for x in [0, 0.6]]
                else:
                    sizes.append(image.size)
                    objects = [DetectionObject.model_validate({
                        'class': positive if len(sizes) == 1 else 'texting', 'confidence': 0.9,
                        'bbox': {'x': 0, 'y': 0, 'width': 1, 'height': 1},
                    })]
                return ModelTestResult(sourceWidth=image.width, sourceHeight=image.height,
                    objects=objects, backend='test', device='CPU', preprocessMillis=0,
                    inferenceMillis=1, postprocessMillis=0)

        settings = RuntimeSettings(
            api_key='a-secure-runtime-key-for-tests', runtime_data_root=tmp_path)

        value = request(1, '11111111-1111-1111-1111-111111111111')
        value.pipeline = {'schemaVersion': '1.0', 'nodes': [
            {'id': 'person', 'type': 'DETECTOR', 'capabilityKey': 'detector.person'},
            {'id': 'behavior', 'type': 'CLASSIFIER', 'capabilityKey': behavior,
             'inputMode': 'PERSON_CROPS'},
        ]}
        value.model_bindings = {'person': 40, 'behavior': 41}
        store = OfflineEventStore(tmp_path / 'events.sqlite3')
        runner = TaskRunner(value, asyncio.Queue(),
            FakeSharedStream(value.camera_id, value.source_url, settings), Pool(), settings, store)
        try:
            with Image.new('RGB', (200, 100)) as source:
                results, objects = await runner._infer_frame(source)
            assert sizes == [(80, 100), (80, 100)]
            assert len(results) == 3
            assert len(objects) == 1
            assert objects[0].class_name == 'phone_call'
            assert objects[0].bbox.width == 0.4
            assert objects[0].attributes['behaviorPersonAssociated'] is True
        finally:
            await runner.stop()
            store.close()

    asyncio.run(scenario())
