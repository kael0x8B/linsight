#!/usr/bin/env python3
"""Create and validate tamper-evident LInsight production acceptance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

EVIDENCE_TYPES = (
    "algorithmAcceptance",
    "weakNetwork30Minutes",
    "apiLoadP95",
    "securityScan",
    "edgeRollback",
    "observabilityDashboard",
)
MODEL_CODES = {
    "safety-helmet",
    "sleeping-on-duty",
    "person-detection",
    "license-plate",
    "reflective-vest",
    "flame",
    "smoking-detection",
    "phone-call-detection",
    "road-waterlogging",
    "face-mask",
    "fall-detection",
    "face-detection",
}
ALGORITHM_CODES = {
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
}
SECURITY_SCOPES = {"containerImage", "operatingSystem", "javaArtifact"}
SECURITY_CONTROLS = {
    "authorization",
    "credentialProtection",
    "signedUrl",
    "uploadBoundary",
    "nodeAuthentication",
}
OBSERVABILITY_COVERAGE = {
    "apiLatency",
    "apiErrorRate",
    "taskThroughput",
    "eventThroughput",
    "notificationRetries",
    "objectStorageFailures",
    "streamState",
    "reconnects",
    "inputFps",
    "analysisFps",
    "queueDepth",
    "inferenceLatency",
    "gpuMemory",
    "droppedFrames",
    "evidenceBacklog",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
DIGEST_PATTERN = re.compile(r"(?:sha256:)?[0-9a-f]{64}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not value.strip().lower().startswith("replace-with")
    )


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _timestamp(value: Any, errors: list[str], field: str) -> None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
        now = datetime.now(UTC)
        if parsed > now + timedelta(minutes=5) or parsed < now - timedelta(days=90):
            errors.append(f"{field} must be within the last 90 days")
    except (TypeError, ValueError):
        errors.append(f"{field} must be an ISO-8601 timestamp with timezone")


def _exact_codes(items: Any, expected: set[str], field: str, errors: list[str]) -> dict[str, dict]:
    if not isinstance(items, list):
        errors.append(f"{field} must be an array")
        return {}
    values: dict[str, dict] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not _text(item.get("code")):
            errors.append(f"{field}[{index}].code is required")
            continue
        code = item["code"]
        if code in values:
            errors.append(f"{field} contains duplicate code {code}")
        values[code] = item
    missing = sorted(expected.difference(values))
    extra = sorted(set(values).difference(expected))
    if missing:
        errors.append(f"{field} missing codes: {missing}")
    if extra:
        errors.append(f"{field} has unknown codes: {extra}")
    return values


def _validate_raw_artifacts(
    report: dict, report_path: Path, evidence_root: Path, errors: list[str]
) -> list[dict]:
    structured: list[dict] = []
    artifacts = report.get("rawArtifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("rawArtifacts must contain at least one original log, scan, export or screenshot")
        return structured
    root = evidence_root.resolve()
    for index, artifact in enumerate(artifacts):
        field = f"rawArtifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{field} must be an object")
            continue
        relative = artifact.get("path")
        expected_hash = artifact.get("sha256")
        if not _text(relative) or Path(relative).is_absolute():
            errors.append(f"{field}.path must be relative to the evidence directory")
            continue
        path = (report_path.parent / relative).resolve()
        if path == report_path.resolve() or root not in path.parents:
            errors.append(f"{field}.path escapes the evidence directory or references the report itself")
            continue
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"{field}.path is missing or empty")
            continue
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            errors.append(f"{field}.sha256 is invalid")
        elif sha256(path) != expected_hash:
            errors.append(f"{field}.sha256 does not match")
        else:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                structured.append(value)
    return structured


def _valid_runtime_series(
    artifacts: list[dict], report: dict, errors: list[str]
) -> list[dict]:
    values = [
        artifact
        for artifact in artifacts
        if artifact.get("schemaVersion") == "1.0"
        and artifact.get("artifactType") == "runtimeObservabilitySeries"
    ]
    for index, artifact in enumerate(values):
        field = f"runtimeObservabilitySeries[{index}]"
        if artifact.get("environment") != report.get("environment"):
            errors.append(f"{field}.environment must exactly match the evidence report")
        if artifact.get("runId") != report.get("runId"):
            errors.append(f"{field}.runId must exactly match the evidence report")
        _timestamp(artifact.get("generatedAt"), errors, f"{field}.generatedAt")
        summary = artifact.get("summary")
        if not isinstance(summary, dict):
            errors.append(f"{field}.summary is required")
            continue
        samples = summary.get("sampleCount")
        successful = summary.get("successfulRuntimeSamples")
        if not _integer(samples) or samples < 1 or successful != samples:
            errors.append(f"{field} must contain only successful Runtime samples")
    return values


def _validate_collected_artifacts(
    evidence_type: str, report: dict, artifacts: list[dict], errors: list[str]
) -> None:
    if evidence_type not in {
        "weakNetwork30Minutes",
        "apiLoadP95",
        "observabilityDashboard",
    }:
        return
    series = _valid_runtime_series(artifacts, report, errors)
    if not series:
        errors.append(
            f"{evidence_type} requires a runtimeObservabilitySeries generated by the field collector"
        )
        return
    summaries = [value.get("summary", {}) for value in series]
    if evidence_type == "weakNetwork30Minutes":
        outage = [
            value
            for value in summaries
            if _number(value.get("observedSeconds"))
            and value["observedSeconds"] >= 1800
            and value.get("controlPlaneConfigured") is True
            and value.get("controlPlaneReachableSamples") == 0
            and _number(value.get("runningTasksMin"))
            and value["runningTasksMin"] >= 1
            and _number(value.get("analysisFpsMin"))
            and value["analysisFpsMin"] > 0
            and _number(value.get("activeStreamsMax"))
            and value["activeStreamsMax"] >= 1
            and _number(value.get("pendingEventsMax"))
            and _number(value.get("pendingEventsFirst"))
            and value["pendingEventsMax"] > value["pendingEventsFirst"]
            and _number(value.get("evidenceBacklogBytesMax"))
            and _number(value.get("evidenceBacklogBytesFirst"))
            and value["evidenceBacklogBytesMax"] > value["evidenceBacklogBytesFirst"]
            and value.get("missingMediaFilesMax") == 0
            and "deadLetterTransitionsFirst" in value
            and value.get("deadLetterTransitionsMax")
            == value.get("deadLetterTransitionsFirst")
            and value.get("deadLetterTransitionsFinal")
            == value.get("deadLetterTransitionsFirst")
        ]
        recovered = [
            value
            for value in summaries
            if value.get("controlPlaneConfigured") is True
            and value.get("controlPlaneReachableSamples", 0) > 0
            and value.get("pendingEventsFinal") == 0
            and value.get("pendingTransitionsFinal") == 0
            and value.get("missingMediaFilesMax") == 0
            and "deadLetterTransitionsFirst" in value
            and value.get("deadLetterTransitionsMax")
            == value.get("deadLetterTransitionsFirst")
            and value.get("deadLetterTransitionsFinal")
            == value.get("deadLetterTransitionsFirst")
        ]
        if not outage:
            errors.append(
                "weakNetwork30Minutes requires a 1800-second collector series with the "
                "control plane unreachable, active inference and growing valid backlog"
            )
        if not recovered:
            errors.append(
                "weakNetwork30Minutes requires a post-recovery collector series with empty queues"
            )
    elif evidence_type == "apiLoadP95":
        tested_streams = report.get("runtime", {}).get("testedStreamCount", 0)
        analysis_fps = report.get("runtime", {}).get("analysisFps", 0)
        inference_p95 = report.get("runtime", {}).get("inferenceP95Ms", 0)
        tested_streams = tested_streams if _number(tested_streams) else 0
        analysis_fps = analysis_fps if _number(analysis_fps) else 0
        inference_p95 = inference_p95 if _number(inference_p95) else 0
        if not any(
            _number(value.get("activeStreamsMax"))
            and value["activeStreamsMax"] >= tested_streams
            and _number(value.get("analysisFpsMin"))
            and value["analysisFpsMin"] >= analysis_fps
            and _number(value.get("inferenceP95MillisMax"))
            and 0 < value["inferenceP95MillisMax"] <= inference_p95
            for value in summaries
        ):
            errors.append(
                "apiLoadP95 collector output does not prove the reported stream count, FPS "
                "and inference P95"
            )
    else:
        required_snapshot_fields = {
            "process": {"cpuPercent", "residentMemoryBytes", "openFileCount"},
            "tasks": {"running", "analysisFps", "queueDepth", "inferenceP95Millis"},
            "streams": {"active", "inputFps", "droppedFrames", "reconnects"},
            "models": {"loaded", "capacity"},
            "delivery": {
                "pendingEvents",
                "pendingTransitions",
                "evidenceBacklogBytes",
                "missingMediaFiles",
            },
        }
        valid_snapshot = any(
            isinstance(samples, list)
            and any(
                isinstance(sample, dict)
                and isinstance(sample.get("snapshot"), dict)
                and all(
                    isinstance(sample["snapshot"].get(group), dict)
                    and fields.issubset(sample["snapshot"][group])
                    for group, fields in required_snapshot_fields.items()
                )
                for sample in samples
            )
            for artifact in series
            for samples in (artifact.get("samples"),)
        )
        if not valid_snapshot:
            errors.append("observabilityDashboard collector output is missing Runtime metric groups")


def _validate_algorithm(report: dict, errors: list[str]) -> None:
    assets = _exact_codes(report.get("modelAssets"), MODEL_CODES, "modelAssets", errors)
    for code, asset in assets.items():
        field = f"modelAssets[{code}]"
        for name in ("sourceUrl", "sourceRevision", "licenseSpdx"):
            if not _text(asset.get(name)):
                errors.append(f"{field}.{name} is required")
        if not isinstance(asset.get("artifactSha256"), str) or not SHA256_PATTERN.fullmatch(asset["artifactSha256"]):
            errors.append(f"{field}.artifactSha256 is invalid")
        for name in ("singleImageTest", "nodeDeployment", "standardizedOutput"):
            if asset.get(name) != "PASS":
                errors.append(f"{field}.{name} must be PASS")

    algorithms = _exact_codes(report.get("algorithms"), ALGORITHM_CODES, "algorithms", errors)
    for code, algorithm in algorithms.items():
        field = f"algorithms[{code}]"
        if algorithm.get("status") != "PASS":
            errors.append(f"{field}.status must be PASS")
        if not _text(algorithm.get("datasetVersion")):
            errors.append(f"{field}.datasetVersion is required")
        dataset_hash = algorithm.get("datasetSha256")
        if not isinstance(dataset_hash, str) or not SHA256_PATTERN.fullmatch(dataset_hash):
            errors.append(f"{field}.datasetSha256 is invalid")
        metrics = algorithm.get("metrics")
        thresholds = algorithm.get("thresholds")
        if not isinstance(metrics, dict) or not isinstance(thresholds, dict):
            errors.append(f"{field}.metrics and thresholds are required")
            continue
        comparisons = (
            ("eventPrecision", "minEventPrecision", lambda actual, target: actual >= target),
            ("eventRecall", "minEventRecall", lambda actual, target: actual >= target),
            (
                "falsePositivesPerStreamHour",
                "maxFalsePositivesPerStreamHour",
                lambda actual, target: actual <= target,
            ),
            ("missedEvents", "maxMissedEvents", lambda actual, target: actual <= target),
            ("endToEndP95Ms", "maxEndToEndP95Ms", lambda actual, target: actual <= target),
            ("averageFps", "minAverageFps", lambda actual, target: actual >= target),
        )
        for metric, threshold, predicate in comparisons:
            actual = metrics.get(metric)
            target = thresholds.get(threshold)
            if not _number(actual) or not _number(target):
                errors.append(f"{field}.{metric}/{threshold} must be finite numbers")
            elif not predicate(actual, target):
                errors.append(f"{field}.{metric} does not meet {threshold}")
        for name in ("eventPrecision", "eventRecall"):
            if _number(metrics.get(name)) and not 0 <= metrics[name] <= 1:
                errors.append(f"{field}.metrics.{name} must be between 0 and 1")
        for name in ("falsePositivesPerStreamHour", "endToEndP95Ms"):
            if _number(metrics.get(name)) and metrics[name] < 0:
                errors.append(f"{field}.metrics.{name} must be non-negative")
        if not _integer(metrics.get("missedEvents")) or metrics["missedEvents"] < 0:
            errors.append(f"{field}.metrics.missedEvents must be a non-negative integer")
        if _number(metrics.get("averageFps")) and metrics["averageFps"] <= 0:
            errors.append(f"{field}.metrics.averageFps must be positive")
        if _number(metrics.get("endToEndP95Ms")) and metrics["endToEndP95Ms"] >= 2000:
            errors.append(f"{field}.metrics.endToEndP95Ms must be less than 2000")
        for name in ("minEventPrecision", "minEventRecall"):
            if _number(thresholds.get(name)) and not 0 <= thresholds[name] <= 1:
                errors.append(f"{field}.thresholds.{name} must be between 0 and 1")
        max_false = thresholds.get("maxFalsePositivesPerStreamHour")
        if _number(max_false) and max_false < 0:
            errors.append(
                f"{field}.thresholds.maxFalsePositivesPerStreamHour must be non-negative"
            )
        max_missed = thresholds.get("maxMissedEvents")
        if not _integer(max_missed) or max_missed < 0:
            errors.append(f"{field}.thresholds.maxMissedEvents must be a non-negative integer")
        max_latency = thresholds.get("maxEndToEndP95Ms")
        if _number(max_latency) and not 0 < max_latency < 2000:
            errors.append(f"{field}.thresholds.maxEndToEndP95Ms must be between 0 and 2000")
        min_fps = thresholds.get("minAverageFps")
        if _number(min_fps) and min_fps <= 0:
            errors.append(f"{field}.thresholds.minAverageFps must be positive")
        if algorithm.get("cooldownDedupPass") is not True:
            errors.append(f"{field}.cooldownDedupPass must be true")
        resources = algorithm.get("resourceUsage")
        if not isinstance(resources, dict):
            errors.append(f"{field}.resourceUsage is required")
        else:
            cpu = resources.get("cpuPeakPercent")
            memory = resources.get("memoryPeakMiB")
            accelerator = resources.get("acceleratorMemoryPeakMiB")
            if not _number(cpu) or not 0 <= cpu <= 100:
                errors.append(f"{field}.resourceUsage.cpuPeakPercent must be between 0 and 100")
            if not _number(memory) or memory <= 0:
                errors.append(f"{field}.resourceUsage.memoryPeakMiB must be positive")
            if not _number(accelerator) or accelerator < 0:
                errors.append(f"{field}.resourceUsage.acceleratorMemoryPeakMiB must be non-negative")


def _validate_weak_network(report: dict, errors: list[str]) -> None:
    duration = report.get("disconnectedMinutes")
    if not _number(duration) or duration < 30:
        errors.append("disconnectedMinutes must be at least 30")
    for name in ("continuedAnalysis", "queueRestartVerified", "recoveryVerified"):
        if report.get(name) is not True:
            errors.append(f"{name} must be true")
    for name in ("events", "media"):
        counters = report.get(name)
        if not isinstance(counters, dict):
            errors.append(f"{name} counters are required")
            continue
        generated = counters.get("generated")
        uploaded = counters.get("uploaded")
        duplicates = counters.get("duplicates")
        missing = counters.get("missing")
        if not _integer(generated) or generated <= 0:
            errors.append(f"{name}.generated must be a positive integer")
        if not _integer(uploaded) or uploaded != generated:
            errors.append(f"{name}.uploaded must equal generated")
        if not _integer(duplicates) or not _integer(missing) or duplicates != 0 or missing != 0:
            errors.append(f"{name}.duplicates and missing must both be zero")
    if (
        not _integer(report.get("pendingAfterRecovery"))
        or not _integer(report.get("integrityFailures"))
        or report["pendingAfterRecovery"] != 0
        or report["integrityFailures"] != 0
    ):
        errors.append("pendingAfterRecovery and integrityFailures must both be zero")
    if not _number(report.get("recoverySeconds")) or report["recoverySeconds"] < 0:
        errors.append("recoverySeconds must be non-negative")


def _validate_api_load(report: dict, errors: list[str]) -> None:
    admin = report.get("adminApi")
    if not isinstance(admin, dict):
        errors.append("adminApi results are required")
    else:
        requests = admin.get("requests")
        if not _integer(requests) or requests < 300:
            errors.append("adminApi.requests must be at least 300")
        if admin.get("success") != requests:
            errors.append("adminApi.success must equal requests")
        if not _integer(admin.get("concurrency")) or admin["concurrency"] < 1:
            errors.append("adminApi.concurrency must be positive")
        if not _number(admin.get("p95Ms")) or not 0 < admin["p95Ms"] < 500:
            errors.append("adminApi.p95Ms must be between 0 and 500")
        endpoints = admin.get("endpoints")
        if not isinstance(endpoints, list) or len(set(endpoints)) < 6:
            errors.append("adminApi.endpoints must contain at least six distinct management APIs")
    runtime = report.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime load results are required")
    else:
        target = runtime.get("targetStreamCount")
        tested = runtime.get("testedStreamCount")
        if not _integer(target) or target < 1 or not _integer(tested) or tested < target:
            errors.append("runtime.testedStreamCount must meet a positive targetStreamCount")
        for name in ("analysisFps", "inferenceP95Ms", "memoryPeakMiB"):
            if not _number(runtime.get(name)) or runtime[name] <= 0:
                errors.append(f"runtime.{name} must be positive")
        cpu = runtime.get("cpuPeakPercent")
        if not _number(cpu) or not 0 <= cpu <= 100:
            errors.append("runtime.cpuPeakPercent must be between 0 and 100")
        accelerator = runtime.get("acceleratorMemoryPeakMiB")
        if not _number(accelerator) or accelerator < 0:
            errors.append("runtime.acceleratorMemoryPeakMiB must be non-negative")
    visible = report.get("eventVisibleP95Ms")
    if not _number(visible) or not 0 < visible < 2000:
        errors.append("eventVisibleP95Ms must be between 0 and 2000")


def _validate_security(report: dict, errors: list[str]) -> None:
    scans = _exact_codes(report.get("scans"), SECURITY_SCOPES, "scans", errors)
    for scope, scan in scans.items():
        field = f"scans[{scope}]"
        for name in ("scanner", "scannerVersion", "target", "targetDigest"):
            if not _text(scan.get(name)):
                errors.append(f"{field}.{name} is required")
        digest = scan.get("targetDigest")
        if isinstance(digest, str) and _text(digest) and not DIGEST_PATTERN.fullmatch(digest):
            errors.append(f"{field}.targetDigest must be a SHA256 digest")
        if (
            scan.get("status") != "PASS"
            or not _integer(scan.get("critical"))
            or not _integer(scan.get("high"))
            or scan["critical"] != 0
            or scan["high"] != 0
        ):
            errors.append(f"{field} must PASS with critical=0 and high=0")
        for name in ("medium", "low"):
            if not _integer(scan.get(name)) or scan[name] < 0:
                errors.append(f"{field}.{name} must be a non-negative integer")
    controls = _exact_codes(report.get("controls"), SECURITY_CONTROLS, "controls", errors)
    for code, control in controls.items():
        if control.get("status") != "PASS" or not _text(control.get("summary")):
            errors.append(f"controls[{code}] must have PASS status and a summary")


def _validate_rollback(report: dict, errors: list[str]) -> None:
    for name in ("nodeId", "fromVersion", "attemptedVersion", "finalVersion"):
        if not _text(report.get(name)):
            errors.append(f"{name} is required")
    if report.get("finalVersion") != report.get("fromVersion"):
        errors.append("finalVersion must equal fromVersion after rollback")
    digest = report.get("packageSha256")
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        errors.append("packageSha256 is invalid")
    for name in (
        "signatureVerified",
        "healthFailureDetected",
        "rollbackSucceeded",
        "heartbeatRestored",
        "tasksRestored",
        "offlineReplayVerified",
    ):
        if report.get(name) is not True:
            errors.append(f"{name} must be true")


def _validate_observability(report: dict, errors: list[str]) -> None:
    if not _text(report.get("dashboardUrl")):
        errors.append("dashboardUrl is required")
    coverage = report.get("coverage")
    if not isinstance(coverage, list):
        errors.append("coverage must be an array")
    else:
        missing = sorted(OBSERVABILITY_COVERAGE.difference(coverage))
        if missing:
            errors.append(f"coverage missing metrics: {missing}")
    routes = report.get("alertRoutes")
    if not isinstance(routes, list) or not routes:
        errors.append("alertRoutes must contain at least one tested route")
    else:
        for index, route in enumerate(routes):
            if not isinstance(route, dict) or any(
                not _text(route.get(name)) for name in ("name", "channel", "owner")
            ) or route.get("testStatus") != "PASS":
                errors.append(f"alertRoutes[{index}] is incomplete or not PASS")
    if report.get("dashboardCaptured") is not True:
        errors.append("dashboardCaptured must be true")


VALIDATORS = {
    "algorithmAcceptance": _validate_algorithm,
    "weakNetwork30Minutes": _validate_weak_network,
    "apiLoadP95": _validate_api_load,
    "securityScan": _validate_security,
    "edgeRollback": _validate_rollback,
    "observabilityDashboard": _validate_observability,
}


def validate_evidence_report(
    report: Any,
    evidence_type: str,
    report_path: Path,
    evidence_root: Path,
    expected_environment: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report must be a JSON object"]
    if report.get("schemaVersion") != "1.0":
        errors.append("schemaVersion must be 1.0")
    if report.get("evidenceType") != evidence_type:
        errors.append(f"evidenceType must be {evidence_type}")
    if report.get("status") != "PASS":
        errors.append("status must be PASS")
    _timestamp(report.get("generatedAt"), errors, "generatedAt")
    environment = report.get("environment")
    if not isinstance(environment, dict) or any(
        not _text(environment.get(name)) for name in ("name", "hardware", "softwareVersion")
    ):
        errors.append("environment name/hardware/softwareVersion are required")
    elif expected_environment is not None and environment != expected_environment:
        errors.append("environment must exactly match production-acceptance.json")
    if not _text(report.get("runId")):
        errors.append("runId is required")
    artifacts = _validate_raw_artifacts(report, report_path, evidence_root, errors)
    _validate_collected_artifacts(evidence_type, report, artifacts, errors)
    validator = VALIDATORS.get(evidence_type)
    if validator is None:
        errors.append(f"unsupported evidence type: {evidence_type}")
    else:
        validator(report, errors)
    return errors


def validate_manifest(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"invalid manifest: {error}"]
    if manifest.get("schemaVersion") != "1.1":
        errors.append("manifest schemaVersion must be 1.1")
    _timestamp(manifest.get("generatedAt"), errors, "manifest.generatedAt")
    environment = manifest.get("environment")
    if not isinstance(environment, dict):
        errors.append("manifest environment is required")
        environment = None
    root = path.parent.resolve()
    for evidence_type in EVIDENCE_TYPES:
        entry = manifest.get(evidence_type)
        if not isinstance(entry, dict) or entry.get("status") != "PASS":
            errors.append(f"{evidence_type}.status must be PASS")
            continue
        files = entry.get("evidenceFiles")
        if not isinstance(files, list) or not files:
            errors.append(f"{evidence_type}.evidenceFiles is required")
            continue
        structured = 0
        for index, item in enumerate(files):
            field = f"{evidence_type}.evidenceFiles[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{field} must be an object")
                continue
            relative = item.get("path")
            expected_hash = item.get("sha256")
            if not _text(relative) or Path(relative).is_absolute():
                errors.append(f"{field}.path must be relative")
                continue
            report_path = (root / relative).resolve()
            if root not in report_path.parents or not report_path.is_file():
                errors.append(f"{field}.path is outside the evidence directory or missing")
                continue
            if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
                errors.append(f"{field}.sha256 is invalid")
                continue
            if sha256(report_path) != expected_hash:
                errors.append(f"{field}.sha256 does not match")
                continue
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(report, dict) and report.get("evidenceType") == evidence_type:
                structured += 1
                errors.extend(
                    f"{field}: {message}"
                    for message in validate_evidence_report(
                        report, evidence_type, report_path, root, environment
                    )
                )
        if structured != 1:
            errors.append(f"{evidence_type} must contain exactly one structured JSON report")
    return errors


def _pending_report(evidence_type: str, environment: dict[str, str]) -> dict:
    report = {
        "schemaVersion": "1.0",
        "evidenceType": evidence_type,
        "status": "PENDING",
        "generatedAt": datetime.now(UTC).isoformat(),
        "runId": "replace-with-field-run-id",
        "environment": environment,
        "rawArtifacts": [
            {
                "path": f"../raw/{evidence_type}.log",
                "sha256": "replace-with-lowercase-sha256",
            }
        ],
    }
    if evidence_type == "algorithmAcceptance":
        report["modelAssets"] = [
            {
                "code": code,
                "sourceUrl": "replace-with-source-url",
                "sourceRevision": "replace-with-immutable-commit-or-tag",
                "artifactSha256": "replace-with-model-sha256",
                "licenseSpdx": "replace-with-license-or-usage-terms",
                "singleImageTest": "PENDING",
                "nodeDeployment": "PENDING",
                "standardizedOutput": "PENDING",
            }
            for code in sorted(MODEL_CODES)
        ]
        report["algorithms"] = [
            {
                "code": code,
                "status": "PENDING",
                "datasetVersion": "replace-with-fixed-dataset-version",
                "datasetSha256": "replace-with-dataset-sha256",
                "metrics": {
                    "eventPrecision": None,
                    "eventRecall": None,
                    "falsePositivesPerStreamHour": None,
                    "missedEvents": None,
                    "endToEndP95Ms": None,
                    "averageFps": None,
                },
                "thresholds": {
                    "minEventPrecision": None,
                    "minEventRecall": None,
                    "maxFalsePositivesPerStreamHour": None,
                    "maxMissedEvents": None,
                    "maxEndToEndP95Ms": None,
                    "minAverageFps": None,
                },
                "cooldownDedupPass": False,
                "resourceUsage": {
                    "cpuPeakPercent": None,
                    "memoryPeakMiB": None,
                    "acceleratorMemoryPeakMiB": None,
                },
            }
            for code in sorted(ALGORITHM_CODES)
        ]
    elif evidence_type == "weakNetwork30Minutes":
        report["rawArtifacts"] = [
            {
                "path": "../raw/weak-network-outage-runtime-series.json",
                "sha256": "replace-with-lowercase-sha256",
            },
            {
                "path": "../raw/weak-network-recovery-runtime-series.json",
                "sha256": "replace-with-lowercase-sha256",
            },
        ]
        report.update(
            {
                "disconnectedMinutes": None,
                "continuedAnalysis": False,
                "queueRestartVerified": False,
                "recoveryVerified": False,
                "events": {"generated": None, "uploaded": None, "duplicates": None, "missing": None},
                "media": {"generated": None, "uploaded": None, "duplicates": None, "missing": None},
                "pendingAfterRecovery": None,
                "integrityFailures": None,
                "recoverySeconds": None,
            }
        )
    elif evidence_type == "apiLoadP95":
        report["rawArtifacts"] = [
            {
                "path": "../raw/api-load-runtime-series.json",
                "sha256": "replace-with-lowercase-sha256",
            },
            {
                "path": "../raw/admin-api-load-report.json",
                "sha256": "replace-with-lowercase-sha256",
            },
        ]
        report.update(
            {
                "adminApi": {
                    "requests": None,
                    "success": None,
                    "concurrency": None,
                    "p95Ms": None,
                    "endpoints": [],
                },
                "runtime": {
                    "targetStreamCount": None,
                    "testedStreamCount": None,
                    "analysisFps": None,
                    "inferenceP95Ms": None,
                    "cpuPeakPercent": None,
                    "memoryPeakMiB": None,
                    "acceleratorMemoryPeakMiB": None,
                },
                "eventVisibleP95Ms": None,
            }
        )
    elif evidence_type == "securityScan":
        report["scans"] = [
            {
                "code": code,
                "status": "PENDING",
                "scanner": "replace-with-scanner",
                "scannerVersion": "replace-with-version",
                "target": "replace-with-scanned-target",
                "targetDigest": "replace-with-immutable-digest",
                "critical": None,
                "high": None,
                "medium": None,
                "low": None,
            }
            for code in sorted(SECURITY_SCOPES)
        ]
        report["controls"] = [
            {"code": code, "status": "PENDING", "summary": "replace-with-result"}
            for code in sorted(SECURITY_CONTROLS)
        ]
    elif evidence_type == "edgeRollback":
        report.update(
            {
                "nodeId": "replace-with-node-id",
                "fromVersion": "replace-with-known-good-version",
                "attemptedVersion": "replace-with-failed-version",
                "finalVersion": "replace-with-restored-version",
                "packageSha256": "replace-with-package-sha256",
                "signatureVerified": False,
                "healthFailureDetected": False,
                "rollbackSucceeded": False,
                "heartbeatRestored": False,
                "tasksRestored": False,
                "offlineReplayVerified": False,
            }
        )
    elif evidence_type == "observabilityDashboard":
        report["rawArtifacts"] = [
            {
                "path": "../raw/observability-runtime-series.json",
                "sha256": "replace-with-lowercase-sha256",
            },
            {
                "path": "../raw/observability-dashboard.png",
                "sha256": "replace-with-lowercase-sha256",
            },
        ]
        report.update(
            {
                "dashboardUrl": "replace-with-dashboard-url",
                "coverage": sorted(OBSERVABILITY_COVERAGE),
                "alertRoutes": [
                    {
                        "name": "replace-with-alert-name",
                        "channel": "replace-with-channel",
                        "owner": "replace-with-on-call-owner",
                        "testStatus": "PENDING",
                    }
                ],
                "dashboardCaptured": False,
            }
        )
    return report


def initialize_workspace(directory: Path, environment: dict[str, str]) -> None:
    targets = [directory / "production-acceptance.json"] + [
        directory / "reports" / f"{evidence_type}.json"
        for evidence_type in EVIDENCE_TYPES
    ]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite existing evidence files: {existing}")
    reports = directory / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (directory / "raw").mkdir(parents=True, exist_ok=True)
    for evidence_type in EVIDENCE_TYPES:
        report = _pending_report(evidence_type, environment)
        (reports / f"{evidence_type}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    manifest = {
        "schemaVersion": "1.1",
        "generatedAt": datetime.now(UTC).isoformat(),
        "environment": environment,
        **{
            evidence_type: {
                "status": "PENDING",
                "summary": "Complete and validate the matching structured report",
                "evidenceFiles": [],
            }
            for evidence_type in EVIDENCE_TYPES
        },
    }
    (directory / "production-acceptance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def assemble_manifest(directory: Path) -> Path:
    manifest_path = directory / "production-acceptance.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    environment = manifest.get("environment")
    errors: list[str] = []
    for evidence_type in EVIDENCE_TYPES:
        report_path = directory / "reports" / f"{evidence_type}.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{evidence_type}: {error}")
            continue
        errors.extend(
            f"{evidence_type}: {message}"
            for message in validate_evidence_report(
                report, evidence_type, report_path, directory, environment
            )
        )
        manifest[evidence_type] = {
            "status": "PASS",
            "summary": f"Validated structured report for {evidence_type}",
            "evidenceFiles": [
                {
                    "path": str(report_path.relative_to(directory)),
                    "sha256": sha256(report_path),
                }
            ],
        }
    if errors:
        raise ValueError("\n".join(errors))
    manifest["generatedAt"] = datetime.now(UTC).isoformat()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="create a pending field evidence workspace")
    init.add_argument("--directory", type=Path, required=True)
    init.add_argument("--environment-name", required=True)
    init.add_argument("--hardware", required=True)
    init.add_argument("--software-version", required=True)
    assemble = subparsers.add_parser("assemble", help="validate reports and assemble hashes")
    assemble.add_argument("--directory", type=Path, required=True)
    verify = subparsers.add_parser("verify", help="verify an assembled acceptance manifest")
    verify.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "init":
        try:
            initialize_workspace(
                args.directory,
                {
                    "name": args.environment_name,
                    "hardware": args.hardware,
                    "softwareVersion": args.software_version,
                },
            )
            print(args.directory / "production-acceptance.json")
            return 0
        except OSError as error:
            print(error, file=sys.stderr)
            return 1
    if args.command == "assemble":
        try:
            print(assemble_manifest(args.directory))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(error, file=sys.stderr)
            return 1
    errors = validate_manifest(args.manifest)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("production acceptance evidence is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
