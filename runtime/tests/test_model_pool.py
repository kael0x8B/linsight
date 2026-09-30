import asyncio
import hashlib
import zipfile

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from ai_runtime.app.model.backends import (
    LPRNET_CHARACTERS,
    decode_license_plate_yunet,
)
from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestRequest
from ai_runtime.app.model.pool import ModelPool


@pytest.mark.parametrize("fails", [False, True])
def test_file_only_model_receives_memory_crop_and_cleans_up(tmp_path, fails):
    from pathlib import Path

    from ai_runtime.app.model.contracts import ModelTestResult
    from ai_runtime.app.model.pool import PoolEntry

    paths = []

    class FileOnlyAdapter:
        def infer(self, image_path, parameters):
            paths.append(Path(image_path))
            with Image.open(image_path) as image:
                assert image.size == (62, 25)
                assert image.getpixel((31, 12)) == (12, 34, 56)
            if fails:
                raise ValueError("inference failed")
            return ModelTestResult(
                sourceWidth=62, sourceHeight=25, objects=[], backend="FILE_ONLY",
                device="CPU", preprocessMillis=0, inferenceMillis=1, postprocessMillis=0,
            )

    pool = ModelPool()
    pool._entries[(1, "CPU")] = PoolEntry(
        "a" * 64, "legacy", "ONNX", "FILE_ONLY", FileOnlyAdapter()
    )
    original = tmp_path / "unwritten-crop.png"
    request = ModelTestRequest.model_validate({
        "modelVersionId": 1, "imagePath": original,
        "parameters": {"schemaVersion": "1.0", "confidence": 0.5, "nmsThreshold": 0.5,
                       "inputWidth": 640, "inputHeight": 640,
                       "outputCoordinates": "NORMALIZED_XYWH"},
    })

    async def exercise():
        if fails:
            with pytest.raises(ValueError, match="inference failed"):
                await pool.test(request, image=Image.new("RGB", (62, 25), (12, 34, 56)))
        else:
            result = await pool.test(request, image=Image.new("RGB", (62, 25), (12, 34, 56)))
            assert result.source_width == 62
        assert not pool._pins
        await pool.close()

    asyncio.run(exercise())
    assert not original.exists()
    assert len(paths) == 1 and not paths[0].exists() and not paths[0].parent.exists()


def test_specialist_detector_uses_shared_original_pixels_without_reopening_jpeg(tmp_path):
    path = tmp_path / "plate.onnx"
    row = np.array(
        [[[320, 320, 200, 50, 0.9, 220, 295, 420, 295, 420, 345, 220, 345, 0.8, 0.1]]],
        dtype=np.float32,
    )
    graph = helper.make_graph(
        [
            helper.make_node("Constant", [], ["output"], value=numpy_helper.from_array(row)),
        ],
        "plate",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 640, 640])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 1, 15])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 12)])
    model.ir_version = 8
    onnx.save(model, path)
    pool = ModelPool()

    async def exercise():
        await pool.deploy(
            DeployModelRequest.model_validate(
                {
                    "modelVersionId": 1,
                    "artifactPath": path,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "runtimeManifest": {
                        "schemaVersion": "1.0",
                        "taskType": "OBJECT_DETECTION",
                        "preprocess": {
                            "inputWidth": 640,
                            "inputHeight": 640,
                            "color": "RGB",
                            "resize": "LETTERBOX",
                        },
                        "decoder": {"type": "YOLO_PLATE"},
                    },
                }
            )
        )
        result = await pool.test(
            ModelTestRequest.model_validate(
                {
                    "modelVersionId": 1,
                    "imagePath": tmp_path / "must-not-open.jpg",
                    "parameters": {
                        "schemaVersion": "1.0",
                        "confidence": 0.5,
                        "nmsThreshold": 0.5,
                        "inputWidth": 640,
                        "inputHeight": 640,
                        "outputCoordinates": "NORMALIZED_XYWH",
                    },
                }
            ),
            image=Image.new("RGB", (1280, 720)),
        )
        assert result.source_width == 1280 and result.source_height == 720
        assert result.objects[0].attributes["corner1Y"] == pytest.approx(310 / 720)
        await pool.close()

    asyncio.run(exercise())


def test_model_pool_executes_real_onnx_and_returns_standard_result(tmp_path) -> None:
    model_path = tmp_path / "person.onnx"
    image_path = tmp_path / "input.png"
    _write_contract_model(model_path)
    Image.new("RGB", (320, 180), color=(20, 30, 40)).save(image_path)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    pool = ModelPool(max_models=2)

    first = asyncio.run(
        pool.deploy(
            DeployModelRequest(
                modelVersionId=101,
                artifactPath=model_path,
                sha256=digest,
                adapter="person_detection_v1",
                device="CPU",
            )
        )
    )
    second = asyncio.run(
        pool.deploy(
            DeployModelRequest(
                modelVersionId=101,
                artifactPath=model_path,
                sha256=digest,
                adapter="person_detection_v1",
                device="CPU",
            )
        )
    )
    result = asyncio.run(
        pool.test(
            ModelTestRequest.model_validate(
                {
                    "modelVersionId": 101,
                    "imagePath": str(image_path),
                    "parameters": {
                        "schemaVersion": "1.0",
                        "confidence": 0.5,
                        "nmsThreshold": 0.5,
                        "inputWidth": 32,
                        "inputHeight": 32,
                        "outputCoordinates": "NORMALIZED_XYWH",
                    },
                }
            )
        )
    )

    assert first.reused is False
    assert second.reused is True
    assert pool.size == 1
    assert pool.capacity == 2
    assert result.source_width == 320
    assert result.source_height == 180
    assert len(result.objects) == 1
    assert result.objects[0].class_name == "person"
    assert result.objects[0].bbox.x == pytest.approx(0.1)


def test_manifest_executes_detection_without_business_adapter(tmp_path) -> None:
    model_path = tmp_path / "generic.onnx"
    image_path = tmp_path / "input.png"
    _write_contract_model(model_path)
    Image.new("RGB", (96, 64), color=(20, 30, 40)).save(image_path)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    request = DeployModelRequest.model_validate(
        {
            "modelVersionId": 909,
            "artifactPath": str(model_path),
            "sha256": digest,
            "runtimeManifest": {
                "schemaVersion": "1.0",
                "taskType": "OBJECT_DETECTION",
                "preprocess": {
                    "inputWidth": 32,
                    "inputHeight": 32,
                    "color": "RGB",
                    "layout": "NCHW",
                    "dtype": "FLOAT32",
                },
                "decoder": {"type": "AUTO_DETECTION", "labels": ["worker"]},
            },
        }
    )
    pool = ModelPool()

    deployed = asyncio.run(pool.deploy(request))
    result = asyncio.run(
        pool.test(
            ModelTestRequest.model_validate(
                {
                    "modelVersionId": 909,
                    "imagePath": str(image_path),
                    "parameters": {
                        "schemaVersion": "1.0",
                        "confidence": 0.5,
                        "nmsThreshold": 0.5,
                        "inputWidth": 32,
                        "inputHeight": 32,
                        "outputCoordinates": "NORMALIZED_XYWH",
                    },
                }
            )
        )
    )

    assert deployed.backend == "ONNX_RUNTIME_MANIFEST"
    assert result.objects[0].class_name == "worker"


def test_deploy_requires_manifest_or_legacy_adapter(tmp_path) -> None:
    model_path = tmp_path / "generic.onnx"
    _write_contract_model(model_path)

    with pytest.raises(ValueError, match="runtimeManifest"):
        DeployModelRequest.model_validate(
            {
                "modelVersionId": 909,
                "artifactPath": str(model_path),
                "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            }
        )


def test_rknn_dfl_decoder_never_treats_80_class_tensor_as_boxes() -> None:
    from ai_runtime.app.model.person import decode_detection_rows

    box_head = np.zeros((1, 64, 2, 2), dtype=np.float32)
    class_head = np.zeros((1, 80, 2, 2), dtype=np.float32)
    objectness = np.zeros((1, 1, 2, 2), dtype=np.float32)

    rows = decode_detection_rows(
        [box_head, class_head, objectness],
        input_width=32,
        input_height=32,
        class_count=80,
        min_confidence=0.5,
    )

    assert rows.shape == (0, 6)


def test_model_pool_rejects_sha_mismatch(tmp_path) -> None:
    model_path = tmp_path / "person.onnx"
    _write_contract_model(model_path)
    pool = ModelPool()

    try:
        asyncio.run(
            pool.deploy(
                DeployModelRequest(
                    modelVersionId=101,
                    artifactPath=model_path,
                    sha256="0" * 64,
                    adapter="person_detection_v1",
                    device="CPU",
                )
            )
        )
        raise AssertionError("expected SHA mismatch")
    except ValueError as error:
        assert "SHA256" in str(error)


def test_same_version_and_hash_with_different_adapter_is_not_reused(tmp_path) -> None:
    model_path = tmp_path / "contract.onnx"
    _write_contract_model(model_path)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    pool = ModelPool()
    person_request = DeployModelRequest(
        modelVersionId=101,
        artifactPath=model_path,
        sha256=digest,
        adapter="person_detection_v1",
        device="CPU",
    )
    flame_request = person_request.model_copy(update={"adapter": "flame_detection_v1"})

    assert asyncio.run(pool.deploy(person_request)).reused is False
    assert asyncio.run(pool.deploy(flame_request)).reused is False


def test_model_pool_loads_single_onnx_member_from_archive(tmp_path) -> None:
    model_path = tmp_path / "contract.onnx"
    archive_path = tmp_path / "contract.zip"
    _write_contract_model(model_path)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(model_path, "models/contract.onnx")
    pool = ModelPool()

    response = asyncio.run(
        pool.deploy(
            DeployModelRequest.model_validate(
                {
                    "modelVersionId": 303,
                    "artifactPath": archive_path,
                    "artifactFormat": "ARCHIVE",
                    "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                    "adapter": "person_detection_v1",
                }
            )
        )
    )

    assert response.backend == "ONNX_RUNTIME"
    assert pool.is_loaded(303)


def test_model_pool_rejects_untrusted_pytorch_checkpoint_before_loading(tmp_path) -> None:
    checkpoint = tmp_path / "custom.pt"
    with zipfile.ZipFile(checkpoint, "w") as archive:
        archive.writestr("archive/data.pkl", b"ultralytics")
    pool = ModelPool()

    with pytest.raises(ValueError, match="PRESET"):
        asyncio.run(
            pool.deploy(
                DeployModelRequest.model_validate(
                    {
                        "modelVersionId": 304,
                        "artifactPath": checkpoint,
                        "artifactFormat": "PYTORCH",
                        "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                        "adapter": "person_detection_v1",
                        "trustedArtifact": False,
                    }
                )
            )
        )


@pytest.mark.parametrize(
    ("adapter", "expected_class"),
    [
        ("safety_helmet_v1", "person"),
        ("reflective_vest_v1", "person"),
        ("smoking_detection_v1", "smoking"),
        ("phone_call_detection_v1", "phone_call"),
        ("flame_detection_v1", "flame"),
        ("fall_detection_v1", "fall"),
        ("vehicle_detection_v1", "car"),
        ("coco_detection_v1", "person"),
        ("unified_ppe_detection_v1", "person"),
        ("smoking_phone_detection_v1", "person"),
        ("flame_smoke_detection_v1", "flame"),
        ("garbage_debris_detection_v1", "garbage"),
        ("vehicle_type_detection_v1", "sedan"),
    ],
)
def test_controlled_adapters_standardize_class_zero(
    tmp_path, adapter: str, expected_class: str
) -> None:
    model_path = tmp_path / f"{adapter}.onnx"
    image_path = tmp_path / "input.png"
    _write_contract_model(model_path)
    Image.new("RGB", (64, 64)).save(image_path)
    pool = ModelPool()
    asyncio.run(
        pool.deploy(
            DeployModelRequest.model_validate(
                {
                    "modelVersionId": 202,
                    "artifactPath": str(model_path),
                    "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                    "adapter": adapter,
                    "device": "CPU",
                }
            )
        )
    )
    result = asyncio.run(
        pool.test(
            ModelTestRequest.model_validate(
                {
                    "modelVersionId": 202,
                    "imagePath": str(image_path),
                    "parameters": {
                        "schemaVersion": "1.0",
                        "confidence": 0.5,
                        "nmsThreshold": 0.5,
                        "inputWidth": 32,
                        "inputHeight": 32,
                        "outputCoordinates": "NORMALIZED_XYWH",
                    },
                }
            )
        )
    )

    assert result.objects[0].class_name == expected_class


def test_lprnet_adapter_decodes_mainland_chinese_plate_and_confidence(tmp_path) -> None:
    model_path = tmp_path / "lprnet.onnx"
    image_path = tmp_path / "plate.png"
    expected = "湘F6CL03"
    blank = len(LPRNET_CHARACTERS) - 1
    sequence = [blank]
    for character in expected:
        sequence.extend([LPRNET_CHARACTERS.index(character), blank])
    logits = np.full((1, len(LPRNET_CHARACTERS), len(sequence)), -10.0, dtype=np.float32)
    for timestep, index in enumerate(sequence):
        logits[0, index, timestep] = 10.0
    graph = helper.make_graph(
        [
            helper.make_node(
                "Constant", inputs=[], outputs=["output"], value=numpy_helper.from_array(logits)
            )
        ],
        "lprnet-contract-model",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 24, 94])],
        [
            helper.make_tensor_value_info(
                "output", TensorProto.FLOAT, [1, len(LPRNET_CHARACTERS), len(sequence)]
            )
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 10
    onnx.save(model, model_path)
    Image.new("RGB", (188, 48), color=(20, 30, 40)).save(image_path)
    pool = ModelPool()
    asyncio.run(
        pool.deploy(
            DeployModelRequest.model_validate(
                {
                    "modelVersionId": 909,
                    "artifactPath": model_path,
                    "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                    "adapter": "license_plate_ocr_v1",
                }
            )
        )
    )

    result = asyncio.run(
        pool.test(
            ModelTestRequest.model_validate(
                {
                    "modelVersionId": 909,
                    "imagePath": image_path,
                    "parameters": {
                        "schemaVersion": "1.0",
                        "confidence": 0.5,
                        "nmsThreshold": 0.5,
                        "inputWidth": 640,
                        "inputHeight": 640,
                        "outputCoordinates": "NORMALIZED_XYWH",
                    },
                }
            )
        )
    )

    assert result.backend == "ONNX_RUNTIME_LPRNET"
    assert result.objects[0].attributes["plateText"] == expected
    assert result.objects[0].attributes["ocrCharset"] == "CHINESE_MAINLAND"
    assert result.objects[0].attributes["ocrConfidence"] > 0.99


def test_license_plate_yunet_decoder_returns_quadrilateral() -> None:
    priors = np.array([[0.5, 0.5, 0.2, 0.1]], dtype=np.float32)
    loc = np.zeros((1, 14), dtype=np.float32)
    loc[0, 4:8] = [-5, -5, 5, -5]
    loc[0, 10:14] = [5, 5, -5, 5]
    conf = np.array([[0.1, 0.9]], dtype=np.float32)
    iou = np.array([[1.0]], dtype=np.float32)

    objects = decode_license_plate_yunet(loc, conf, iou, priors, 0.5, 0.5)

    assert len(objects) == 1
    detected = objects[0]
    assert detected.class_name == "license_plate"
    assert detected.confidence == pytest.approx(0.948683, abs=1e-6)
    assert detected.attributes["rectificationSource"] == "YUNET_QUADRILATERAL"
    assert detected.attributes["corner1X"] == pytest.approx(0.4)
    assert detected.attributes["corner4Y"] == pytest.approx(0.55)


def _write_contract_model(path) -> None:
    detections = np.array(
        [
            [
                [0.1, 0.2, 0.4, 0.5, 0.95, 0.0],
                [0.12, 0.22, 0.4, 0.5, 0.85, 0.0],
                [0.7, 0.1, 0.2, 0.2, 0.2, 0.0],
            ]
        ],
        dtype=np.float32,
    )
    graph = helper.make_graph(
        [
            helper.make_node(
                "Constant",
                inputs=[],
                outputs=["detections"],
                value=numpy_helper.from_array(detections),
            )
        ],
        "person-contract-model",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 32, 32])],
        [helper.make_tensor_value_info("detections", TensorProto.FLOAT, [1, 3, 6])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 10
    onnx.save(model, path)


def test_face_quality_rejection_keeps_actual_execution_device(monkeypatch):
    from types import SimpleNamespace

    from ai_runtime.app.model.face_pair import FaceQualityError, RknnFacePairAdapter

    pool = ModelPool(max_models=2)
    adapter = object.__new__(RknnFacePairAdapter)

    async def borrow(version):
        return (version, "RKNPU"), SimpleNamespace(adapter=adapter)

    async def inference(*args):
        raise FaceQualityError("NO_FACE")

    monkeypatch.setattr(pool, "_borrow", borrow)
    monkeypatch.setattr(pool, "_inference", inference)
    with pytest.raises(FaceQualityError) as caught:
        asyncio.run(pool.extract_face(131, Image.new("RGB", (10, 10))))
    assert caught.value.device == "RKNPU"
    assert caught.value.backend == "RKNN_FACE_PAIR_SFACE"
    assert str(caught.value) == "NO_FACE"
