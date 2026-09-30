import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ai_runtime/app/gateway/console_artifact.py"
SPEC = importlib.util.spec_from_file_location("gateway_console_artifact", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _source(root: Path) -> Path:
    source = root / "frontend"
    source.mkdir()
    (source / "source.ts").write_text("export const value = 1;\n", encoding="utf-8")
    return source


def _dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "js").mkdir(parents=True)
    (dist / "gateway.html").write_text("<html>gateway</html>\n", encoding="utf-8")
    (dist / "index.html").write_text("<html>index</html>\n", encoding="utf-8")
    (dist / "js/app.js").write_text("console.log('ok');\n", encoding="utf-8")
    return dist


def test_artifact_is_deterministic_and_installs_verified_files(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    source = _source(tmp_path)
    bundle = tmp_path / "bundle"

    first = MODULE.build_artifact(dist, bundle, source)
    first_bytes = (bundle / first["artifact"]["fileName"]).read_bytes()
    second = MODULE.build_artifact(dist, bundle, source)

    assert first == second
    assert (bundle / second["artifact"]["fileName"]).read_bytes() == first_bytes
    assert (bundle / "current/gateway.html").read_text() == "<html>gateway</html>\n"
    assert second["files"] == sorted(second["files"], key=lambda item: item["path"])


def test_install_rejects_a_tampered_artifact_without_replacing_current(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    manifest = MODULE.build_artifact(_dist(tmp_path), bundle, _source(tmp_path))
    current = bundle / "current"
    artifact = bundle / manifest["artifact"]["fileName"]
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="size mismatch"):
        MODULE.install_artifact(bundle, current)

    assert (current / "gateway.html").is_file()


def test_install_rejects_manifest_inventory_tampering(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    MODULE.build_artifact(_dist(tmp_path), bundle, _source(tmp_path))
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="file SHA256 mismatch"):
        MODULE.install_artifact(bundle, tmp_path / "installed")


def test_install_rejects_an_unexpected_artifact_type(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    MODULE.build_artifact(_dist(tmp_path), bundle, _source(tmp_path))
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifactType"] = "anotherArtifact"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact type"):
        MODULE.install_artifact(bundle, tmp_path / "installed")
