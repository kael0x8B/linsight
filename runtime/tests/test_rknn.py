import asyncio
import hashlib

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from ai_runtime.app.model import rknn
from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestParameters, ModelTestRequest
from ai_runtime.app.model.dependencies import (
    DependencyFailure,
    DependencyManager,
    DependencyRequest,
)
from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.pool import ModelPool
from edge_agent.app.command.deployed_models import DeployedModelRegistry


def manifest():
    return {
        "schemaVersion": "1.0",
        "taskType": "OBJECT_DETECTION",
        "preprocess": {
            "inputWidth": 32,
            "inputHeight": 32,
            "layout": "NHWC",
            "dtype": "UINT8",
            "scale": 1.0,
            "color": "RGB",
        },
        "decoder": {"type": "AUTO_DETECTION", "labels": ["person"]},
    }


def payload(path, version=1):
    return {
        "modelVersionId": version,
        "artifactPath": path,
        "artifactFormat": "RKNN",
        "device": "RKNPU",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "runtimeManifest": manifest(),
    }


def test_npu_and_cpu_contracts_cannot_be_mislabeled(tmp_path):
    path = tmp_path / "model.rknn"
    path.write_bytes(b"RKNN-test")
    for changes in [{"device": "CPU"}, {"artifactFormat": "ONNX"}, {"runtimeManifest": None}]:
        with pytest.raises(ValidationError):
            DeployModelRequest.model_validate({**payload(path), **changes})


def test_npu_pool_runs_manifest_without_cpu_fallback_and_releases(tmp_path, monkeypatch):
    instances = []

    class SDK:
        def __init__(self, **_):
            self.released = 0
            instances.append(self)

        def load_rknn(self, path):
            return 0

        def init_runtime(self):
            return 0

        def inference(self, inputs, data_format):
            assert data_format == ["nhwc"]
            assert inputs[0].dtype == np.uint8
            assert inputs[0].shape == (1, 32, 32, 3)
            assert inputs[0][0, 0, 0].tolist() == [20, 40, 60]
            return [np.array([[[0.1, 0.2, 0.3, 0.4, 0.9, 0]]], dtype=np.float32)]

        def release(self):
            self.released += 1

    monkeypatch.setattr(rknn, "require_rknn_sdk", lambda: SDK)
    path = tmp_path / "model.rknn"
    path.write_bytes(b"RKNN-test")
    picture = tmp_path / "input.png"
    Image.new("RGB", (96, 64), (20, 40, 60)).save(picture)
    pool = ModelPool(max_models=1, isolate_rknn=False)

    async def exercise():
        result = await pool.deploy(DeployModelRequest.model_validate(payload(path)))
        assert result.device == "RKNPU"
        assert result.backend == "RKNN_RUNTIME_MANIFEST"
        assert pool.is_loaded(1) and not pool.is_loaded(1, "CPU")
        request = ModelTestRequest.model_validate(
            {
                "modelVersionId": 1,
                "imagePath": picture,
                "parameters": {
                    "schemaVersion": "1.0",
                    "confidence": 0.25,
                    "nmsThreshold": 0.45,
                    "inputWidth": 32,
                    "inputHeight": 32,
                    "outputCoordinates": "NORMALIZED_XYWH",
                },
            }
        )
        result = await pool.test(request)
        assert result.device == "RKNPU"
        assert (result.source_width, result.source_height) == (96, 64)
        assert result.objects[0].class_name == "person"
        assert result.objects[0].bbox.x == pytest.approx(0.1)
        # A sampled camera frame is decoded once and shared by both models.
        # The pool must not open the evidence JPEG again or mutate that image.
        source = Image.new("RGB", (96, 64), (20, 40, 60))
        with monkeypatch.context() as patch:

            def unexpected_open(*_args, **_kwargs):
                raise AssertionError("shared RGB input must not reopen the JPEG")

            patch.setattr(Image, "open", unexpected_open)
            shared = await pool.test(request, image=source)
        assert shared.objects == result.objects
        assert (shared.source_width, shared.source_height) == (96, 64)
        assert source.getpixel((0, 0)) == (20, 40, 60)
        await pool.deploy(DeployModelRequest.model_validate(payload(path, 2)))
        assert instances[0].released == 1
        await pool.close()
        assert instances[1].released == 1

    asyncio.run(exercise())


def test_npu_failed_initialization_releases_device(tmp_path, monkeypatch):
    class SDK:
        released = 0

        def __init__(self, **_):
            pass

        def load_rknn(self, path):
            return 0

        def init_runtime(self):
            return -1

        def release(self):
            SDK.released += 1

    monkeypatch.setattr(rknn, "require_rknn_sdk", lambda: SDK)
    path = tmp_path / "model.rknn"
    path.write_bytes(b"RKNN-test")
    pool = ModelPool(isolate_rknn=False)
    with pytest.raises(ValueError, match="incompatible"):
        asyncio.run(pool.deploy(DeployModelRequest.model_validate(payload(path))))
    assert pool.size == 0
    assert SDK.released == 1


def test_missing_sdk_is_reported_without_installing_other_backends(tmp_path, monkeypatch):
    def missing():
        raise ValueError("SDK unavailable")

    monkeypatch.setattr(rknn, "require_rknn_sdk", missing)
    manager = DependencyManager(tmp_path)
    assert manager.start(DependencyRequest(artifactFormat="RKNN")).status == "FAILED"
    with pytest.raises(DependencyFailure, match="SDK unavailable"):
        asyncio.run(manager.ensure("RKNN"))
    assert manager._task is None
    assert not manager.root.exists()


def test_agent_registry_preserves_npu_device_across_restart(tmp_path):
    path = tmp_path / "models/1/model.rknn"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"RKNN-test")
    registry = DeployedModelRegistry(tmp_path)
    registry.record({**payload(path), "trustedArtifact": False})
    restored = DeployedModelRegistry(tmp_path).load_payloads()
    assert restored[0]["artifactFormat"] == "RKNN"
    assert restored[0]["device"] == "RKNPU"
    assert restored[0]["runtimeManifest"] == manifest()


def test_plate_npu_uses_letterbox_and_restores_source_corners(tmp_path, monkeypatch):
    class SDK:
        def __init__(self, **_):
            pass

        def load_rknn(self, path):
            return 0

        def init_runtime(self):
            return 0

        def release(self):
            pass

        def inference(self, inputs, data_format):
            image = inputs[0]
            assert image.shape == (1, 640, 640, 3)
            assert image.dtype == np.uint8
            assert image[0, 0, 0].tolist() == [114, 114, 114]
            assert image[0, 140, 0].tolist() == [20, 40, 60]
            return [
                np.array(
                    [[[320, 320, 200, 50, 0.9, 220, 295, 420, 295, 420, 345, 220, 345, 0.8, 0.1]]]
                )
            ]

    monkeypatch.setattr(rknn, "require_rknn_sdk", lambda: SDK)
    contract = RuntimeManifest.model_validate(
        {
            "schemaVersion": "1.0",
            "taskType": "OBJECT_DETECTION",
            "preprocess": {
                "inputWidth": 640,
                "inputHeight": 640,
                "layout": "NHWC",
                "dtype": "UINT8",
                "color": "RGB",
                "scale": 1,
                "resize": "LETTERBOX",
            },
            "decoder": {"type": "YOLO_PLATE"},
        }
    )
    result = rknn.RknnAdapter(tmp_path / "model.rknn", contract).infer_image(
        Image.new("RGB", (1280, 720), (20, 40, 60)),
        ModelTestParameters(
            schemaVersion="1.0",
            confidence=0.5,
            nmsThreshold=0.5,
            inputWidth=640,
            inputHeight=640,
            outputCoordinates="NORMALIZED_XYWH",
        ),
    )
    assert result.device == "RKNPU"
    assert result.objects[0].confidence == pytest.approx(0.72)
    assert result.objects[0].attributes["corner1Y"] == pytest.approx(310 / 720)
