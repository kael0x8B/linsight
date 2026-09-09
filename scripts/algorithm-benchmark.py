#!/usr/bin/env python3
"""Evaluate real LInsight field datasets and emit per-algorithm acceptance metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "acceptance/datasets/current"
DEFAULT_OUTPUT = ROOT / "artifacts/production-readiness/algorithm-benchmark.json"
CORE_ALGORITHMS = (
    "safety-helmet",
    "reflective-vest",
    "smoking-detection",
    "phone-call-detection",
    "person-intrusion",
    "area-intrusion",
    "fall-detection",
    "flame-detection",
    "vehicle-detection",
    "license-plate",
    "person-absence",
)
VEHICLE_CONDITIONS = (
    "day",
    "night",
    "backlight",
    "rain",
    "blur",
    "dirty",
    "occlusion",
    "small-target",
    "tilt",
    "long-distance",
    "motion-blur",
    "glare",
)
VEHICLE_CLASSES = (
    "sedan",
    "suv",
    "van",
    "small_truck",
    "box_truck",
    "medium_truck",
    "heavy_truck",
    "trailer",
    "engineering_vehicle",
)
PLATE_TYPES = ("blue", "yellow", "new-energy", "large-vehicle", "double-row")
CHINESE_PLATE = re.compile(
    r"^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼]"
    r"[A-HJ-NP-Z][A-HJ-NP-Z0-9]{5,6}$"
)


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return round(ordered[index], 3)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_no}: invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: each line must be an object")
        records.append(value)
    return records


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def calculate(records: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    latencies: list[float] = []
    preprocess: list[float] = []
    inference: list[float] = []
    postprocess: list[float] = []
    total_frames = 0
    total_seconds = 0.0
    exact_labels = 0
    labeled = 0
    for truth, prediction in records:
        expected = truth.get("positive") is True
        detected = prediction.get("positive") is True
        if expected and detected:
            tp += 1
        elif not expected and detected:
            fp += 1
        elif not expected and not detected:
            tn += 1
        else:
            fn += 1
        for target, key in (
            (latencies, "latencyMs"),
            (preprocess, "preprocessMs"),
            (inference, "inferenceMs"),
            (postprocess, "postprocessMs"),
        ):
            value = prediction.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                target.append(float(value))
        frames = prediction.get("framesProcessed")
        elapsed = prediction.get("elapsedSeconds")
        if isinstance(frames, int) and frames >= 0:
            total_frames += frames
        if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and elapsed >= 0:
            total_seconds += float(elapsed)
        if truth.get("expectedLabel") is not None:
            labeled += 1
            exact_labels += truth.get("expectedLabel") == prediction.get("predictedLabel")
    precision = safe_ratio(tp, tp + fp)
    recall = safe_ratio(tp, tp + fn)
    return {
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "f1": round(2 * precision * recall / (precision + recall), 6)
        if precision + recall
        else 0.0,
        "falsePositiveRate": safe_ratio(fp, fp + tn),
        "missRate": safe_ratio(fn, tp + fn),
        "latencyMs": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "preprocessP95Ms": percentile(preprocess, 0.95),
        "inferenceP95Ms": percentile(inference, 0.95),
        "postprocessP95Ms": percentile(postprocess, 0.95),
        "fps": round(total_frames / total_seconds, 3) if total_seconds > 0 else 0.0,
        "exactLabelAccuracy": safe_ratio(exact_labels, labeled) if labeled else None,
        "samples": len(records),
    }


def validate_real_dataset(
    dataset_dir: Path,
    manifest: dict[str, Any],
    truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if manifest.get("schemaVersion") != "1.0":
        errors.append("manifest.schemaVersion must be 1.0")
    if manifest.get("dataOrigin") != "REAL_FIELD":
        errors.append("manifest.dataOrigin must be REAL_FIELD; fixtures cannot pass acceptance")
    if not manifest.get("datasetVersion"):
        errors.append("manifest.datasetVersion is required")
    ids: set[str] = set()
    for index, item in enumerate(truth):
        sample_id = item.get("sampleId")
        if not isinstance(sample_id, str) or not sample_id:
            errors.append(f"groundTruth[{index}].sampleId is required")
            continue
        if sample_id in ids:
            errors.append(f"duplicate ground-truth sampleId: {sample_id}")
        ids.add(sample_id)
        for key in ("algorithmCode", "condition", "mediaPath", "mediaSha256"):
            if not item.get(key):
                errors.append(f"groundTruth[{index}].{key} is required")
        if not isinstance(item.get("positive"), bool):
            errors.append(f"groundTruth[{index}].positive must be boolean")
        media = (dataset_dir / str(item.get("mediaPath", ""))).resolve()
        try:
            media.relative_to(dataset_dir.resolve())
        except ValueError:
            errors.append(f"groundTruth[{index}].mediaPath escapes dataset directory")
            continue
        if not media.is_file() or media.stat().st_size == 0:
            errors.append(f"groundTruth[{index}] media is missing or empty")
        elif file_sha256(media) != item.get("mediaSha256"):
            errors.append(f"groundTruth[{index}] mediaSha256 does not match")
    prediction_ids = [item.get("sampleId") for item in predictions]
    if len(prediction_ids) != len(set(prediction_ids)):
        errors.append("predictions contain duplicate sampleId values")
    missing = sorted(ids - set(prediction_ids))
    extra = sorted(set(prediction_ids) - ids)
    if missing:
        errors.append(f"predictions missing sampleIds: {missing[:10]}")
    if extra:
        errors.append(f"predictions contain unknown sampleIds: {extra[:10]}")
    return errors


def waiting_report(reason: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "WAITING_FOR_REAL_DATA",
        "vehicleAndPlateStatus": "WAITING_FOR_FIELD_VIDEO",
        "reason": reason,
        "algorithms": [
            {"algorithmCode": code, "status": "WAITING_FOR_REAL_DATA"}
            for code in CORE_ALGORITHMS
        ],
        "requiredVehicleConditions": list(VEHICLE_CONDITIONS),
        "requiredVehicleClasses": list(VEHICLE_CLASSES),
        "requiredPlateTypes": list(PLATE_TYPES),
    }


def evaluate(dataset_dir: Path) -> dict[str, Any]:
    manifest_path = dataset_dir / "manifest.json"
    truth_path = dataset_dir / "ground-truth.jsonl"
    predictions_path = dataset_dir / "predictions.jsonl"
    if not all(path.is_file() for path in (manifest_path, truth_path, predictions_path)):
        return waiting_report(
            "manifest.json, ground-truth.jsonl and predictions.jsonl from a real field dataset are required"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    truth = read_jsonl(truth_path)
    predictions = read_jsonl(predictions_path)
    errors = validate_real_dataset(dataset_dir, manifest, truth, predictions)
    if errors:
        return {
            **waiting_report("dataset validation failed"),
            "status": "FAIL",
            "errors": errors,
        }
    predictions_by_id = {item["sampleId"]: item for item in predictions}
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    conditions: dict[str, dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item in truth:
        pair = (item, predictions_by_id[item["sampleId"]])
        code = item["algorithmCode"]
        grouped[code].append(pair)
        conditions[code][item["condition"]].append(pair)
    results = []
    for code in sorted(grouped):
        pairs = grouped[code]
        result = {
            "algorithmCode": code,
            "status": "MEASURED",
            "metrics": calculate(pairs),
            "byCondition": {
                condition: calculate(values)
                for condition, values in sorted(conditions[code].items())
            },
        }
        if code in {"vehicle-detection", "license-plate"}:
            observed_conditions = {item[0]["condition"] for item in pairs}
            result["missingRequiredConditions"] = sorted(
                set(VEHICLE_CONDITIONS) - observed_conditions
            )
            if code == "vehicle-detection":
                observed_classes = {item[0].get("vehicleClass") for item in pairs}
                result["missingRequiredVehicleClasses"] = sorted(
                    set(VEHICLE_CLASSES) - observed_classes
                )
                result["vehicleContractViolations"] = [
                    item[1]["sampleId"]
                    for item in pairs
                    if item[1].get("positive") is True
                    and (
                        not isinstance(item[1].get("trackId"), str)
                        or not item[1].get("trackId")
                    )
                ]
            else:
                observed_types = {item[0].get("plateType") for item in pairs}
                result["missingRequiredPlateTypes"] = sorted(set(PLATE_TYPES) - observed_types)
                invalid_finalization = [
                    item[1]["sampleId"]
                    for item in pairs
                    if item[1].get("positive") is True
                    and int(item[1].get("plateFinalizedFromFrames", 0)) < 2
                ]
                result["singleFrameFinalizationViolations"] = invalid_finalization
                result["plateContractViolations"] = [
                    item[1]["sampleId"]
                    for item in pairs
                    if item[1].get("positive") is True
                    and (
                        not isinstance(item[1].get("ocrConfidence"), (int, float))
                        or isinstance(item[1].get("ocrConfidence"), bool)
                        or not 0 <= float(item[1].get("ocrConfidence", -1)) <= 1
                        or not isinstance(item[1].get("trackId"), str)
                        or not item[1].get("trackId")
                        or not isinstance(item[1].get("vehicleTrackId"), str)
                        or not item[1].get("vehicleTrackId")
                        or not isinstance(item[1].get("predictedLabel"), str)
                        or CHINESE_PLATE.fullmatch(item[1].get("predictedLabel", "")) is None
                    )
                ]
        results.append(result)
    missing_algorithms = sorted(set(CORE_ALGORITHMS) - set(grouped))
    vehicle_result = next(
        (value for value in results if value["algorithmCode"] == "vehicle-detection"), None
    )
    plate_result = next(
        (value for value in results if value["algorithmCode"] == "license-plate"), None
    )
    specialized_complete = bool(
        vehicle_result
        and plate_result
        and not vehicle_result.get("missingRequiredConditions")
        and not vehicle_result.get("missingRequiredVehicleClasses")
        and not vehicle_result.get("vehicleContractViolations")
        and not plate_result.get("missingRequiredConditions")
        and not plate_result.get("missingRequiredPlateTypes")
        and not plate_result.get("singleFrameFinalizationViolations")
        and not plate_result.get("plateContractViolations")
    )
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "MEASURED" if not missing_algorithms else "WAITING_FOR_REAL_DATA",
        "vehicleAndPlateStatus": "MEASURED"
        if specialized_complete
        else "WAITING_FOR_FIELD_VIDEO",
        "datasetVersion": manifest["datasetVersion"],
        "datasetSha256": file_sha256(manifest_path),
        "missingCoreAlgorithms": missing_algorithms,
        "algorithms": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--runner-command",
        help="explicit field inference command; receives DATASET_DIR and PREDICTIONS_PATH env vars",
    )
    args = parser.parse_args()
    if args.runner_command:
        environment = dict(__import__("os").environ)
        environment["DATASET_DIR"] = str(args.dataset.resolve())
        environment["PREDICTIONS_PATH"] = str((args.dataset / "predictions.jsonl").resolve())
        result = subprocess.run(
            shlex.split(args.runner_command), cwd=ROOT, env=environment, check=False
        )
        if result.returncode != 0:
            print("field inference runner failed", file=sys.stderr)
            return result.returncode
    report = evaluate(args.dataset.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 2 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
