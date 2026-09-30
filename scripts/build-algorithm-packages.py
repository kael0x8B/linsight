#!/usr/bin/env python3
"""Build SDK examples as ordinary uploadable packages, without touching platform registries."""
import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "algorithm-packages")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for folder in sorted((ROOT / "runtime" / "algorithm_packages").iterdir()):
        if not folder.is_dir() or not (folder / "algorithm.json").is_file():
            continue
        manifest = json.loads((folder / "algorithm.json").read_text())
        target = args.output / f"{manifest['code']}-{manifest['version']}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(folder.rglob("*")):
                if file.is_file() and file.suffix in {".py", ".json", ".md"}:
                    info = zipfile.ZipInfo(str(file.relative_to(folder)), (2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, file.read_bytes())
        print(target)


if __name__ == "__main__":
    main()
