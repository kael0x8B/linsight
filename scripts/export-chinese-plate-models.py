#!/usr/bin/env python3
"""Export pinned pretrained plate weights without training or changing gateway dependencies.

Run in a separate environment with torch 2.8.0, torchvision 0.23.0, onnx 1.20.1,
onnxruntime, opencv-python, pyyaml, scipy, matplotlib, seaborn, requests, tqdm and thop.
The source checkout must match runtime/model_assets/chinese-plate-specialist-v1.json.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
OUT = args.output.resolve()
UP = args.source.resolve()
OUT.mkdir(parents=True, exist_ok=True)
ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads(
    (ROOT / "runtime/model_assets/chinese-plate-specialist-v1.json").read_text()
)
revision = subprocess.check_output(
    ["git", "-C", str(UP), "rev-parse", "HEAD"], text=True
).strip()
if revision != catalog["models"][0]["sourceRevision"]:
    raise ValueError("Source checkout does not match pinned model revision")
if torch.__version__.split("+")[0] != "2.8.0":
    raise ValueError("Reproducible export requires torch 2.8.0")
for entry in catalog["models"]:
    filename = entry["fileName"].replace(
        ".onnx", ".pt" if entry["code"].endswith("yolo") else ".pth"
    )
    if (
        hashlib.sha256((UP / "weights" / filename).read_bytes()).hexdigest()
        != entry["originalWeightsSha256"]
    ):
        raise ValueError("Pretrained checkpoint digest mismatch")
sys.path.insert(0, str(UP))
from models.common import Conv
from plate_recognition.plateNet import myNet_ocr_color
from utils.activations import Hardswish, SiLU

torch.set_num_threads(2)
# Trusted upstream checkpoint, pinned with revision and file digests in export.json.
checkpoint = torch.load(
    UP / "weights/plate_detect.pt", map_location="cpu", weights_only=False
)
det = checkpoint["model"].float().eval()
for m in det.modules():
    m._non_persistent_buffers_set = set()
    if isinstance(m, Conv):
        if isinstance(m.act, torch.nn.Hardswish):
            m.act = Hardswish()
        elif isinstance(m.act, torch.nn.SiLU):
            m.act = SiLU()
det.fuse().eval()
head = det.model[-1]
if hasattr(head, "anchor_grid"):
    delattr(head, "anchor_grid")
head.anchor_grid = [torch.zeros(1)] * head.nl
head.export_cat = True
char = "#京沪津渝冀晋蒙辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新学警港澳挂使领民航危0123456789ABCDEFGHJKLMNPQRSTUVWXYZ险品"
ck = torch.load(
    UP / "weights/plate_rec_color.pth", map_location="cpu", weights_only=True
)
rec = myNet_ocr_color(cfg=ck["cfg"], num_classes=len(char), export=True, color_num=5)
rec.load_state_dict(ck["state_dict"], strict=True)
rec.eval()
records = []
for name, model, shape, names in [
    ("plate_detect", det, (1, 3, 640, 640), ["detections"]),
    ("plate_rec_color", rec, (1, 3, 48, 168), ["characters", "color"]),
]:
    torch.manual_seed(23)
    x = torch.rand(shape)
    with torch.inference_mode():
        expected = model(x)
        if isinstance(expected, torch.Tensor):
            expected = [expected]
        torch.onnx.export(
            model,
            x,
            str(OUT / (name + ".onnx")),
            opset_version=12,
            input_names=["images"],
            output_names=names,
            dynamo=False,
        )
    g = onnx.load(OUT / (name + ".onnx"))
    onnx.checker.check_model(g)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    sess = ort.InferenceSession(
        str(OUT / (name + ".onnx")),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    actual = sess.run(None, {"images": x.numpy()})
    diffs = [float(np.max(np.abs(a - e.numpy()))) for a, e in zip(actual, expected)]
    for a, e in zip(actual, expected):
        np.testing.assert_allclose(a, e.numpy(), rtol=0.002, atol=0.002)
    p = OUT / (name + ".onnx")
    records.append(
        {
            "name": name,
            "inputShape": shape,
            "outputShapes": [list(a.shape) for a in actual],
            "size": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "maxAbsDiff": diffs,
        }
    )
metadata = {
    "source": "https://github.com/we0091234/Chinese_license_plate_detection_recognition",
    "revision": subprocess.check_output(
        ["git", "-C", str(UP), "rev-parse", "HEAD"], text=True
    ).strip(),
    "license": "GPL-3.0",
    "torchVersion": torch.__version__,
    "charset": char,
    "models": records,
    "originalWeights": {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (UP / "weights").glob("*.p*")
    },
}
(OUT / "export.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
print(json.dumps(metadata, ensure_ascii=False, indent=2))
