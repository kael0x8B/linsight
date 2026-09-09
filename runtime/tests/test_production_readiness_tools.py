import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file_name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = load_script("algorithm_benchmark_test", "algorithm-benchmark.py")
INVENTORY = load_script("model_inventory_test", "model-inventory.py")


def test_algorithm_metrics_are_calculated_per_algorithm() -> None:
    records = [
        (
            {"positive": True, "expectedLabel": "皖A12345"},
            {
                "positive": True,
                "predictedLabel": "皖A12345",
                "latencyMs": 100,
                "framesProcessed": 10,
                "elapsedSeconds": 1,
            },
        ),
        ({"positive": True}, {"positive": False, "latencyMs": 200}),
        ({"positive": False}, {"positive": True, "latencyMs": 300}),
        ({"positive": False}, {"positive": False, "latencyMs": 400}),
    ]

    metrics = BENCHMARK.calculate(records)

    assert metrics["TP"] == 1
    assert metrics["FP"] == 1
    assert metrics["TN"] == 1
    assert metrics["FN"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5
    assert metrics["falsePositiveRate"] == 0.5
    assert metrics["missRate"] == 0.5
    assert metrics["latencyMs"] == {"p50": 200.0, "p95": 400.0, "p99": 400.0}
    assert metrics["fps"] == 10
    assert metrics["exactLabelAccuracy"] == 1


def test_benchmark_rejects_non_field_data_and_tampered_media(tmp_path: Path) -> None:
    media = tmp_path / "media.jpg"
    media.write_bytes(b"real-capture-placeholder-for-validation")
    truth = [
        {
            "sampleId": "sample-1",
            "algorithmCode": "license-plate",
            "condition": "day",
            "mediaPath": "media.jpg",
            "mediaSha256": "0" * 64,
            "positive": True,
        }
    ]
    predictions = [{"sampleId": "sample-1", "positive": True}]

    errors = BENCHMARK.validate_real_dataset(
        tmp_path,
        {"schemaVersion": "1.0", "datasetVersion": "v1", "dataOrigin": "FIXTURE"},
        truth,
        predictions,
    )

    assert any("REAL_FIELD" in error for error in errors)
    assert any("mediaSha256" in error for error in errors)


def test_real_dataset_report_keeps_missing_scenes_waiting(tmp_path: Path) -> None:
    media = tmp_path / "media.jpg"
    media.write_bytes(b"field-camera-bytes")
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"schemaVersion": "1.0", "datasetVersion": "field-v1", "dataOrigin": "REAL_FIELD"}
        ),
        encoding="utf-8",
    )
    (tmp_path / "ground-truth.jsonl").write_text(
        json.dumps(
            {
                "sampleId": "sample-1",
                "algorithmCode": "license-plate",
                "condition": "day",
                "mediaPath": "media.jpg",
                "mediaSha256": digest,
                "positive": True,
                "expectedLabel": "皖A12345",
                "plateType": "blue",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "predictions.jsonl").write_text(
        json.dumps(
            {
                "sampleId": "sample-1",
                "positive": True,
                "predictedLabel": "皖A12345",
                "latencyMs": 100,
                "framesProcessed": 3,
                "elapsedSeconds": 1,
                "plateFinalizedFromFrames": 3,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = BENCHMARK.evaluate(tmp_path)

    assert report["status"] == "WAITING_FOR_REAL_DATA"
    assert report["vehicleAndPlateStatus"] == "WAITING_FOR_FIELD_VIDEO"
    assert report["algorithms"][0]["metrics"]["TP"] == 1
    assert "night" in report["algorithms"][0]["missingRequiredConditions"]


def test_inventory_is_fail_closed_when_weights_are_absent(tmp_path: Path) -> None:
    report = INVENTORY.build_inventory(tmp_path)

    assert report["summary"]["declaredLogicalModels"] == 10
    assert 0 < report["summary"]["algorithms"] < 148  # Retired templates are excluded.
    assert report["status"] == "EXISTING_NEEDS_IMPROVEMENT"
    assert report["fieldAcceptance"] == "WAITING_FOR_REAL_DATA"
    assert report["summary"]["violationCounts"]["MODEL_FILE_MISSING"] > 0
