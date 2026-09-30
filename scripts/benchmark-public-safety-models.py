#!/usr/bin/env python3
"""Compare fixed public safety-model candidates on the same immutable image sets.

This is an evidence helper, not an acceptance shortcut.  The emitted report keeps
the sample provenance and reports candidate detections without changing any
model, algorithm, task, or acceptance state.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from PIL import Image


PHONE_LABELS = (
    "calling",
    "clapping",
    "cycling",
    "dancing",
    "drinking",
    "eating",
    "fighting",
    "hugging",
    "laughing",
    "listening_music",
    "running",
    "sitting",
    "sleeping",
    "texting",
    "using_laptop",
)
SAFETY_LABELS = (
    "fall",
    "gloves",
    "goggles",
    "helmet",
    "face_mask",
    "no_gloves",
    "no_goggles",
    "no_helmet",
    "no_face_mask",
    "no_vest",
    "no_harness",
    "person",
    "vest",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--current-phone", type=Path, required=True)
    parser.add_argument("--candidate-phone", type=Path, required=True)
    parser.add_argument("--safety-v1", type=Path, required=True)
    parser.add_argument("--safety-v2", type=Path, required=True)
    parser.add_argument("--current-smoking", type=Path)
    parser.add_argument("--candidate-smoking-paddle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confidence", type=float, default=0.5)
    return parser.parse_args()


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values.astype(np.float64) - float(np.max(values))
    probabilities = np.exp(shifted)
    return probabilities / probabilities.sum()


def prepare(image: Image.Image, width: int, height: int, mean, std) -> np.ndarray:
    resized = image.convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    array = (array - np.asarray(mean, dtype=np.float32)) / np.asarray(std, dtype=np.float32)
    return np.transpose(array, (2, 0, 1))[None]


def classify(
    session: ort.InferenceSession,
    image: Image.Image,
    labels: tuple[str, ...],
    *,
    probability_output: bool,
    imagenet_normalization: bool,
) -> tuple[str, float, float]:
    mean = (0.485, 0.456, 0.406) if imagenet_normalization else (0.5, 0.5, 0.5)
    std = (0.229, 0.224, 0.225) if imagenet_normalization else (0.5, 0.5, 0.5)
    tensor = prepare(image, 224, 224, mean, std)
    started = time.perf_counter()
    output = np.asarray(session.run(None, {session.get_inputs()[0].name: tensor})[0]).reshape(-1)
    elapsed = (time.perf_counter() - started) * 1000
    scores = output.astype(np.float64) if probability_output else softmax(output)
    index = int(np.argmax(scores))
    return labels[index], float(scores[index]), elapsed


def detection_summary(
    session: ort.InferenceSession,
    image: Image.Image,
    labels: tuple[str, ...],
    confidence: float,
) -> tuple[list[dict[str, Any]], float]:
    tensor = prepare(image, 640, 640, (0, 0, 0), (1, 1, 1))
    started = time.perf_counter()
    output = np.asarray(session.run(None, {session.get_inputs()[0].name: tensor})[0])
    elapsed = (time.perf_counter() - started) * 1000
    rows = output[0].T if output.ndim == 3 and output.shape[1] == len(labels) + 4 else output.reshape(-1, len(labels) + 4)
    class_scores = rows[:, 4:]
    class_ids = np.argmax(class_scores, axis=1)
    scores = class_scores[np.arange(class_scores.shape[0]), class_ids]
    best: dict[int, float] = {}
    for class_id, score in zip(class_ids[scores >= confidence], scores[scores >= confidence], strict=True):
        key = int(class_id)
        best[key] = max(best.get(key, 0.0), float(score))
    return [
        {"class": labels[class_id], "confidence": score}
        for class_id, score in sorted(best.items(), key=lambda item: item[1], reverse=True)
    ], elapsed


def create_paddle_predictor(model_dir: Path):
    try:
        import paddle.inference as paddle_infer
    except ImportError as exc:
        raise SystemExit("PaddlePaddle is required for --candidate-smoking-paddle") from exc
    config = paddle_infer.Config(str(model_dir / "model.pdmodel"), str(model_dir / "model.pdiparams"))
    config.disable_gpu()
    config.switch_ir_optim(True)
    config.disable_glog_info()
    return paddle_infer.create_predictor(config)


def paddle_smoking_score(predictor, image: Image.Image) -> tuple[float, float]:
    rgb = image.convert("RGB")
    original_width, original_height = rgb.size
    tensor = prepare(
        rgb,
        640,
        640,
        (0.485, 0.456, 0.406),
        (0.229, 0.224, 0.225),
    )
    scale_factor = np.asarray(
        [[640.0 / original_height, 640.0 / original_width]],
        dtype=np.float32,
    )
    inputs = {name: predictor.get_input_handle(name) for name in predictor.get_input_names()}
    inputs["image"].reshape(tensor.shape)
    inputs["image"].copy_from_cpu(tensor)
    inputs["scale_factor"].reshape(scale_factor.shape)
    inputs["scale_factor"].copy_from_cpu(scale_factor)
    started = time.perf_counter()
    predictor.run()
    elapsed = (time.perf_counter() - started) * 1000
    output = np.asarray(predictor.get_output_handle(predictor.get_output_names()[0]).copy_to_cpu())
    return (float(output[:, 1].max()) if output.size else 0.0), elapsed


def nearest_rank_p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, int(np.ceil(0.95 * len(ordered))) - 1)]


def main() -> None:
    args = parse_args()
    phone_current = ort.InferenceSession(str(args.current_phone), providers=["CPUExecutionProvider"])
    phone_candidate = ort.InferenceSession(str(args.candidate_phone), providers=["CPUExecutionProvider"])
    safety_v1 = ort.InferenceSession(str(args.safety_v1), providers=["CPUExecutionProvider"])
    safety_v2 = ort.InferenceSession(str(args.safety_v2), providers=["CPUExecutionProvider"])
    report: dict[str, Any] = {
        "schemaVersion": "1.0",
        "limitations": [
            "Fixed public images are functional A/B evidence, not independent field acceptance.",
            "Detection summaries record the best score per class before NMS; event rules are not evaluated.",
            "Host timing is useful for relative regression only and is not RK3566 latency evidence.",
        ],
        "phone": {"samples": []},
        "safety": {"samples": []},
    }
    phone_times = {"current": [], "candidate": []}
    phone_counts = {"current": {"tp": 0, "fp": 0}, "candidate": {"tp": 0, "fp": 0}}
    phone_paths = sorted(args.samples.glob("calling-*.jpg")) + sorted(args.samples.glob("texting-*.jpg"))
    for path in phone_paths:
        expected = "calling" if path.name.startswith("calling-") else "other"
        with Image.open(path) as image:
            current = classify(phone_current, image, PHONE_LABELS, probability_output=False, imagenet_normalization=False)
            candidate = classify(phone_candidate, image, ("calling", "other"), probability_output=True, imagenet_normalization=True)
        for name, result in (("current", current), ("candidate", candidate)):
            predicted_positive = result[0] == "calling" and result[1] >= args.confidence
            if expected == "calling" and predicted_positive:
                phone_counts[name]["tp"] += 1
            if expected == "other" and predicted_positive:
                phone_counts[name]["fp"] += 1
            phone_times[name].append(result[2])
        report["phone"]["samples"].append(
            {
                "file": path.name,
                "expected": expected,
                "current": {"class": current[0], "confidence": current[1]},
                "candidate": {"class": candidate[0], "confidence": candidate[1]},
            }
        )
    positives = sum(1 for item in report["phone"]["samples"] if item["expected"] == "calling")
    negatives = len(report["phone"]["samples"]) - positives
    for name in ("current", "candidate"):
        report["phone"][name] = {
            **phone_counts[name],
            "positiveCount": positives,
            "negativeCount": negatives,
            "recall": phone_counts[name]["tp"] / positives if positives else None,
            "falsePositiveRate": phone_counts[name]["fp"] / negatives if negatives else None,
            "medianInferenceMillis": statistics.median(phone_times[name]),
            "p95InferenceMillis": nearest_rank_p95(phone_times[name]),
        }

    safety_times = {"v1": [], "v2": []}
    safety_hits = {"v1": 0, "v2": 0}
    safety_paths = sorted(args.samples.glob("fall-*.jpg"))
    for path in safety_paths:
        with Image.open(path) as image:
            v1, v1_ms = detection_summary(safety_v1, image, SAFETY_LABELS, args.confidence)
            v2, v2_ms = detection_summary(safety_v2, image, SAFETY_LABELS, args.confidence)
        safety_times["v1"].append(v1_ms)
        safety_times["v2"].append(v2_ms)
        safety_hits["v1"] += any(item["class"] == "fall" for item in v1)
        safety_hits["v2"] += any(item["class"] == "fall" for item in v2)
        report["safety"]["samples"].append({"file": path.name, "v1": v1, "v2": v2})
    for name in ("v1", "v2"):
        report["safety"][name] = {
            "fallImagesDetected": safety_hits[name],
            "fallImageCount": len(safety_paths),
            "medianInferenceMillis": statistics.median(safety_times[name]),
            "p95InferenceMillis": nearest_rank_p95(safety_times[name]),
        }

    if bool(args.current_smoking) != bool(args.candidate_smoking_paddle):
        raise SystemExit("--current-smoking and --candidate-smoking-paddle must be supplied together")
    if args.current_smoking and args.candidate_smoking_paddle:
        current_smoking = ort.InferenceSession(str(args.current_smoking), providers=["CPUExecutionProvider"])
        candidate_smoking = create_paddle_predictor(args.candidate_smoking_paddle)
        report["smoking"] = {"samples": []}
        smoking_times = {"current": [], "candidate": []}
        smoking_counts = {
            "current": {"tp": 0, "fp": 0},
            "candidate": {"tp": 0, "fp": 0},
        }
        smoking_paths = sorted(args.samples.glob("smoking-*.jpg")) + sorted(
            args.samples.glob("not_smoking-*.jpg")
        )
        for path in smoking_paths:
            expected = "smoking" if path.name.startswith("smoking-") else "other"
            with Image.open(path) as image:
                current_detections, current_ms = detection_summary(
                    current_smoking,
                    image,
                    ("smoking",),
                    args.confidence,
                )
                candidate_score, candidate_ms = paddle_smoking_score(candidate_smoking, image)
            current_score = current_detections[0]["confidence"] if current_detections else 0.0
            scores = {"current": current_score, "candidate": candidate_score}
            smoking_times["current"].append(current_ms)
            smoking_times["candidate"].append(candidate_ms)
            for name, score in scores.items():
                predicted_positive = score >= args.confidence
                if expected == "smoking" and predicted_positive:
                    smoking_counts[name]["tp"] += 1
                if expected == "other" and predicted_positive:
                    smoking_counts[name]["fp"] += 1
            report["smoking"]["samples"].append(
                {
                    "file": path.name,
                    "expected": expected,
                    "current": {"confidence": current_score},
                    "candidate": {"confidence": candidate_score},
                }
            )
        positive_count = sum(
            1 for item in report["smoking"]["samples"] if item["expected"] == "smoking"
        )
        negative_count = len(report["smoking"]["samples"]) - positive_count
        for name in ("current", "candidate"):
            report["smoking"][name] = {
                **smoking_counts[name],
                "positiveCount": positive_count,
                "negativeCount": negative_count,
                "recall": smoking_counts[name]["tp"] / positive_count if positive_count else None,
                "falsePositiveRate": (
                    smoking_counts[name]["fp"] / negative_count if negative_count else None
                ),
                "medianInferenceMillis": statistics.median(smoking_times[name]),
                "p95InferenceMillis": nearest_rank_p95(smoking_times[name]),
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary = {
        "phone": {key: report["phone"][key] for key in ("current", "candidate")},
        "safety": {key: report["safety"][key] for key in ("v1", "v2")},
    }
    if "smoking" in report:
        summary["smoking"] = {
            key: report["smoking"][key] for key in ("current", "candidate")
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
