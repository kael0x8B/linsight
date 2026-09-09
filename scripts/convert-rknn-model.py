#!/usr/bin/env python3
"""Convert an existing manifest-based ONNX version in the isolated RKNN build image."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from PIL import Image
from rknn.api import RKNN


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--precision", choices=("int8", "fp16"), default="int8")
    args = parser.parse_args()
    if importlib.metadata.version("rknn-toolkit2") != "2.3.2":
        raise ValueError("Use the pinned RKNN 2.3.2 conversion image")
    manifest = json.loads(args.manifest.read_text())
    pre = manifest["preprocess"]
    if pre["dtype"] != "FLOAT32" or pre["layout"] != "NCHW" or pre["resize"] != "STRETCH":
        raise ValueError("This converter requires the declared FLOAT32 NCHW STRETCH source")
    width, height = pre["inputWidth"], pre["inputHeight"]
    scale = pre["scale"]
    mean = [value / scale for value in pre["mean"]]
    std = [value / scale for value in pre["std"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    resized = args.output.parent / (args.output.stem + "-calibration")
    resized.mkdir(exist_ok=True)
    sources = []
    inputs = []
    for path in sorted(args.calibration.glob("*.jpg")):
        target = resized / (path.stem + ".png")
        with Image.open(path) as image:
            image.convert("RGB").resize((width, height), Image.Resampling.BILINEAR).save(target)
        inputs.append(str(target.resolve()))
        sources.append({"name": path.name, "sha256": sha(path), "resizedSha256": sha(target)})
    if not inputs:
        raise ValueError("Real calibration images are required")
    dataset = resized / "dataset.txt"
    dataset.write_text("\n".join(inputs) + "\n")
    model = RKNN(verbose=False)
    try:
        model.config(target_platform="rk3566", mean_values=[mean], std_values=[std])
        if model.load_onnx(model=str(args.onnx)) != 0:
            raise RuntimeError("ONNX import failed")
        if model.build(do_quantization=args.precision == "int8", dataset=str(dataset)) != 0:
            raise RuntimeError("RKNN conversion failed")
        if model.export_rknn(str(args.output)) != 0:
            raise RuntimeError("RKNN export failed")
    finally:
        model.release()
    original_manifest_sha = sha(args.manifest)
    manifest["preprocess"] = {
        **pre, "layout": "NHWC", "dtype": "UINT8", "scale": 1.0,
        "mean": [0, 0, 0], "std": [1, 1, 1],
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    provenance = {
        "schemaVersion": "1.0", "sourceOnnxSha256": sha(args.onnx),
        "sourceManifestSha256": original_manifest_sha, "artifactSha256": sha(args.output),
        "targetPlatform": "rk3566", "precision": args.precision,
        "toolkitVersion": "2.3.2", "calibrationImages": sources,
        "embeddedNormalization": {"meanValues": mean, "stdValues": std},
        "validationStatus": "PENDING_REAL_NODE_COMPARISON",
    }
    args.output.with_suffix(".conversion.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps({key: provenance[key] for key in
                      ["artifactSha256", "targetPlatform", "precision", "validationStatus"]}), flush=True)


if __name__ == "__main__":
    main()
