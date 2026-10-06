import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "asset_sync", Path(__file__).parents[1] / "sync-builtin-model-assets.py",
)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def test_matching_upstream_hash_does_not_accept_truncated_onnx(tmp_path):
    content = b"\x08\x08\x3a\x64partial graph"
    path = tmp_path / "broken.onnx"
    path.write_bytes(content)
    asset = {"key": "fire", "fileName": path.name, "format": "ONNX",
             "expectedSha256": hashlib.sha256(content).hexdigest()}
    with pytest.raises(ValueError, match="truncated protobuf field"):
        sync.download_asset(asset, tmp_path)
    assert path.read_bytes() == content  # Preserve the failed file for diagnosis.


@pytest.mark.parametrize("content", [b"", b"<html>error</html>", b"\x08\x80", b"\x08\x08"])
def test_invalid_model_payload_is_rejected(tmp_path, content):
    path = tmp_path / "model.onnx"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="invalid ONNX artifact"):
        sync.validate_asset_content({"key": "test", "format": "ONNX"}, path)


def test_complete_model_envelope_is_accepted(tmp_path):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"\x08\x08\x3a\x02\x12\x00")
    sync.validate_asset_content({"key": "test", "format": "ONNX"}, path)


def test_packaged_weight_initializes_without_network(tmp_path, monkeypatch):
    source = tmp_path / "source"
    output = tmp_path / "cache"
    source.mkdir()
    output.mkdir()
    content = b"\x08\x08\x3a\x02\x12\x00"
    (source / "model.onnx").write_bytes(content)
    asset = {"key": "local", "fileName": "model.onnx", "format": "ONNX",
             "expectedSha256": hashlib.sha256(content).hexdigest()}
    monkeypatch.setattr(sync, "run", lambda *args, **kwargs: pytest.fail("unexpected network request"))
    record = sync.download_asset(asset, output, source)
    assert Path(record["path"]).read_bytes() == content
    assert record["sha256"] == asset["expectedSha256"]


def test_tampered_packaged_weight_is_rejected(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "cache"
    source.mkdir()
    output.mkdir()
    (source / "model.onnx").write_bytes(b"tampered")
    asset = {"key": "local", "fileName": "model.onnx", "format": "ONNX",
             "expectedSha256": "0" * 64}
    with pytest.raises(RuntimeError, match="SHA256 不一致"):
        sync.download_asset(asset, output, source)


def test_import_refuses_to_replace_an_existing_version():
    registry = sync.LocalRegistry({}, 1)
    responses = iter(["71013", json.dumps({"sha256": "0" * 64, "runtimeManifest": {}})])
    registry.mysql = lambda sql: next(responses)
    with pytest.raises(RuntimeError, match="已存在且权重或执行契约不同"):
        registry.register_version("model", {"version": "v1"}, {"sha256": "1" * 64}, "url", {})
