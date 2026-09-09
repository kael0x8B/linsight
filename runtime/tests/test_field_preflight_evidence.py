import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/verify-field-preflight.py"
SPEC = importlib.util.spec_from_file_location("field_preflight_evidence_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def create_bundle(root: Path, content: str = "sanitized field evidence\n") -> Path:
    artifact = root / "probe.json"
    artifact.write_text(content, encoding="utf-8")
    index = root / "index.json"
    index.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "status": "PARTIAL_GATEWAY_OFFLINE",
                "artifacts": [{"path": artifact.name, "sha256": MODULE.sha256(artifact)}],
            }
        ),
        encoding="utf-8",
    )
    return index


def test_valid_bundle_passes(tmp_path) -> None:
    assert MODULE.validate(create_bundle(tmp_path)) == []


def test_hash_tampering_fails(tmp_path) -> None:
    index = create_bundle(tmp_path)
    (tmp_path / "probe.json").write_text("tampered", encoding="utf-8")

    assert any("does not match" in error for error in MODULE.validate(index))


def test_embedded_credentials_fail(tmp_path) -> None:
    index = create_bundle(tmp_path, '{"password":"not-redacted"}\n')

    assert any("credential-like" in error for error in MODULE.validate(index))


def test_path_escape_fails(tmp_path) -> None:
    outside = tmp_path.parent / "outside.log"
    outside.write_text("outside", encoding="utf-8")
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "status": "PARTIAL_GATEWAY_OFFLINE",
                "artifacts": [{"path": "../outside.log", "sha256": MODULE.sha256(outside)}],
            }
        ),
        encoding="utf-8",
    )

    assert any("escapes" in error for error in MODULE.validate(index))
