from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Point(BaseModel):
    x: Annotated[float, Field(ge=0, le=1)]
    y: Annotated[float, Field(ge=0, le=1)]


class Region(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    type: Literal["POLYGON"]
    source_width: int = Field(alias="sourceWidth", gt=0)
    source_height: int = Field(alias="sourceHeight", gt=0)
    point_mode: Literal["CENTROID", "FOOT", "OVERLAP"] = Field(alias="pointMode")
    overlap_threshold: Annotated[float, Field(alias="overlapThreshold", ge=0, le=1)] = 0
    points: list[Point] = Field(min_length=3, max_length=100)

    @model_validator(mode="after")
    def validate_polygon(self) -> "Region":
        if _self_intersects(self.points):
            raise ValueError("polygon self-intersects")
        if _area(self.points) < 0.0001:
            raise ValueError("polygon area is too small")
        return self


class ScheduleSlot(BaseModel):
    days: list[Annotated[int, Field(ge=1, le=7)]] = Field(min_length=1)
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class Schedule(BaseModel):
    timezone: str
    weekly: list[ScheduleSlot] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timezone(self) -> "Schedule":
        ZoneInfo(self.timezone)
        return self


class Dedup(BaseModel):
    scope: Literal["TRACK", "CAMERA_TASK_TYPE"]
    window_seconds: Annotated[float, Field(alias="windowSeconds", gt=0, le=86400)]


class RuleAst(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = Field(alias="schemaVersion")
    event_type: str = Field(alias="eventType", pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    severity: Literal["INFO", "MINOR", "MAJOR", "CRITICAL"]
    regions: list[Region] = Field(min_length=1)
    schedule: Schedule
    condition: dict
    cooldown_seconds: Annotated[float, Field(alias="cooldownSeconds", ge=0, le=86400)]
    recovery_seconds: Annotated[float, Field(alias="recoverySeconds", ge=0, le=86400)]
    dedup: Dedup

    @model_validator(mode="after")
    def validate_condition(self) -> "RuleAst":
        region_ids = {region.id for region in self.regions}
        _validate_condition(self.condition, region_ids)
        return self


class RuleTransition(BaseModel):
    state: Literal["DETECTED", "PENDING", "CONFIRMED", "ALARM", "COOLDOWN", "RECOVERED", "CLOSED"]
    event_type: str = Field(alias="eventType")
    severity: str
    occurred_at_millis: int = Field(alias="occurredAtMillis")
    track_id: str | None = Field(default=None, alias="trackId")
    dedup_key: str = Field(alias="dedupKey")
    activity_id: str = Field(alias="activityId")
    source_event_id: str = Field(alias="sourceEventId")
    object_snapshot: dict = Field(alias="objectSnapshot")
    rule_snapshot: dict = Field(alias="ruleSnapshot")


class RuleDryRunFrame(BaseModel):
    timestamp_millis: int = Field(alias="timestampMillis", ge=0)
    objects: list[dict]


class RuleDryRunRequest(BaseModel):
    task_id: int = Field(alias="taskId", gt=0)
    camera_id: int = Field(alias="cameraId", gt=0)
    ast: RuleAst
    frames: list[RuleDryRunFrame] = Field(min_length=1, max_length=300)


class RuleDryRunResponse(BaseModel):
    confirmed: bool
    transitions: list[RuleTransition]


def _validate_condition(node: dict, region_ids: set[str]) -> None:
    node_type = node.get("type")
    if node_type in {"AND", "OR"}:
        children = node.get("children")
        if not isinstance(children, list) or not children:
            raise ValueError("condition children are required")
        for child in children:
            if not isinstance(child, dict):
                raise ValueError("condition child must be an object")
            _validate_condition(child, region_ids)
    elif node_type == "NOT":
        child = node.get("child")
        if not isinstance(child, dict):
            raise ValueError("NOT child is required")
        _validate_condition(child, region_ids)
    elif node_type == "ROI_ENTER":
        if node.get("regionId") not in region_ids:
            raise ValueError("ROI_ENTER references an unknown region")
        if not isinstance(node.get("objectClasses"), list) or not node["objectClasses"]:
            raise ValueError("ROI_ENTER objectClasses are required")
    elif node_type == "N_OF_M":
        n, m = node.get("n"), node.get("m")
        if not isinstance(n, int) or not isinstance(m, int) or not 1 <= n <= m <= 300:
            raise ValueError("N_OF_M requires 1 <= n <= m <= 300")
    elif node_type == "DURATION":
        seconds = node.get("seconds")
        if not isinstance(seconds, (int, float)) or not 0 <= seconds <= 86400:
            raise ValueError("DURATION seconds are invalid")
    elif node_type == "COUNT":
        if not isinstance(node.get("min"), int) or node["min"] < 1:
            raise ValueError("COUNT min is invalid")
    elif node_type == "COUNT_BELOW":
        if not isinstance(node.get("min"), int) or node["min"] < 1:
            raise ValueError("COUNT_BELOW min is invalid")
        if node.get("regionId") not in region_ids:
            raise ValueError("COUNT_BELOW references an unknown region")
        if not isinstance(node.get("objectClasses"), list) or not node["objectClasses"]:
            raise ValueError("COUNT_BELOW objectClasses are required")
    elif node_type == "STATIONARY":
        movement = node.get("maxMovement")
        if not isinstance(movement, (int, float)) or not 0 < movement <= 1:
            raise ValueError("STATIONARY maxMovement is invalid")
    elif node_type == "LOITERING":
        path_length, seconds = node.get("minPathLength"), node.get("seconds")
        if not isinstance(path_length, (int, float)) or not 0 < path_length <= 1:
            raise ValueError("LOITERING minPathLength is invalid")
        if not isinstance(seconds, (int, float)) or not 1 <= seconds <= 86400:
            raise ValueError("LOITERING seconds is invalid")
    else:
        raise ValueError(f"unsupported condition type: {node_type}")


def _area(points: list[Point]) -> float:
    return (
        abs(
            sum(
                point.x * points[(index + 1) % len(points)].y
                - points[(index + 1) % len(points)].x * point.y
                for index, point in enumerate(points)
            )
        )
        / 2
    )


def _self_intersects(points: list[Point]) -> bool:
    size = len(points)
    for left in range(size):
        for right in range(left + 1, size):
            if right in {left, (left + 1) % size} or (right + 1) % size == left:
                continue
            if _intersects(
                points[left],
                points[(left + 1) % size],
                points[right],
                points[(right + 1) % size],
            ):
                return True
    return False


def _intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
    def cross(left: Point, right: Point, value: Point) -> float:
        return (right.x - left.x) * (value.y - left.y) - (right.y - left.y) * (value.x - left.x)

    return cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0
