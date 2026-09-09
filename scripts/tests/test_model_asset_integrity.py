import hashlib
import importlib.util
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
