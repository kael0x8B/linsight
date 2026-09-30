import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from ai_runtime.app.model import rknn
from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestParameters
from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.plate import PLATE_CHARACTERS, ChinesePlateOcrAdapter


def contract(npu=True):
    catalog = json.loads(
        (Path(__file__).parents[1] / "model_assets/chinese-plate-specialist-v1.json").read_text()
    )
    value = catalog["models"][1]["runtimeManifest"]
    if npu:
        value["preprocess"].update(
            layout="NHWC", dtype="UINT8", scale=1, mean=[0, 0, 0], std=[1, 1, 1]
        )
    return value


def outputs():
    indices = [0]
    for char in "吉WD0011":
        indices.extend([PLATE_CHARACTERS.index(char), 0])
    chars = np.full((1, len(indices), len(PLATE_CHARACTERS)), -8.0, dtype=np.float32)
    for step, index in enumerate(indices):
        chars[0, step, index] = 8
    # One weak character must remain weak on either backend.
    chars[0, 1, :] = 0
    chars[0, 1, PLATE_CHARACTERS.index("吉")] = 4
    return [chars, np.array([[0, 0, 5, 0, 0]], dtype=np.float32)]


def parameters():
    return ModelTestParameters(
        schemaVersion="1.0", confidence=0.5, nmsThreshold=0.5,
        inputWidth=640, inputHeight=640, outputCoordinates="NORMALIZED_XYWH",
    )


@pytest.mark.parametrize("sidebar", [False, True])
def test_cpu_npu_ocr_keep_identical_pixels_cropping_and_character_confidence(
    tmp_path, monkeypatch, sidebar
):
    captured = {}

    class SDK:
        def __init__(self, **_):
            pass

        def load_rknn(self, _path):
            return 0

        def init_runtime(self):
            return 0

        def inference(self, inputs, data_format):
            assert data_format == ["nhwc"]
            captured["npu"] = inputs[0].copy()
            return outputs()

        def release(self):
            captured["released"] = True

    class Session:
        def get_inputs(self):
            return [SimpleNamespace(name="image", shape=[1, 3, 48, 168])]

        def get_outputs(self):
            return [None, None]

        def run(self, _, inputs):
            captured["cpu"] = inputs["image"].copy()
            return outputs()

    monkeypatch.setattr(rknn, "require_rknn_sdk", lambda: SDK)
    image = Image.new("RGB", (168, 48), (20, 100, 90))
    if sidebar:
        image.paste((150, 155, 40), (8, 6, 18, 18))
        image.paste((150, 155, 40), (8, 28, 18, 40))
    image.paste("white", (23, 5, 35, 42))
    original = image.tobytes()
    cpu = ChinesePlateOcrAdapter(Session(), "CPU").infer_image(image, parameters())
    adapter = rknn.RknnAdapter(tmp_path / "ocr.rknn", RuntimeManifest.model_validate(contract()))
    npu = adapter.infer_image(image, parameters())
    assert captured["npu"].shape == (1, 48, 168, 3)
    assert captured["npu"].dtype == np.uint8
    assert captured["npu"][0, 0, 0].tolist() == [90, 100, 20]  # BGR, not RGB.
    normalized = ((captured["npu"].astype(np.float32) / 255 - 0.588) / 0.193)
    np.testing.assert_array_equal(normalized.transpose(0, 3, 1, 2), captured["cpu"])
    assert image.tobytes() == original
    assert npu.objects == cpu.objects
    attrs = npu.objects[0].attributes
    assert attrs["plateText"] == "吉WD0011"
    assert attrs["plateColor"] == "GREEN"
    assert attrs["ocrMinCharConfidence"] < 0.75
    assert attrs["ocrNumberRegionLeft"] == (18 / 168 if sidebar else 0)
    assert attrs["ocrLayout"] == ("YELLOW_SIDEBAR" if sidebar else "STANDARD")
    assert npu.device == "RKNPU"
    assert npu.backend == "RKNN_RUNTIME_MANIFEST_CHINESE_PLATE_CTC"
    assert (npu.source_width, npu.source_height) == image.size
    adapter.close()
    assert captured["released"]


@pytest.mark.parametrize("change", ["float_npu", "uint_cpu", "wrong_color", "wrong_size"])
def test_ocr_deployment_rejects_mismatched_execution_contract(tmp_path, change):
    manifest = copy.deepcopy(contract())
    request = dict(
        modelVersionId=1, artifactPath=tmp_path / "ocr.rknn", artifactFormat="RKNN",
        device="RKNPU", sha256="a" * 64, runtimeManifest=manifest,
    )
    if change == "float_npu":
        request["runtimeManifest"] = contract(False)
    elif change == "uint_cpu":
        request.update(artifactFormat="ONNX", device="CPU")
    elif change == "wrong_color":
        manifest["preprocess"]["color"] = "RGB"
    else:
        manifest["preprocess"]["inputWidth"] = 640
    with pytest.raises(ValueError, match="normalization|preprocessing"):
        DeployModelRequest.model_validate(request)


@pytest.mark.parametrize("bad", ["one_head", "swapped", "nan"])
def test_ocr_npu_rejects_invalid_outputs_without_fabricating_a_plate(tmp_path, monkeypatch, bad):
    heads = outputs()
    if bad == "one_head":
        heads = heads[:1]
    elif bad == "swapped":
        heads.reverse()
    else:
        heads[0][0, 0, 0] = np.nan
    sdk = SimpleNamespace(
        load_rknn=lambda _: 0, init_runtime=lambda: 0,
        inference=lambda **_: heads, release=lambda: None,
    )
    monkeypatch.setattr(rknn, "require_rknn_sdk", lambda: lambda **_: sdk)
    adapter = rknn.RknnAdapter(tmp_path / "ocr.rknn", RuntimeManifest.model_validate(contract()))
    with pytest.raises(ValueError, match="outputs|output|non-finite"):
        adapter.infer_image(Image.new("RGB", (168, 48)), parameters())
    adapter.close()
