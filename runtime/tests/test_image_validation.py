import asyncio
import hashlib
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from test_model_pool import _write_contract_model
from test_task_image_recognition import document, image_request

from ai_runtime.app.gateway.api import build_gateway_router
from ai_runtime.app.gateway.store import GatewayStore
from ai_runtime.app.model.contracts import DeployModelRequest
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.task.contracts import TaskStartRequest
from ai_runtime.app.task.image_recognition import ImageRecognitionError, TaskImageRecognizer
from ai_runtime.app.task.validation import ExpectedResult, ImageValidationService, compare


def gateway(tmp_path, pool=None):
    store = GatewayStore(tmp_path / "gateway")
    config = document()
    store.save(config, str(uuid4()), "fixture")
    model = {
        "modelVersionId": 40,
        "sha256": "a" * 64,
        "version": "1",
        "adapter": "person_detection_v1",
    }
    result = SimpleNamespace(
        store=store,
        settings=SimpleNamespace(runtime_data_root=tmp_path),
        models=SimpleNamespace(summaries=lambda: [model]),
        image_recognizer=TaskImageRecognizer(tmp_path, pool, None),
        _validate=TaskStartRequest.model_validate,
    )
    result.image_validation = ImageValidationService(result)
    return result, model


async def dataset(service):
    create = {
        "id": str(uuid4()),
        "requestId": str(uuid4()),
        "expectedRevision": 0,
        "name": "现场回归集",
    }
    value = await service.invoke("validation.save", create)
    upload = {
        "id": value["id"],
        "requestId": str(uuid4()),
        "expectedRevision": 1,
        "sampleId": str(uuid4()),
        "name": "现场.png",
        "note": "测试备注",
        "expected": {"category": "person", "count": 1, "confidence": 0.5, "text": ""},
        "imageBase64": image_request().image_base64,
    }
    return await service.invoke("validation.sample-save", upload), upload


async def start(service, value):
    change = {
        "id": value["id"],
        "expectedRevision": value["revision"],
        "requestId": str(uuid4()),
        "taskId": 1,
        "taskRevision": 7,
    }
    return await service.invoke("validation.run-create", change), change


def test_real_onnx_reusable_snapshot_history_and_chunked_images(tmp_path):
    async def scenario():
        path = tmp_path / "person.onnx"
        _write_contract_model(path)
        pool = ModelPool(max_models=2)
        await pool.deploy(
            DeployModelRequest(
                modelVersionId=40,
                artifactPath=path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                adapter="person_detection_v1",
                device="CPU",
            )
        )
        host, model = gateway(tmp_path, pool)
        model["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        service = host.image_validation
        try:
            before = host.store.get(1)
            value, upload = await dataset(service)
            run, change = await start(service, value)
            assert "_configuration" not in run
            assert "sourceUrl" not in str(run)
            assert (await service.invoke("validation.run-create", change))["id"] == run["id"]
            # Editing the expectation after launch never rewrites the run snapshot.
            edit = {
                **upload,
                "expectedRevision": 2,
                "requestId": str(uuid4()),
                "expected": {"category": "person", "count": 0},
            }
            edit.pop("imageBase64")
            edited = await service.invoke("validation.sample-save", edit)
            item = {"id": run["id"], "sampleId": upload["sampleId"]}
            first = await service.invoke("validation.run-item", item)
            assert first["status"] == "PASS"
            assert first["result"]["backend"] == "ONNX_RUNTIME"
            assert first["actualCount"] == 1
            assert await service.invoke("validation.run-item", item) == first
            assert (await service.invoke("validation.result", item))["result"]["objects"]
            summary = await service.invoke("validation.run-get", {"id": run["id"]})
            assert summary["items"][0]["result"]["objects"] == []
            second, _ = await start(service, edited)
            second_item = await service.invoke("validation.run-item", {**item, "id": second["id"]})
            assert second_item["status"] == "FAIL"
            chunk = await service.invoke("validation.image", {**item, "offset": 0})
            assert chunk["imageBase64"] == upload["imageBase64"]
            assert chunk["length"] == chunk["size"]
            assert host.store.get(1) == before
            assert not pool._pins
            host.store.close()
            reopened = GatewayStore(tmp_path / "gateway")
            assert reopened.validation.get(run["id"])["items"][0]["status"] == "PASS"
            assert len(reopened.validation.list("run", value["id"])) == 2
            reopened.close()
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_validation_conflicts_idempotency_limits_and_version_pin(tmp_path):
    async def scenario():
        host, model = gateway(tmp_path)
        service = host.image_validation
        value, upload = await dataset(service)
        assert await service.invoke("validation.sample-save", upload) == value
        with pytest.raises(ImageRecognitionError, match="请求编号"):
            await service.invoke("validation.sample-save", {**upload, "note": "changed"})
        with pytest.raises(ImageRecognitionError, match="已修改"):
            await service.invoke("validation.sample-save", {**upload, "requestId": str(uuid4())})
        run, change = await start(service, value)
        with pytest.raises(ImageRecognitionError, match="任务版本"):
            await service.invoke(
                "validation.run-create", {**change, "requestId": str(uuid4()), "taskRevision": 6}
            )
        with pytest.raises(ImageRecognitionError, match="尚未部署"):
            await service.invoke(
                "validation.run-create",
                {
                    **change,
                    "requestId": str(uuid4()),
                    "modelBindings": {
                        next(iter(host.store.get(1)["config"]["modelBindings"])): 999
                    },
                },
            )
        model["sha256"] = "b" * 64
        item = await service.invoke(
            "validation.run-item", {"id": run["id"], "sampleId": upload["sampleId"]}
        )
        assert item["status"] == "ERROR" and "改变" in item["error"]
        with pytest.raises(KeyError):
            await service.invoke("validation.image", {"id": value["id"], "sampleId": str(uuid4())})
        host.store.close()

    asyncio.run(scenario())


def test_recovery_and_delete_only_owned_media(tmp_path):
    async def scenario():
        host, _ = gateway(tmp_path)
        value, upload = await dataset(host.image_validation)
        run, _ = await start(host.image_validation, value)
        doc = host.store.validation.get(run["id"])
        doc["items"][0]["status"] = "RUNNING"
        host.store.validation.put(doc)
        host.store.close()
        other = GatewayStore(tmp_path / "gateway")
        assert other.validation.get(run["id"])["items"][0]["status"] == "ERROR"
        host.store = other
        service = ImageValidationService(host)
        await service.invoke(
            "validation.delete",
            {"id": value["id"], "expectedRevision": 2, "requestId": str(uuid4())},
        )
        assert not other.validation.list("set") and not other.validation.list("run")
        assert not list(other.validation.root.iterdir())
        assert other.get(1) is not None
        other.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("expected", "result", "status"),
    [
        ({"count": 0}, {"objects": []}, "PASS"),
        ({"count": 1}, {"objects": []}, "FAIL"),
        ({"count": 0}, {"objects": [], "observationValid": False}, "INCONCLUSIVE"),
        (
            {"category": "person", "count": 0},
            {"objects": [{"class": "car", "confidence": 0.9}]},
            "PASS",
        ),
        (
            {"category": "person", "count": 0},
            {"objects": [{"class": "person", "confidence": 0.4}]},
            "PASS",
        ),
        (
            {"text": "苏A12345", "count": 1},
            {
                "objects": [
                    {"class": "plate", "confidence": 0.9, "attributes": {"plateText": "苏A12345"}}
                ]
            },
            "PASS",
        ),
    ],
)
def test_comparison(expected, result, status):
    assert compare(ExpectedResult.model_validate(expected).model_dump(), result)[0] == status


def test_comparison_ignores_explicitly_hidden_diagnostic_candidates():
    expected = ExpectedResult.model_validate(
        {"category": "license_plate", "count": 1, "confidence": 0.5}
    ).model_dump()
    result = {
        "objects": [
            {
                "class": "license_plate",
                "confidence": 0.77,
                "attributes": {
                    "plateText": "京A26797D",
                    "ocrStatus": "PENDING",
                    "visibleByDefault": True,
                },
            },
            {
                "class": "license_plate",
                "confidence": 0.53,
                "attributes": {
                    "plateText": "SDTCXF",
                    "ocrStatus": "LOW_CHAR_CONFIDENCE",
                    "visibleByDefault": False,
                },
            },
        ]
    }

    assert compare(expected, result) == ("PASS", 1)


def test_comparison_uses_final_ocr_confidence_for_visible_plate():
    expected = ExpectedResult.model_validate(
        {"category": "license_plate", "count": 1, "confidence": 0.5}
    ).model_dump()
    result = {
        "objects": [
            {
                "class": "license_plate",
                "confidence": 0.3046,
                "attributes": {
                    "plateText": "京A25662D",
                    "ocrConfidence": 0.9994,
                    "ocrStatus": "PENDING",
                    "visibleByDefault": True,
                },
            }
        ]
    }

    assert compare(expected, result) == ("PASS", 1)


def test_rpc_authentication_and_rejecting_configuration_injection(tmp_path):
    host, _ = gateway(tmp_path)

    async def scenario():
        app = FastAPI()
        app.include_router(build_gateway_router(host, lambda: None), prefix="/v1")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/gateway/rpc",
                json={
                    "action": "validation.save",
                    "payload": {
                        "id": str(uuid4()),
                        "requestId": str(uuid4()),
                        "expectedRevision": 0,
                        "name": "test",
                        "configuration": {"sourceUrl": "file:///private"},
                    },
                },
            )
            assert response.json()["code"] == 422

        def deny():
            raise HTTPException(401)

        protected = FastAPI()
        protected.include_router(build_gateway_router(host, deny), prefix="/v1")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=protected), base_url="http://test"
        ) as client:
            assert (
                await client.post("/v1/gateway/rpc", json={"action": "validation.list"})
            ).status_code == 401

    asyncio.run(scenario())
    host.store.close()


def test_batch_failures_concurrency_and_removed_sample_history(tmp_path):
    async def scenario():
        host, _ = gateway(tmp_path)
        service = host.image_validation
        value, upload = await dataset(service)
        run, _ = await start(service, value)
        await service.lock.acquire()
        try:
            with pytest.raises(ImageRecognitionError, match="正在运行"):
                await service.invoke(
                    "validation.run-item", {"id": run["id"], "sampleId": upload["sampleId"]}
                )
            with pytest.raises(ImageRecognitionError, match="进行中"):
                await service.invoke(
                    "validation.delete",
                    {"id": value["id"], "expectedRevision": 2, "requestId": str(uuid4())},
                )
        finally:
            service.lock.release()
        with pytest.raises(ImageRecognitionError, match="图片"):
            await service.invoke(
                "validation.sample-save",
                {
                    **upload,
                    "expectedRevision": 2,
                    "requestId": str(uuid4()),
                    "imageBase64": "invalid!",
                },
            )
        assert len(service.repo.get(value["id"])["samples"]) == 1
        removed = await service.invoke(
            "validation.sample-delete",
            {
                "id": value["id"],
                "expectedRevision": 2,
                "requestId": str(uuid4()),
                "sampleId": upload["sampleId"],
            },
        )
        assert not removed["samples"]
        assert (
            await service.invoke(
                "validation.image", {"id": run["id"], "sampleId": upload["sampleId"]}
            )
        )["length"] > 0
        assert service.repo.get(run["id"])["items"][0]["expected"]["count"] == 1
        host.store.close()

    asyncio.run(scenario())


def test_cancelled_inference_is_persisted_and_safe_to_replay(tmp_path):
    async def scenario():
        host, _ = gateway(tmp_path)
        service = host.image_validation
        value, upload = await dataset(service)
        run, _ = await start(service, value)

        async def cancel(*_args):
            raise asyncio.CancelledError()

        host.image_recognizer.recognize = cancel
        item = {"id": run["id"], "sampleId": upload["sampleId"]}
        with pytest.raises(asyncio.CancelledError):
            await service.invoke("validation.run-item", item)
        assert (await service.invoke("validation.run-item", item))["status"] == "ERROR"
        assert not service.lock.locked()
        host.store.close()

    asyncio.run(scenario())


def test_algorithm_version_selection_does_not_change_task(tmp_path):
    from types import MethodType

    from test_algorithm_packages import package
    from test_task_image_recognition import Pool

    from ai_runtime.app.capability.packages import AlgorithmPackageStore
    from ai_runtime.app.gateway.service import GatewayService

    async def scenario():
        host, model = gateway(tmp_path, Pool())
        model["runtimeManifest"] = {"taskType": "DETECTION", "decoder": {"labels": ["person"]}}
        packages = AlgorithmPackageStore(tmp_path)
        first = packages.install(package())
        second = packages.install(package(version="2.0.0"))
        source = host.store.get(1)
        source["config"]["pipeline"]["algorithmPackage"] = first
        source["config"]["modelBindings"] = {"person": 40}
        source["config"]["parameters"]["algorithm"] = {"limit": 0.4}
        host.store.save(source, str(uuid4()), "algorithm-fixture")
        host._validate = MethodType(GatewayService._validate, host)
        service = host.image_validation
        value, _ = await dataset(service)
        change = {
            "id": value["id"],
            "expectedRevision": 2,
            "requestId": str(uuid4()),
            "taskId": 1,
            "taskRevision": 7,
            "algorithmSha256": second["sha256"],
        }
        run = await service.invoke("validation.run-create", change)
        assert run["target"]["algorithm"]["manifest"]["version"] == "2.0.0"
        assert host.store.get(1) == source
        host.store.close()

    asyncio.run(scenario())
