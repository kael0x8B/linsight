"""Configured lower bound for rule confirmation latency.

The Runtime evaluates a rule only when a sampled frame arrives.  N-of-M first
becomes stable on the Nth positive sample; a duration threshold can then only
complete on a later sample boundary.  This is a lower bound: inference,
tracking, upload and UI delivery add more time.
"""

import math

EVENT_VISIBILITY_TARGET_SECONDS = 2.0


def thresholds(ast: dict) -> tuple[int, int, float]:
    values = {"n": 1, "m": 1, "duration": 0.0}

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "N_OF_M":
            values["n"] = int(node.get("n", 1))
            values["m"] = int(node.get("m", values["n"]))
        elif node.get("type") == "DURATION":
            values["duration"] = float(node.get("seconds", 0))
        for child in node.get("children", []):
            visit(child)
        visit(node.get("child"))

    visit(ast.get("condition"))
    return int(values["n"]), int(values["m"]), float(values["duration"])


def minimum_confirmation_seconds(ast: dict, sample_fps: float) -> float:
    if sample_fps <= 0:
        raise ValueError("sampleFps must be greater than zero")
    n, _, duration = thresholds(ast)
    duration_intervals = math.ceil(max(0.0, duration * sample_fps) - 1e-12)
    return ((n - 1) + duration_intervals) / sample_fps


def conflicts_with_visibility_target(
    ast: dict,
    sample_fps: float,
    target_seconds: float = EVENT_VISIBILITY_TARGET_SECONDS,
) -> bool:
    return minimum_confirmation_seconds(ast, sample_fps) > target_seconds + 1e-9
