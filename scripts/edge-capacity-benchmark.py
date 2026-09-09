#!/usr/bin/env python3
"""Evaluate staged 1/2/4/8/16/32-stream production capacity evidence."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "acceptance/edge-capacity.example.json"
DEFAULT_OUTPUT = ROOT / "artifacts/production-readiness/edge-capacity-report.json"
REQUIRED_STAGES = (1, 2, 4, 8, 16, 32)


def waiting(reason: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "WAITING_FOR_TARGET_HARDWARE",
        "reason": reason,
        "requiredStages": list(REQUIRED_STAGES),
        "results": [],
    }


def read_series(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("artifactType") != "runtimeObservabilitySeries":
        raise ValueError(f"{path} is not a runtimeObservabilitySeries")
    if not isinstance(value.get("summary"), dict):
        raise ValueError(f"{path} has no summary")
    return value


def stage_result(streams: int, series: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    summary = series["summary"]
    active = int(summary.get("activeStreamsMax", 0))
    fps = float(summary.get("analysisFpsMin", 0))
    per_stream_fps = fps / streams if streams else 0
    cpu = float(summary.get("systemCpuPeakPercent", summary.get("processCpuPeakPercent", 0)))
    memory = float(summary.get("systemMemoryPeakPercent", 0))
    disk = float(summary.get("systemDiskPeakPercent", 0))
    p95 = float(
        summary.get("totalLatencyP95MillisMax", summary.get("inferenceP95MillisMax", 0))
    )
    drop_rate = float(summary.get("dropRate", 0))
    reconnects = max(
        0,
        int(summary.get("reconnectsFinal", 0)) - int(summary.get("reconnectsFirst", 0)),
    )
    checks = {
        "activeStreams": active >= streams,
        "analysisFpsPerStream": per_stream_fps >= float(
            thresholds.get("minAnalysisFpsPerStream", 1)
        ),
        "systemCpu": cpu <= float(thresholds.get("maxSystemCpuPercent", 90)),
        "systemMemory": memory <= float(thresholds.get("maxSystemMemoryPercent", 90)),
        "systemDisk": disk <= float(thresholds.get("maxSystemDiskPercent", 80)),
        "totalP95Latency": p95 <= float(thresholds.get("maxP95LatencyMs", 2000)),
        "dropRate": drop_rate <= float(thresholds.get("maxDropRate", 0.05)),
        "reconnects": reconnects <= int(thresholds.get("maxReconnects", 0)),
        "sampleDuration": float(summary.get("observedSeconds", 0))
        >= float(thresholds.get("minStageDurationSeconds", 300)),
    }
    return {
        "streams": streams,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "cameraCount": streams,
        "rtspStreamCount": active,
        "inputFps": float(summary.get("inputFpsMin", 0)),
        "decodeFps": float(summary.get("inputFpsMin", 0)),
        "inferenceFps": fps,
        "analysisFpsPerStream": round(per_stream_fps, 3),
        "droppedFrames": int(summary.get("droppedFramesDelta", 0)),
        "dropRate": drop_rate,
        "rtspReconnects": reconnects,
        "videoBitrateKbps": summary.get("videoBitrateKbps", "UNAVAILABLE_FROM_CURRENT_DECODER"),
        "preprocessP95Ms": float(summary.get("preprocessP95MillisMax", 0)),
        "inferenceP50Ms": float(summary.get("inferenceP50MillisMax", 0)),
        "inferenceP95Ms": float(summary.get("inferenceP95MillisMax", 0)),
        "inferenceP99Ms": float(summary.get("inferenceP99MillisMax", 0)),
        "postprocessP95Ms": float(summary.get("postprocessP95MillisMax", 0)),
        "totalLatencyP50Ms": float(summary.get("totalLatencyP50MillisMax", 0)),
        "totalLatencyP95Ms": p95,
        "totalLatencyP99Ms": float(summary.get("totalLatencyP99MillisMax", 0)),
        "systemCpuPeakPercent": cpu,
        "aiCpuPeakPercent": float(summary.get("processCpuPeakPercent", 0)),
        "javaCpuPeakPercent": summary.get("javaCpuPeakPercent", "NOT_COLLECTED"),
        "loadAverage1mPeak": float(summary.get("loadAverage1mPeak", 0)),
        "systemMemoryPeakPercent": memory,
        "aiMemoryPeakBytes": int(summary.get("processMemoryPeakBytes", 0)),
        "javaMemoryPeakBytes": summary.get("javaMemoryPeakBytes", "NOT_COLLECTED"),
        "gpuNpu": summary.get("accelerator", {"status": "NOT_DETECTED"}),
        "networkSentBytes": int(summary.get("networkSentBytesDelta", 0)),
        "networkReceivedBytes": int(summary.get("networkReceivedBytesDelta", 0)),
    }


def evaluate(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return waiting(f"missing capacity config: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("environmentType") != "TARGET_HARDWARE":
        return waiting("environmentType must be TARGET_HARDWARE")
    results = []
    errors = []
    for stage in config.get("stages", []):
        streams = stage.get("streams")
        artifact = stage.get("artifact")
        if streams not in REQUIRED_STAGES or not artifact:
            errors.append(f"invalid stage declaration: {stage}")
            continue
        path = (config_path.parent / artifact).resolve()
        try:
            path.relative_to(config_path.parent.resolve())
            series = read_series(path)
            results.append(stage_result(streams, series, config.get("thresholds", {})))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"stage {streams}: {error}")
    results.sort(key=lambda value: value["streams"])
    stable = [value["streams"] for value in results if value["status"] == "PASS"]
    max_stable = max(stable, default=0)
    available_stages = sorted(value["streams"] for value in results)
    recommended_limit = math.floor(max_stable * float(config.get("productionHeadroom", 0.8)))
    recommended = max(
        (stage for stage in available_stages if stage <= recommended_limit), default=0
    )
    required_complete = set(REQUIRED_STAGES).issubset(available_stages) or bool(
        config.get("hardwareLimitReached")
    )
    status = "PASS" if results and max_stable > 0 and required_complete and not errors else "WAITING_FOR_TARGET_HARDWARE"
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": status,
        "environment": config.get("environment"),
        "maximumStableStreams": max_stable,
        "recommendedProductionStreams": recommended,
        "productionHeadroom": config.get("productionHeadroom", 0.8),
        "results": results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(args.config.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
