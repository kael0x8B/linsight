import hashlib
import sys
from pathlib import Path

import onnx
import pytest
from onnx import TensorProto, helper
from PIL import Image

from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestParameters
from ai_runtime.app.model.isolated import IsolatedAdapter


def test_worker_preserves_binary_rgb_pixels_geometry_and_releases(tmp_path):
    path = tmp_path / "color.onnx"
    graph = helper.make_graph(
        [
            helper.make_node("ReduceMean", ["image"], ["scores"], axes=[2, 3], keepdims=0),
        ],
        "color",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 32, 32])],
        [helper.make_tensor_value_info("scores", TensorProto.FLOAT, [1, 3])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 11)])
    model.ir_version = 10
    onnx.save(model, path)
    manifest = {
        "schemaVersion": "1.0",
        "taskType": "CLASSIFICATION",
        "preprocess": {
            "inputWidth": 32,
            "inputHeight": 32,
            "layout": "NCHW",
            "dtype": "FLOAT32",
            "scale": 1.0 / 255,
            "color": "RGB",
        },
        "decoder": {"type": "CLASSIFICATION", "labels": ["red", "green", "blue"]},
    }
    request = DeployModelRequest(
        modelVersionId=1,
        artifactPath=path,
        artifactFormat="ONNX",
        device="CPU",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        runtimeManifest=manifest,
    )
    worker = IsolatedAdapter(Path(sys.executable), request)
    parameters = ModelTestParameters(
        schemaVersion="1.0",
        confidence=0.25,
        nmsThreshold=0.45,
        inputWidth=32,
        inputHeight=32,
        outputCoordinates="NORMALIZED_XYWH",
    )
    try:
        source = Image.new("RGB", (96, 64), (255, 0, 0))
        image_path = tmp_path / "input.png"
        source.save(image_path)
        reference = worker.infer(str(image_path), parameters)
        red = worker.infer_image(source, parameters)
        blue = worker.infer_image(Image.new("RGB", (80, 60), (0, 0, 255)), parameters)
        assert red.objects == reference.objects
        assert red.objects[0].class_name == "red"
        assert (red.source_width, red.source_height) == (96, 64)
        assert blue.objects[0].class_name == "blue"
        assert (blue.source_width, blue.source_height) == (80, 60)
        assert worker.alive
    finally:
        worker.close()
    assert not worker.alive
    with pytest.raises(ValueError, match="退出"):
        worker.infer_image(Image.new("RGB", (10, 10)), parameters)
