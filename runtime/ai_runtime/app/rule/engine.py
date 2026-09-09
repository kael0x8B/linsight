from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.rule.contracts import Region, RuleAst, RuleTransition


@dataclass
class _TrackState:
    history: deque[bool]
    state: str = "IDLE"
    stable_since_millis: int | None = None
    last_match_millis: int | None = None
    cooldown_until_millis: int = 0
    active_dedup_key: str | None = None
    activity_id: str | None = None
    alarmed: bool = False
    last_center: tuple[float, float] | None = None
    path_length: float = 0.0
    observed_since_millis: int | None = None
    last_detection: DetectionObject | None = None


@dataclass
class RuleEngine:
    task_id: int
    camera_id: int
    ast: RuleAst
    _states: dict[str, _TrackState] = field(default_factory=dict)

    def evaluate(
        self, objects: list[DetectionObject], occurred_at_millis: int
    ) -> list[RuleTransition]:
        if not self._schedule_active(occurred_at_millis):
            return []
        n, m, duration_seconds = _thresholds(self.ast.condition)
        count_condition = _count_condition(self.ast.condition)
        if count_condition is not None:
            comparison, minimum, classes = count_condition
            observed = sum(
                detected.class_name in classes and self._inside_region(detected)
                for detected in objects
            )
            return self._evaluate_scene_count(
                observed < minimum if comparison == "BELOW" else observed >= minimum,
                observed,
                minimum,
                comparison,
                occurred_at_millis,
                n,
                m,
                duration_seconds,
            )
        if (
            self.ast.dedup.scope == "CAMERA_TASK_TYPE"
            and _find_condition(self.ast.condition, "STATIONARY") is None
            and _find_condition(self.ast.condition, "LOITERING") is None
        ):
            # Presence alarms such as smoke belong to the scene, not to unstable
            # detector tracks. Count one observation per frame and retain a real
            # matching object for evidence. Motion rules still need track state.
            classes = _object_classes(self.ast.condition)
            candidates = [
                detected for detected in objects
                if detected.class_name in classes and self._inside_region(detected)
            ]
            objects = [max(candidates, key=lambda item: item.confidence).model_copy(
                update={"track_id": None}
            )] if candidates else []
        transitions: list[RuleTransition] = []
        matched_ids: set[str] = set()
        observed_ids: set[str] = set()
        for detected in objects:
            track_id = detected.track_id or "untracked"
            observed_ids.add(track_id)
            state = self._states.setdefault(track_id, _TrackState(deque(maxlen=m)))
            matched = self._matches_roi(detected, state, occurred_at_millis)
            if matched:
                matched_ids.add(track_id)
                state.last_detection = detected
            state.history.append(matched)
            matched_frames = sum(state.history)
            stable = len(state.history) >= n and matched_frames >= n
            if matched:
                state.last_match_millis = occurred_at_millis
                if state.state == "IDLE":
                    state.active_dedup_key = self._dedup_key(track_id, occurred_at_millis)
                    state.activity_id = self._activity_id(track_id, occurred_at_millis)
                    state.state = "DETECTED"
                    transitions.append(
                        self._transition(
                            "DETECTED",
                            detected,
                            occurred_at_millis,
                            state.active_dedup_key,
                            state.activity_id,
                        )
                    )
            if stable:
                if state.stable_since_millis is None:
                    state.stable_since_millis = occurred_at_millis
                    state.state = "PENDING"
                    transitions.append(
                        self._transition(
                            "PENDING",
                            detected,
                            occurred_at_millis,
                            state.active_dedup_key,
                            state.activity_id,
                        )
                    )
                elapsed = occurred_at_millis - state.stable_since_millis
                if (
                    elapsed >= duration_seconds * 1000
                    and occurred_at_millis >= state.cooldown_until_millis
                    and not state.alarmed
                ):
                    if state.state != "COOLDOWN":
                        state.state = "CONFIRMED"
                        transitions.append(
                            self._transition(
                                "CONFIRMED",
                                detected,
                                occurred_at_millis,
                                state.active_dedup_key,
                                state.activity_id,
                            )
                        )
                        transitions.append(
                            self._transition(
                                "ALARM",
                                detected,
                                occurred_at_millis,
                                state.active_dedup_key,
                                state.activity_id,
                            )
                        )
                        state.alarmed = True
                        state.cooldown_until_millis = occurred_at_millis + round(
                            self.ast.cooldown_seconds * 1000
                        )
                        state.state = "COOLDOWN"
            elif not matched:
                state.stable_since_millis = None

        recovery_millis = round(self.ast.recovery_seconds * 1000)
        for track_id, state in list(self._states.items()):
            if track_id in matched_ids or state.active_dedup_key is None:
                continue
            if track_id not in observed_ids:
                # An absent candidate is a negative frame too (for example,
                # a tracked person becoming compliant/unknown in a PPE task).
                state.history.append(False)
                state.stable_since_millis = None
            if (
                state.last_match_millis is not None
                and occurred_at_millis - state.last_match_millis >= recovery_millis
            ):
                snapshot = state.last_detection or DetectionObject.model_validate(
                    {
                        "class": "person",
                        "confidence": 0,
                        "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
                        "trackId": track_id,
                    }
                )
                if state.alarmed:
                    transitions.append(
                        self._transition(
                            "RECOVERED",
                            snapshot,
                            occurred_at_millis,
                            state.active_dedup_key,
                            state.activity_id,
                        )
                    )
                    transitions.append(
                        self._transition(
                            "CLOSED",
                            snapshot,
                            occurred_at_millis,
                            state.active_dedup_key,
                            state.activity_id,
                        )
                    )
                self._states.pop(track_id, None)
        return transitions

    def _matches_roi(
        self, detected: DetectionObject, state: _TrackState, occurred_at_millis: int
    ) -> bool:
        classes = _object_classes(self.ast.condition)
        if detected.class_name not in classes:
            return False
        inside = self._inside_region(detected)
        bbox = detected.bbox
        center = (bbox.x + bbox.width / 2, bbox.y + bbox.height / 2)
        movement = 0.0
        if state.last_center is not None:
            movement = (
                (center[0] - state.last_center[0]) ** 2 + (center[1] - state.last_center[1]) ** 2
            ) ** 0.5
            if inside:
                state.path_length += movement
        state.last_center = center
        if not inside:
            state.path_length = 0.0
            state.observed_since_millis = None
            return False
        if state.observed_since_millis is None:
            state.observed_since_millis = occurred_at_millis
        stationary = _find_condition(self.ast.condition, "STATIONARY")
        if stationary is not None and movement > float(stationary["maxMovement"]):
            return False
        loitering = _find_condition(self.ast.condition, "LOITERING")
        if loitering is not None:
            elapsed = occurred_at_millis - state.observed_since_millis
            return (
                state.path_length >= float(loitering["minPathLength"])
                and elapsed >= float(loitering["seconds"]) * 1000
            )
        return True

    def _inside_region(self, detected: DetectionObject) -> bool:
        region = self.ast.regions[0]
        bbox = detected.bbox
        x = bbox.x + bbox.width / 2
        y = bbox.y + bbox.height if region.point_mode == "FOOT" else bbox.y + bbox.height / 2
        return _contains(region, x, y)

    def _evaluate_scene_count(
        self,
        matched: bool,
        observed: int,
        minimum: int,
        comparison: str,
        occurred_at_millis: int,
        n: int,
        m: int,
        duration_seconds: float,
    ) -> list[RuleTransition]:
        key = "scene"
        state = self._states.setdefault(key, _TrackState(deque(maxlen=m)))
        state.history.append(matched)
        snapshot = DetectionObject.model_validate(
            {
                "class": "scene",
                "confidence": 1,
                "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
                "attributes": {
                    "observedCount": observed,
                    "minimumCount": minimum,
                    "thresholdCount": minimum,
                    "comparison": comparison,
                },
            }
        )
        transitions: list[RuleTransition] = []
        stable = matched and len(state.history) >= n and sum(state.history) >= n
        if matched:
            state.last_match_millis = occurred_at_millis
            if state.state == "IDLE":
                state.active_dedup_key = self._dedup_key(key, occurred_at_millis)
                state.activity_id = self._activity_id(key, occurred_at_millis)
                state.state = "DETECTED"
                transitions.append(
                    self._transition(
                        "DETECTED",
                        snapshot,
                        occurred_at_millis,
                        state.active_dedup_key,
                        state.activity_id,
                    )
                )
        if stable:
            if state.stable_since_millis is None:
                state.stable_since_millis = occurred_at_millis
                state.state = "PENDING"
                transitions.append(
                    self._transition(
                        "PENDING",
                        snapshot,
                        occurred_at_millis,
                        state.active_dedup_key,
                        state.activity_id,
                    )
                )
            if (
                occurred_at_millis - state.stable_since_millis >= duration_seconds * 1000
                and occurred_at_millis >= state.cooldown_until_millis
                and state.state != "COOLDOWN"
                and not state.alarmed
            ):
                transitions.extend(
                    self._transition(
                        transition_state,
                        snapshot,
                        occurred_at_millis,
                        state.active_dedup_key,
                        state.activity_id,
                    )
                    for transition_state in ("CONFIRMED", "ALARM")
                )
                state.alarmed = True
                state.cooldown_until_millis = occurred_at_millis + round(
                    self.ast.cooldown_seconds * 1000
                )
                state.state = "COOLDOWN"
        elif not matched:
            state.stable_since_millis = None
            if (
                state.active_dedup_key is not None
                and state.last_match_millis is not None
                and occurred_at_millis - state.last_match_millis
                >= round(self.ast.recovery_seconds * 1000)
            ):
                if state.alarmed:
                    transitions.extend(
                        self._transition(
                            transition_state,
                            snapshot,
                            occurred_at_millis,
                            state.active_dedup_key,
                            state.activity_id,
                        )
                        for transition_state in ("RECOVERED", "CLOSED")
                    )
                self._states.pop(key, None)
        return transitions

    def _schedule_active(self, occurred_at_millis: int) -> bool:
        local = datetime.fromtimestamp(
            occurred_at_millis / 1000, tz=ZoneInfo(self.ast.schedule.timezone)
        )
        current = local.strftime("%H:%M")
        return any(
            local.isoweekday() in slot.days and slot.start <= current <= slot.end
            for slot in self.ast.schedule.weekly
        )

    def _dedup_key(self, track_id: str, occurred_at_millis: int) -> str:
        if self.ast.dedup.scope == "TRACK":
            return f"{self.camera_id}:{self.task_id}:{self.ast.event_type}:{track_id}"
        bucket = int(occurred_at_millis / (self.ast.dedup.window_seconds * 1000))
        return f"{self.camera_id}:{self.task_id}:{self.ast.event_type}:{bucket}"

    def _activity_id(self, track_id: str, occurred_at_millis: int) -> str:
        value = (
            f"linsight://rule-activity/{self.camera_id}/{self.task_id}/"
            f"{self.ast.event_type}/{track_id}/{occurred_at_millis}"
        )
        return str(uuid5(NAMESPACE_URL, value))

    def _transition(
        self,
        state: str,
        detected: DetectionObject,
        occurred_at_millis: int,
        dedup_key: str | None = None,
        activity_id: str | None = None,
    ) -> RuleTransition:
        key = dedup_key or self._dedup_key(detected.track_id or "untracked", occurred_at_millis)
        source_id = activity_id or self._activity_id(
            detected.track_id or "untracked", occurred_at_millis
        )
        return RuleTransition.model_validate(
            {
                "state": state,
                "eventType": self.ast.event_type,
                "severity": self.ast.severity,
                "occurredAtMillis": occurred_at_millis,
                "trackId": detected.track_id,
                "dedupKey": key,
                "activityId": source_id,
                "sourceEventId": source_id,
                "objectSnapshot": detected.model_dump(by_alias=True),
                "ruleSnapshot": self.ast.model_dump(by_alias=True),
            }
        )


def _contains(region: Region, x: float, y: float) -> bool:
    inside = False
    points = region.points
    previous = len(points) - 1
    for current, point in enumerate(points):
        other = points[previous]
        if (point.y > y) != (other.y > y) and x < (other.x - point.x) * (y - point.y) / (
            other.y - point.y
        ) + point.x:
            inside = not inside
        previous = current
    return inside


def _thresholds(condition: dict) -> tuple[int, int, float]:
    result: dict[str, float | int] = {"n": 1, "m": 1, "duration": 0.0}

    def collect(node: dict) -> None:
        if node.get("type") == "N_OF_M":
            result["n"], result["m"] = int(node["n"]), int(node["m"])
        elif node.get("type") == "DURATION":
            result["duration"] = float(node["seconds"])
        for child in node.get("children", []):
            collect(child)
        if isinstance(node.get("child"), dict):
            collect(node["child"])

    collect(condition)
    return int(result["n"]), int(result["m"]), float(result["duration"])


def _find_condition(condition: dict, expected_type: str) -> dict | None:
    if condition.get("type") == expected_type:
        return condition
    for child in condition.get("children", []):
        if isinstance(child, dict):
            result = _find_condition(child, expected_type)
            if result is not None:
                return result
    child = condition.get("child")
    return _find_condition(child, expected_type) if isinstance(child, dict) else None


def _object_classes(condition: dict) -> set[str]:
    result: set[str] = set()

    def collect(node: dict) -> None:
        result.update(str(value) for value in node.get("objectClasses", []))
        for child in node.get("children", []):
            collect(child)
        if isinstance(node.get("child"), dict):
            collect(node["child"])

    collect(condition)
    return result or {"person"}


def _count_condition(condition: dict) -> tuple[str, int, set[str]] | None:
    result: tuple[str, int, set[str]] | None = None
    fallback_classes = _object_classes(condition)

    def collect(node: dict) -> None:
        nonlocal result
        if node.get("type") in {"COUNT", "COUNT_BELOW"}:
            result = (
                "BELOW" if node["type"] == "COUNT_BELOW" else "AT_LEAST",
                int(node["min"]),
                {str(value) for value in node.get("objectClasses", fallback_classes)},
            )
        for child in node.get("children", []):
            collect(child)
        if isinstance(node.get("child"), dict):
            collect(node["child"])

    collect(condition)
    return result
