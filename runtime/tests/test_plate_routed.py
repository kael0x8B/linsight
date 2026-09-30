import asyncio
import hashlib
import json
import zipfile
from types import SimpleNamespace

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from ai_runtime.app.model.contracts import DeployModelRequest, ModelTestParameters, ModelTestRequest
from ai_runtime.app.model.manifest import RuntimeManifest
from ai_runtime.app.model.plate_routed import PaddlePlateTextRecognizer, RoutedPlateOcrAdapter
from ai_runtime.app.model.pool import ModelPool, _load_adapter

CHARS = "吉WD01·-两V"


class SiteSession:
    def __init__(self, text="吉W·D0010"):
        self.text = text
        self.input_tensor = None

    def get_inputs(self):
        return [SimpleNamespace(name="x", shape=[1, 3, 48, "width"], type="tensor(float)")]

    def get_outputs(self):
        return [SimpleNamespace(shape=[1, "time", len(CHARS) + 2])]

    def get_modelmeta(self):
        return SimpleNamespace(custom_metadata_map={"character": "\n".join(CHARS)})

    def run(self, _, inputs):
        self.input_tensor = inputs["x"]
        return [_probabilities(self.text)]


def _probabilities(text):
    values = np.zeros((1, len(text) * 2, len(CHARS) + 2), np.float32)
    for index, char in enumerate(text):
        values[0, index * 2, CHARS.index(char) + 1] = 1
        values[0, index * 2 + 1, 0] = 1
    return values


def _parameters():
    return ModelTestParameters(
        schemaVersion="1.0", confidence=0.5, nmsThreshold=0.5,
        inputWidth=640, inputHeight=640, outputCoordinates="NORMALIZED_XYWH",
    )


def _manifest():
    return RuntimeManifest.model_validate({
        "schemaVersion": "1.0", "taskType": "OCR",
        "preprocess": {
            "inputWidth": 320, "inputHeight": 48, "color": "BGR",
            "resize": "OCR_RIGHT_PAD", "mean": [0.5] * 3, "std": [0.5] * 3,
        },
        "decoder": {"type": "PLATE_OCR_ROUTED"},
    })


def test_paddle_prepare_preserves_width_channels_and_padding():
    image = Image.new("RGB", (100, 40), (255, 128, 0))
    tensor = PaddlePlateTextRecognizer.prepare(image)
    assert tensor.shape == (1, 3, 48, 320)
    assert tensor.dtype == np.float32
    assert np.allclose(tensor[0, :, 24, 50], [-1, 128 / 127.5 - 1, 1], atol=1e-7)
    assert np.all(tensor[:, :, :, 120:] == 0)
    assert image.size == (100, 40)  # The caller retains its frame/crop.
    with pytest.raises(ValueError, match="aspect ratio"):
        PaddlePlateTextRecognizer.prepare(Image.new("RGB", (1025, 48)))


def test_ctc_keeps_repeated_digits_and_excludes_separator_from_confidence():
    recognizer = PaddlePlateTextRecognizer(SiteSession())
    scores = _probabilities("吉W·D0010")
    scores[0, 4, :] = 0
    scores[0, 4, CHARS.index("·") + 1] = 0.51
    scores[0, 4, 0] = 0.49
    text, raw, average, minimum = recognizer.decode(scores)
    assert text == "吉WD0010" and raw == "吉W·D0010"
    assert average == minimum == 1
    # Repeated labels collapse only without the intervening blank.
    assert recognizer.decode(np.repeat(scores, 2, axis=1))[0] == text


@pytest.mark.parametrize("text", ["两吉W-D0010", "吉VD0010"])
def test_decoder_never_deletes_prefix_or_substitutes_letters(text):
    recognizer = PaddlePlateTextRecognizer(SiteSession())
    assert recognizer.decode(_probabilities(text))[0] == text.replace("-", "")


@pytest.mark.parametrize("kind", ["transpose", "nan", "negative", "logits", "classes"])
def test_malformed_probabilities_are_rejected(kind):
    recognizer = PaddlePlateTextRecognizer(SiteSession())
    scores = _probabilities("吉W")
    if kind == "transpose":
        scores = scores.transpose(0, 2, 1)
    elif kind == "nan":
        scores[0, 0, 0] = np.nan
    elif kind == "negative":
        scores[0, 0, 0] = -0.1
    elif kind == "logits":
        scores += 1
    else:
        scores = scores[:, :, :-1]
    with pytest.raises(ValueError, match="normalized"):
        recognizer.decode(scores)


@pytest.mark.parametrize("metadata", [{}, {"character": ""}, {"character": "吉\n吉"}])
def test_missing_or_ambiguous_charset_is_rejected(metadata):
    session = SiteSession()
    session.get_modelmeta = lambda: SimpleNamespace(custom_metadata_map=metadata)
    with pytest.raises(ValueError, match="dictionary"):
        PaddlePlateTextRecognizer(session)


def test_unknown_marker_uses_specialist_unchanged(monkeypatch):
    from ai_runtime.app.model import plate_routed

    image = Image.new("RGB", (168, 48), "blue")
    sentinel = object()
    calls = []

    class Specialist:
        def infer_image(self, source, parameters):
            calls.append(source)
            return sentinel

    adapter = RoutedPlateOcrAdapter.__new__(RoutedPlateOcrAdapter)
    adapter._specialist = Specialist()
    adapter._site = None
    monkeypatch.setattr(plate_routed, "plate_number_region", lambda source: (source.copy(), 0))
    assert adapter.infer_image(image, _parameters()) is sentinel
    assert calls == [image]
    assert image.getpixel((0, 0)) == (0, 0, 255)


def test_positive_marker_routes_site_with_explicit_retry_evidence(monkeypatch):
    from ai_runtime.app.model import plate_routed

    image = Image.new("RGB", (180, 48), "green")
    adapter = RoutedPlateOcrAdapter.__new__(RoutedPlateOcrAdapter)
    adapter._specialist = None
    adapter._site = PaddlePlateTextRecognizer(SiteSession())
    monkeypatch.setattr(
        plate_routed, "plate_number_region", lambda source: (source.crop((20, 0, 180, 48)), 20)
    )
    result = adapter.infer_image(image, _parameters())
    attrs = result.objects[0].attributes
    assert attrs["plateText"] == "吉WD0010"
    assert attrs["ocrRawText"] == "吉W·D0010"
    assert attrs["ocrLayout"] == "YELLOW_SIDEBAR"
    assert attrs["ocrNumberRegionLeft"] == 20 / 180
    assert attrs["ocrMinCharConfidence"] == 1


@pytest.mark.parametrize("field,value", [("color", "RGB"), ("resize", "STRETCH"),
                                        ("inputWidth", 168), ("dtype", "UINT8")])
def test_manifest_rejects_incompatible_preprocessing(field, value):
    payload = _manifest().model_dump(by_alias=True)
    payload["preprocess"][field] = value
    with pytest.raises(ValueError):
        RuntimeManifest.model_validate(payload)


def _constant_model(path, input_shape, values, charset=None):
    nodes = [
        helper.make_node("Constant", [], [f"out{i}"], value=numpy_helper.from_array(value))
        for i, value in enumerate(values)
    ]
    graph = helper.make_graph(
        nodes, "test", [helper.make_tensor_value_info("x", TensorProto.FLOAT, input_shape)],
        [helper.make_tensor_value_info(f"out{i}", TensorProto.FLOAT, list(value.shape))
         for i, value in enumerate(values)],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 12)])
    model.ir_version = 8
    if charset:
        helper.set_model_props(model, {"character": "\n".join(charset)})
    onnx.save(model, path)


def test_archive_pool_loads_fixed_pair_without_dependency_installs(tmp_path):
    specialist = tmp_path / "specialist.onnx"
    site = tmp_path / "site.onnx"
    _constant_model(specialist, [1, 3, 48, 168],
                    [np.zeros((1, 2, 78), np.float32), np.zeros((1, 5), np.float32)])
    _constant_model(site, [1, 3, 48, "width"], [_probabilities("吉WD0010")], CHARS)
    archive = tmp_path / "routed.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(specialist, specialist.name)
        bundle.write(site, site.name)
        bundle.writestr("metadata.json", json.dumps({"source": "test"}))

    class NoInstall:
        async def ensure(self, artifact_format):
            raise AssertionError("Pure ONNX routed bundle must not install Python dependencies")

        async def close(self):
            pass

    pool = ModelPool(dependencies=NoInstall())

    async def exercise():
        result = await pool.deploy(DeployModelRequest(
            modelVersionId=1, artifactPath=archive, artifactFormat="ARCHIVE",
            sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), runtimeManifest=_manifest(),
        ))
        assert result.backend == "ONNX_RUNTIME_PLATE_OCR_ROUTED"
        baseline = await pool.test(
            ModelTestRequest(modelVersionId=1, imagePath=tmp_path / "unused.png",
                             parameters=_parameters()),
            image=Image.new("RGB", (168, 48), "blue"),
        )
        assert baseline.backend == "ONNX_RUNTIME_CHINESE_PLATE_CTC"
        await pool.close()

    asyncio.run(exercise())


def test_routed_adapter_requires_archive_and_exact_members(tmp_path):
    with pytest.raises(ValueError, match="CPU ARCHIVE"):
        _load_adapter(tmp_path, "ONNX", "CPU", "", _manifest(), False, "a" * 64)
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("other.onnx", b"bad")
    with pytest.raises(ValueError, match="specialist.onnx and site.onnx"):
        _load_adapter(archive, "ARCHIVE", "CPU", "", _manifest(), False, "b" * 64)
