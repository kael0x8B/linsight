#!/usr/bin/env python3
"""Package verified publisher dependencies already prepared on the source machine."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / "deploy/application-release/baseline"
contract = hashlib.sha256((ROOT / "runtime/pyproject.toml").read_bytes()).hexdigest()
wheels = ROOT / f"runtime/deployment-wheels/{contract}/aarch64-cp312"
wheel_manifest = json.loads((wheels / "manifest.json").read_text(encoding="utf-8"))
console = ROOT / "runtime/gateway-console"
console_manifest = json.loads((console / "manifest.json").read_text(encoding="utf-8"))
python = ROOT / "runtime/deployment-python/cpython-3.12.14+20260924-aarch64-unknown-linux-gnu-install_only.tar.gz"
python_sha = "c0574c9c9fec561eb192ad510e4e79aaad039929b3531b3bb873e2f630fb14a9"
assert hashlib.sha256(python.read_bytes()).hexdigest() == python_sha
paths = [python, wheels / "manifest.json", console / "manifest.json", console / console_manifest["artifact"]["fileName"]]
for name, sha in wheel_manifest["files"].items():
    path = wheels / name
    assert path.name == name and hashlib.sha256(path.read_bytes()).hexdigest() == sha
    paths.append(path)
files = []
for path in paths:
    relative = path.relative_to(ROOT)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    # Avoid long wheel names plus nested hashes exceeding Git for Windows MAX_PATH.
    source = f"files/{checksum}"
    destination = target / source
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, destination)
    files.append({"source": source, "path": relative.as_posix(), "sha256": checksum, "size": path.stat().st_size})
manifest = {"schemaVersion": 1, "architecture": "aarch64", "pythonVersion": "3.12", "minGlibc": "2.34",
            "pyprojectSha256": contract, "pythonArchive": python.relative_to(ROOT).as_posix(),
            "pythonSha256": python_sha, "wheelsDirectory": wheels.relative_to(ROOT).as_posix(), "files": files}
(target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
# Retire the previous generated layout after the complete replacement is written.
if (target / "runtime").is_dir():
    shutil.rmtree(target / "runtime")
print(f"[ok] 发布依赖 {len(files)} 个文件 / {sum(item['size'] for item in files)} bytes")
