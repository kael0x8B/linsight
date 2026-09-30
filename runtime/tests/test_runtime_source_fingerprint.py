import hashlib
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/runtime-source-fingerprint.py"
SPEC = importlib.util.spec_from_file_location("runtime_source_fingerprint", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_console_bundle(root: Path) -> list[str]:
    directory = root / "gateway-console"
    directory.mkdir()
    artifact = directory / "gateway-console-0123456789ab.tar.gz"
    artifact.write_bytes(b"console")
    (directory / "manifest.json").write_text(
        '{"artifact":{"fileName":"gateway-console-0123456789ab.tar.gz"}}\n',
        encoding="utf-8",
    )
    return [
        "gateway-console/gateway-console-0123456789ab.tar.gz",
        "gateway-console/manifest.json",
    ]


def test_fingerprint_uses_sorted_manifest_and_excludes_bytecode(tmp_path: Path) -> None:
    (tmp_path / "ai_runtime" / "__pycache__").mkdir(parents=True)
    (tmp_path / "edge_agent").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "ai_runtime" / "z.py").write_text("z = 1\n", encoding="utf-8")
    (tmp_path / "ai_runtime" / "__pycache__" / "z.pyc").write_bytes(b"ignored")
    (tmp_path / "edge_agent" / "a.py").write_text("a = 1\n", encoding="utf-8")
    console = write_console_bundle(tmp_path)

    files = MODULE.source_files(tmp_path)
    relative = [path.relative_to(tmp_path).as_posix() for path in files]
    assert relative == [
        "ai_runtime/z.py",
        "edge_agent/a.py",
        *console,
        "pyproject.toml",
    ]

    manifest = "".join(
        f"{hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()}  {name}\n"
        for name in relative
    ).encode()
    assert (
        MODULE.fingerprint(tmp_path)["fingerprint"]["sha256"]
        == hashlib.sha256(manifest).hexdigest()
    )


def test_fingerprint_changes_when_deployed_source_changes(tmp_path: Path) -> None:
    (tmp_path / "ai_runtime").mkdir()
    (tmp_path / "edge_agent").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    source = tmp_path / "ai_runtime" / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    write_console_bundle(tmp_path)

    before = MODULE.fingerprint(tmp_path)["fingerprint"]["sha256"]
    source.write_text("value = 2\n", encoding="utf-8")
    after = MODULE.fingerprint(tmp_path)["fingerprint"]["sha256"]

    assert before != after
