import asyncio
import base64
import copy
import hashlib
from io import BytesIO
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from PIL import Image
from pydantic import ValidationError
from test_algorithm_packages import package
from test_model_pool import _write_contract_model
from test_task_manager import request

from ai_runtime.app.capability.packages import AlgorithmPackageStore
from ai_runtime.app.gateway.api import build_gateway_router
from ai_runtime.app.model.contracts import DeployModelRequest, DetectionObject, ModelTestResult
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.task.image_recognition import (
    ImageRecognitionError,
    TaskImageRecognizer,
    TaskImageRequest,
    decode_image,
)


def image_request(format="PNG", size=(320, 180)):
    buffer = BytesIO()
    Image.new("RGB", size, (20, 30, 40)).save(buffer, format=format)
    return TaskImageRequest(taskId=1, imageBase64=base64.b64encode(buffer.getvalue()).decode())


def document():
    config = request(1, str(uuid4())).model_dump(mode="json", by_alias=True)
    config["sourceUrl"] = "rtsp://camera.invalid/live"
    config["parameters"].update(inputWidth=32, inputHeight=32)
    return {"revision": 7, "enabled": False, "config": config}


def test_real_onnx_image_keeps_configuration_and_cleans_temporary_files(tmp_path):
    async def scenario():
        model_path = tmp_path / "person.onnx"
        _write_contract_model(model_path)
        pool = ModelPool(max_models=2)
        await pool.deploy(DeployModelRequest(
            modelVersionId=40, artifactPath=model_path,
            sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
            adapter="person_detection_v1", device="CPU",
        ))
        source = document()
        before = copy.deepcopy(source)
        recognizer = TaskImageRecognizer(tmp_path, pool, None)
        try:
            result = await recognizer.recognize(image_request(), source)
            assert result["objects"][0]["class"] == "person"
            assert result["objects"][0]["confidence"] == pytest.approx(0.95)
            assert result["sourceWidth"] == 320 and result["sourceHeight"] == 180
            assert result["revision"] == 7 and result["taskId"] == 1
            assert result["backend"] == "ONNX_RUNTIME"
            assert result["device"] == "CPU"
            empty_source = copy.deepcopy(source)
            empty_source["config"]["parameters"]["confidence"] = 1
            empty = await recognizer.recognize(image_request(), empty_source)
            assert empty["objects"] == []
            assert source == before
            assert not pool._pins
            assert not list(tmp_path.glob("image-test-*"))
            assert not (tmp_path / "tasks").exists()
            assert not (tmp_path / "events").exists()
        finally:
            await pool.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_supported_images_decode_without_resizing(format):
    with decode_image(image_request(format).image_base64) as image:
        assert image.size == (320, 180)


def test_rejects_invalid_oversized_and_animated_images():
    for value in ("not base64!", base64.b64encode(b"not an image").decode()):
        with pytest.raises(ImageRecognitionError, match="图片"):
            decode_image(value)
    with pytest.raises(ImageRecognitionError, match="JPG"):
        decode_image(image_request("GIF").image_base64)
    with pytest.raises(ImageRecognitionError, match="1600"):
        decode_image(image_request(size=(4001, 4000)).image_base64)
    with pytest.raises(ValidationError):
        TaskImageRequest(taskId=1, imageBase64="A" * 5_592_412)
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        buffer, "PNG", save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")]
    )
    with pytest.raises(ImageRecognitionError, match="动图"):
        decode_image(base64.b64encode(buffer.getvalue()).decode())


def test_exif_orientation_matches_browser_image():
    buffer = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (80, 40)).save(buffer, "JPEG", exif=exif)
    with decode_image(base64.b64encode(buffer.getvalue()).decode()) as image:
        assert image.size == (40, 80)


class Pool:
    def __init__(self):
        self.leases = 0
        self.calls = []
        self.failure = False

    async def acquire(self, ids, registry=None):
        self.leases += 1
        return tuple(ids)

    async def release(self, lease):
        self.leases -= 1

    def is_loaded(self, *args):
        return False

    async def test(self, request, image=None):
        self.calls.append((request.model_version_id, image.size))
        if self.failure:
            raise RuntimeError("private runtime path and credential must not be disclosed")
        objects = [DetectionObject.model_validate({
            "class": "license_plate", "confidence": 0.95,
            "bbox": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.1},
            "attributes": (
                {"plateText": "粤BF27861", "ocrConfidence": 0.98}
                if request.model_version_id == 41 else {}
            ),
        })]
        return ModelTestResult(
            sourceWidth=image.width, sourceHeight=image.height, objects=objects,
            backend="TEST", device="CPU", preprocessMillis=1,
            inferenceMillis=2, postprocessMillis=1,
        )


def test_plate_uses_cropped_ocr_but_never_accumulates_image_votes(tmp_path):
    async def scenario():
        pool = Pool()
        recognizer = TaskImageRecognizer(tmp_path, pool, None)
        source = document()
        source["config"]["pipeline"]["nodes"] = [
            {"id": "plate", "capabilityKey": "detector.license-plate"},
            {"id": "ocr", "capabilityKey": "ocr.license-plate"},
        ]
        source["config"]["modelBindings"] = {"plate": 40, "ocr": 41}
        for _ in range(4):
            result = await recognizer.recognize(image_request(), source)
            attrs = result["objects"][0]["attributes"]
            assert attrs["plateText"] == "粤BF27861"
            assert attrs["ocrStatus"] == "PENDING"
            assert "plateNumber" not in attrs
        assert pool.calls[0] == (40, (320, 180))
        assert pool.calls[1][0] == 41 and pool.calls[1][1][0] < 320
        assert pool.leases == 0
        assert not list(tmp_path.iterdir())
    asyncio.run(scenario())


def test_package_state_is_fresh_for_every_uploaded_image(tmp_path):
    descriptor = AlgorithmPackageStore(tmp_path).install(package("""class Algorithm:
 def __init__(self): self.count = 0
 def process(self, frame, sdk):
  self.count += 1
  return {'objects': [{**o, 'attributes': {'sampleCount': self.count}} for o in frame['objects']]}
"""))
    async def scenario():
        pool = Pool()
        recognizer = TaskImageRecognizer(tmp_path, pool, None)
        source = document()
        source["config"]["pipeline"]["algorithmPackage"] = descriptor
        source["config"]["modelBindings"] = {"person": 40}
        source["config"]["parameters"]["algorithm"] = {"limit": 0.4}
        for _ in range(2):
            result = await recognizer.recognize(image_request(), source)
            assert result["objects"][0]["attributes"]["sampleCount"] == 1
        assert pool.leases == 0
    asyncio.run(scenario())


def test_concurrent_requests_fail_fast_and_failures_allow_retry(tmp_path):
    async def scenario():
        pool = Pool()
        recognizer = TaskImageRecognizer(tmp_path, pool, None)
        async with recognizer._lock:
            with pytest.raises(ImageRecognitionError) as failure:
                await recognizer.recognize(image_request(), document())
            assert failure.value.code == 409
        pool.failure = True
        with pytest.raises(ImageRecognitionError) as failure:
            await recognizer.recognize(image_request(), document())
        assert failure.value.diagnostic_id
        assert "credential" not in str(failure.value)
        assert pool.leases == 0
        assert not list(tmp_path.iterdir())
        pool.failure = False
        assert (await recognizer.recognize(image_request(), document()))["objects"]
    asyncio.run(scenario())


def test_rpc_requires_authentication_and_rejects_task_config_in_upload(tmp_path):
    async def authenticate(request: Request):
        if request.headers.get("Authorization") != "Bearer image-test":
            raise HTTPException(401)

    class Service:
        async def recognize_image(self, value):
            if value.task_id != 1:
                raise KeyError(value.task_id)
            return await TaskImageRecognizer(tmp_path, Pool(), None).recognize(value, document())

    app = FastAPI()
    app.include_router(build_gateway_router(Service(), authenticate))
    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = image_request().model_dump(by_alias=True)
            body = {"action": "task.recognize-image", "payload": payload}
            assert (await client.post("/gateway/rpc", json=body)).status_code == 401
            client.headers["Authorization"] = "Bearer image-test"
            assert (await client.post("/gateway/rpc", json=body)).json()["ok"]
            payload["taskId"] = 2
            assert (await client.post("/gateway/rpc", json=body)).json()["code"] == 404
            payload["sourceUrl"] = "file:///private"
            assert (await client.post("/gateway/rpc", json=body)).json()["code"] == 422
    asyncio.run(scenario())


def test_timeout_releases_models_and_allows_next_image(tmp_path, monkeypatch):
    from ai_runtime.app.task import image_recognition

    class SlowPool(Pool):
        async def test(self, *args, **kwargs):
            await asyncio.sleep(1)
            return await super().test(*args, **kwargs)

    async def scenario():
        pool = SlowPool()
        recognizer = TaskImageRecognizer(tmp_path, pool, None)
        monkeypatch.setattr(image_recognition, "IMAGE_TEST_TIMEOUT_SECONDS", 0.02)
        with pytest.raises(ImageRecognitionError) as failure:
            await recognizer.recognize(image_request(), document())
        assert failure.value.code == 504
        assert pool.leases == 0
        assert not recognizer._lock.locked()
        assert not list(tmp_path.iterdir())
    asyncio.run(scenario())
