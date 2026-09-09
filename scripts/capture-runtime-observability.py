#!/usr/bin/env python3
"""Capture authenticated Runtime metrics without writing credentials to evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def safe_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials in URLs are forbidden")
    if parsed.query or parsed.fragment:
        raise ValueError("base URL must not contain a query or fragment")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )


def request_json(
    opener: urllib.request.OpenerDirector,
    url: str,
    runtime_key: str | None = None,
) -> tuple[dict[str, Any] | None, float, str | None]:
    headers = {"Accept": "application/json"}
    if runtime_key is not None:
        headers["X-Runtime-Key"] = runtime_key
    request = urllib.request.Request(url, headers=headers)
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=10) as response:
            value = json.loads(response.read())
            if response.status != 200 or not isinstance(value, dict):
                raise ValueError("response is not a successful JSON object")
            return value, (time.perf_counter() - started) * 1000, None
    except (
        OSError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as error:
        return None, (time.perf_counter() - started) * 1000, type(error).__name__


def process_metrics(pid: int | None) -> dict[str, float | int] | None:
    if pid is None:
        return None
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "%cpu=,rss="],
        text=True,
        capture_output=True,
        check=False,
    )
    parts = result.stdout.split()
    if result.returncode != 0 or len(parts) != 2:
        return None
    try:
        return {"pid": pid, "cpuPercent": float(parts[0]), "residentMemoryBytes": int(parts[1]) * 1024}
    except ValueError:
        return None


def accelerator_metrics() -> dict[str, Any]:
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            rows = []
            for index, line in enumerate(result.stdout.splitlines()):
                values = [value.strip() for value in line.split(",")]
                if len(values) == 5:
                    try:
                        rows.append(
                            {
                                "index": index,
                                "type": "NVIDIA_GPU",
                                "utilizationPercent": float(values[0]),
                                "memoryUsedMiB": float(values[1]),
                                "memoryTotalMiB": float(values[2]),
                                "temperatureCelsius": float(values[3]),
                                "powerWatts": float(values[4]),
                            }
                        )
                    except ValueError:
                        continue
            if rows:
                return {"status": "DETECTED", "devices": rows}
    npu_load_files = sorted(Path("/sys/class/devfreq").glob("*npu*/load"))
    devices = []
    for path in npu_load_files:
        try:
            match = __import__("re").search(r"(\d+)", path.read_text(encoding="utf-8"))
            if match:
                devices.append(
                    {"type": "NPU", "name": path.parent.name, "utilizationPercent": float(match.group(1))}
                )
        except OSError:
            continue
    return {"status": "DETECTED", "devices": devices} if devices else {"status": "NOT_DETECTED"}


def summarize(samples: list[dict[str, Any]], observed_seconds: float) -> dict[str, Any]:
    snapshots = [sample["snapshot"] for sample in samples if sample.get("snapshot")]

    def values(path: tuple[str, ...]) -> list[float]:
        result: list[float] = []
        for snapshot in snapshots:
            current: Any = snapshot
            for key in path:
                current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, (int, float)) and not isinstance(current, bool):
                result.append(float(current))
        return result

    def minimum(path: tuple[str, ...]) -> float:
        found = values(path)
        return min(found, default=0)

    def maximum(path: tuple[str, ...]) -> float:
        found = values(path)
        return max(found, default=0)

    def final(path: tuple[str, ...]) -> float:
        found = values(path)
        return found[-1] if found else 0

    def first(path: tuple[str, ...]) -> float:
        found = values(path)
        return found[0] if found else 0

    java_cpu = [
        float(sample["javaProcess"]["cpuPercent"])
        for sample in samples
        if isinstance(sample.get("javaProcess"), dict)
    ]
    java_memory = [
        int(sample["javaProcess"]["residentMemoryBytes"])
        for sample in samples
        if isinstance(sample.get("javaProcess"), dict)
    ]
    accelerator_devices = [
        device
        for sample in samples
        for device in sample.get("accelerator", {}).get("devices", [])
        if isinstance(device, dict)
    ]

    frames_delta = max(0, final(("streams", "frames")) - first(("streams", "frames")))
    dropped_delta = max(
        0,
        final(("streams", "droppedFrames")) - first(("streams", "droppedFrames")),
    )
    network_sent_delta = max(
        0,
        final(("system", "networkBytesSent")) - first(("system", "networkBytesSent")),
    )
    network_received_delta = max(
        0,
        final(("system", "networkBytesReceived"))
        - first(("system", "networkBytesReceived")),
    )

    return {
        "sampleCount": len(samples),
        "successfulRuntimeSamples": len(snapshots),
        "observedSeconds": round(observed_seconds, 3),
        "controlPlaneConfigured": any(
            sample.get("controlPlaneReachable") is not None for sample in samples
        ),
        "controlPlaneReachableSamples": sum(
            sample.get("controlPlaneReachable") is True for sample in samples
        ),
        "runningTasksMin": int(minimum(("tasks", "running"))),
        "analysisFpsMin": round(minimum(("tasks", "analysisFps")), 3),
        "activeStreamsMax": int(maximum(("streams", "active"))),
        "inputFpsMin": round(minimum(("streams", "inputFps")), 3),
        "droppedFramesFirst": int(values(("streams", "droppedFrames"))[0])
        if snapshots
        else 0,
        "droppedFramesFinal": int(final(("streams", "droppedFrames"))),
        "reconnectsFirst": int(values(("streams", "reconnects"))[0])
        if snapshots
        else 0,
        "reconnectsFinal": int(final(("streams", "reconnects"))),
        "pendingEventsMax": int(maximum(("delivery", "pendingEvents"))),
        "pendingEventsFirst": int(values(("delivery", "pendingEvents"))[0])
        if snapshots
        else 0,
        "pendingEventsFinal": int(final(("delivery", "pendingEvents"))),
        "pendingTransitionsMax": int(maximum(("delivery", "pendingTransitions"))),
        "pendingTransitionsFirst": int(values(("delivery", "pendingTransitions"))[0])
        if snapshots
        else 0,
        "pendingTransitionsFinal": int(final(("delivery", "pendingTransitions"))),
        "deadLetterTransitionsMax": int(maximum(("delivery", "deadLetterTransitions"))),
        "deadLetterTransitionsFirst": int(
            values(("delivery", "deadLetterTransitions"))[0]
        )
        if snapshots
        else 0,
        "deadLetterTransitionsFinal": int(final(("delivery", "deadLetterTransitions"))),
        "evidenceBacklogBytesMax": int(maximum(("delivery", "evidenceBacklogBytes"))),
        "evidenceBacklogBytesFirst": int(values(("delivery", "evidenceBacklogBytes"))[0])
        if snapshots
        else 0,
        "missingMediaFilesMax": int(maximum(("delivery", "missingMediaFiles"))),
        "inferenceP95MillisMax": round(maximum(("tasks", "inferenceP95Millis")), 3),
        "preprocessP95MillisMax": round(maximum(("tasks", "preprocessP95Millis")), 3),
        "inferenceP50MillisMax": round(maximum(("tasks", "inferenceP50Millis")), 3),
        "inferenceP99MillisMax": round(maximum(("tasks", "inferenceP99Millis")), 3),
        "postprocessP95MillisMax": round(maximum(("tasks", "postprocessP95Millis")), 3),
        "totalLatencyP50MillisMax": round(
            maximum(("tasks", "totalLatencyP50Millis")), 3
        ),
        "totalLatencyP95MillisMax": round(
            maximum(("tasks", "totalLatencyP95Millis")), 3
        ),
        "totalLatencyP99MillisMax": round(
            maximum(("tasks", "totalLatencyP99Millis")), 3
        ),
        "processCpuPeakPercent": round(maximum(("process", "cpuPercent")), 3),
        "processMemoryPeakBytes": int(maximum(("process", "residentMemoryBytes"))),
        "systemCpuPeakPercent": round(maximum(("system", "cpuPercent")), 3),
        "systemMemoryPeakPercent": round(maximum(("system", "memoryPercent")), 3),
        "systemDiskPeakPercent": round(maximum(("system", "diskPercent")), 3),
        "systemTemperaturePeakCelsius": round(
            maximum(("system", "temperatureCelsius")), 3
        ),
        "loadAverage1mPeak": round(maximum(("system", "loadAverage1m")), 3),
        "framesDelta": int(frames_delta),
        "droppedFramesDelta": int(dropped_delta),
        "dropRate": round(
            dropped_delta / (frames_delta + dropped_delta)
            if frames_delta + dropped_delta > 0
            else 0,
            6,
        ),
        "networkSentBytesDelta": int(network_sent_delta),
        "networkReceivedBytesDelta": int(network_received_delta),
        "javaCpuPeakPercent": round(max(java_cpu, default=0), 3),
        "javaMemoryPeakBytes": max(java_memory, default=0),
        "accelerator": {
            "status": "DETECTED" if accelerator_devices else "NOT_DETECTED",
            "utilizationPeakPercent": max(
                (float(value.get("utilizationPercent", 0)) for value in accelerator_devices),
                default=0,
            ),
            "memoryUsedPeakMiB": max(
                (float(value.get("memoryUsedMiB", 0)) for value in accelerator_devices),
                default=0,
            ),
            "temperaturePeakCelsius": max(
                (float(value.get("temperatureCelsius", 0)) for value in accelerator_devices),
                default=0,
            ),
            "powerPeakWatts": max(
                (float(value.get("powerWatts", 0)) for value in accelerator_devices),
                default=0,
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-url", required=True)
    parser.add_argument("--runtime-key-env", default="LINSIGHT_RUNTIME_API_KEY")
    parser.add_argument("--control-plane-health-url")
    parser.add_argument("--duration-seconds", type=float, default=0)
    parser.add_argument("--interval-seconds", type=float, default=10)
    parser.add_argument("--environment-name", required=True)
    parser.add_argument("--hardware", required=True)
    parser.add_argument("--software-version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--java-pid", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration_seconds < 0 or not 0 < args.interval_seconds <= 60:
        parser.error("duration must be non-negative and interval must be in (0, 60]")
    runtime_key = os.environ.get(args.runtime_key_env)
    if not runtime_key:
        print(f"missing runtime key environment variable: {args.runtime_key_env}", file=sys.stderr)
        return 2
    try:
        runtime_base = safe_base_url(args.runtime_url)
        control_url = (
            safe_base_url(args.control_plane_health_url)
            if args.control_plane_health_url
            else None
        )
    except ValueError as error:
        parser.error(str(error))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started_at = iso_now()
    started = time.monotonic()
    deadline = started + args.duration_seconds
    samples: list[dict[str, Any]] = []
    while True:
        observed_at = iso_now()
        snapshot, runtime_millis, runtime_error = request_json(
            opener, f"{runtime_base}/v1/observability/snapshot", runtime_key
        )
        if snapshot is not None and snapshot.get("schemaVersion") != "1.0":
            runtime_error = "UnsupportedSnapshotSchema"
            snapshot = None
        control_reachable = None
        control_millis = None
        control_error = None
        if control_url is not None:
            control, control_millis, control_error = request_json(opener, control_url)
            control_reachable = control is not None
        samples.append(
            {
                "observedAt": observed_at,
                "runtimeRequestMillis": round(runtime_millis, 3),
                "runtimeError": runtime_error,
                "controlPlaneReachable": control_reachable,
                "controlPlaneRequestMillis": None
                if control_millis is None
                else round(control_millis, 3),
                "controlPlaneError": control_error,
                "snapshot": snapshot,
                "javaProcess": process_metrics(args.java_pid),
                "accelerator": accelerator_metrics(),
            }
        )
        now = time.monotonic()
        if now >= deadline:
            break
        time.sleep(min(args.interval_seconds, max(0, deadline - now)))
    observed_seconds = time.monotonic() - started
    summary = summarize(samples, observed_seconds)
    report = {
        "schemaVersion": "1.0",
        "artifactType": "runtimeObservabilitySeries",
        "generatedAt": iso_now(),
        "startedAt": started_at,
        "runId": args.run_id,
        "environment": {
            "name": args.environment_name,
            "hardware": args.hardware,
            "softwareVersion": args.software_version,
        },
        "runtimeUrl": runtime_base,
        "controlPlaneHealthUrl": control_url,
        "requestedDurationSeconds": args.duration_seconds,
        "intervalSeconds": args.interval_seconds,
        "summary": summary,
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "summary": summary}, ensure_ascii=False))
    return 0 if summary["successfulRuntimeSamples"] == summary["sampleCount"] else 1


if __name__ == "__main__":
    sys.exit(main())
