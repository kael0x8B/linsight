import math
import re
from dataclasses import dataclass

from ai_runtime.app.model.contracts import BoundingBox, DetectionObject


@dataclass
class _Track:
    track_id: str
    bbox: BoundingBox
    class_name: str
    missed: int = 0
    timestamp: int | None = None
    velocity: tuple[float, float] = (0, 0)
    text: str = ""
    plate_crop_width: int = 0


class IoUTracker:
    """Small deterministic tracker used by the first area-intrusion vertical slice."""

    def __init__(
        self,
        minimum_iou: float = 0.2,
        maximum_missed_frames: int = 5,
        motion_classes: frozenset[str] = frozenset(),
        stationary_reacquire_millis: int = 1500,
    ) -> None:
        self.minimum_iou = minimum_iou
        self.maximum_missed_frames = maximum_missed_frames
        self._tracks: dict[str, _Track] = {}
        self._sequence = 0
        self.motion_classes = motion_classes
        self.stationary_reacquire_millis = max(1500, stationary_reacquire_millis)

    def reset(self) -> None:
        self._tracks.clear()

    def update(
        self, objects: list[DetectionObject], timestamp: int | None = None
    ) -> list[DetectionObject]:
        # Motion identity cannot survive a stream outage or a clock discontinuity.
        self._tracks = {
            key: track
            for key, track in self._tracks.items()
            if track.class_name not in self.motion_classes
            or timestamp is None
            or track.timestamp is None
            or 0 <= timestamp - track.timestamp <= self.stationary_reacquire_millis
        }
        remaining = set(self._tracks)
        tracked: list[DetectionObject] = []
        ordered = sorted(objects, key=lambda item: item.confidence, reverse=True)
        for detected in ordered:
            candidate = max(
                (
                    (track_id, _iou(track.bbox, detected.bbox))
                    for track_id, track in self._tracks.items()
                    if track_id in remaining
                    and track.class_name == detected.class_name
                    and (
                        detected.class_name not in self.motion_classes
                        or _compatible(track.text, _text(detected))
                    )
                    and (
                        detected.class_name not in self.motion_classes
                        or timestamp is None
                        or track.timestamp is None
                        or timestamp - track.timestamp <= 1500
                        or (
                            timestamp - track.timestamp <= self.stationary_reacquire_millis
                            and track.text
                            and track.text == _text(detected)
                            and track.plate_crop_width >= 400
                            and _plate_crop_width(detected) >= 400
                            and _iou(track.bbox, detected.bbox) >= 0.5
                        )
                    )
                ),
                key=lambda item: item[1],
                default=("", 0.0),
            )
            track_id = candidate[0] if candidate[1] >= self.minimum_iou else ""
            if (
                not track_id
                and detected.class_name in self.motion_classes
                and timestamp is not None
            ):
                scores = sorted(
                    (
                        (_motion_cost(track, detected, timestamp), key)
                        for key, track in self._tracks.items()
                        if key in remaining
                    ),
                    key=lambda item: item[0],
                )
                if scores and math.isfinite(scores[0][0]):
                    cost, key = scores[0]
                    # Ambiguous crossings start a new confirmation instead of
                    # merging two plates' votes. Require a mutual nearest match.
                    rival = min(
                        (
                            _motion_cost(self._tracks[key], other, timestamp)
                            for other in ordered
                            if other is not detected
                        ),
                        default=math.inf,
                    )
                    alternate = scores[1][0] if len(scores) > 1 else math.inf
                    if cost + 0.25 < min(rival, alternate):
                        track_id = key
            if track_id:
                remaining.remove(track_id)
                track = self._tracks[track_id]
                if (
                    timestamp is not None
                    and track.timestamp is not None
                    and timestamp > track.timestamp
                ):
                    seconds = (timestamp - track.timestamp) / 1000
                    track.velocity = tuple(
                        (new - old) / seconds
                        for new, old in zip(
                            _center(detected.bbox), _center(track.bbox), strict=True
                        )
                    )
                track.bbox = detected.bbox
                track.missed = 0
                track.timestamp = timestamp
                track.text = _text(detected) or track.text
                track.plate_crop_width = _plate_crop_width(detected)
            else:
                self._sequence += 1
                track_id = f"track-{self._sequence}"
                self._tracks[track_id] = _Track(
                    track_id,
                    detected.bbox,
                    detected.class_name,
                    timestamp=timestamp,
                    text=_text(detected),
                    plate_crop_width=_plate_crop_width(detected),
                )
            tracked.append(detected.model_copy(update={"track_id": track_id}))
        for track_id in remaining:
            self._tracks[track_id].missed += 1
        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if track.missed <= self.maximum_missed_frames
        }
        return tracked


def _center(box: BoundingBox) -> tuple[float, float]:
    return box.x + box.width / 2, box.y + box.height / 2


def _text(detected: DetectionObject) -> str:
    text = detected.attributes.get("plateText", "")
    confidence = detected.attributes.get(
        "ocrMinCharConfidence", detected.attributes.get("ocrConfidence", 0)
    )
    if (
        not isinstance(text, str)
        or not isinstance(confidence, (int, float))
        or not 0.75 <= confidence <= 1
    ):
        return ""
    normalized = re.sub(r"[\s·•._-]+", "", text).upper()
    # Partial glyphs must not break a valid geometric track during occlusion.
    return normalized if len(normalized) in {7, 8} else ""


def _plate_crop_width(detected: DetectionObject) -> int:
    value = detected.attributes.get("plateCropWidth")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _compatible(left: str, right: str) -> bool:
    # OCR may insert/drop one glyph without the physical plate changing.
    # Keep the geometric association; confirmation still uses exact strings.
    if not left or not right:
        return True
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) <= 1
    if abs(len(left) - len(right)) != 1:
        return False
    shorter, longer = sorted((left, right), key=len)
    return any(longer[:index] + longer[index + 1 :] == shorter for index in range(len(longer)))


def _motion_cost(track: _Track, detected: DetectionObject, timestamp: int) -> float:
    if track.class_name != detected.class_name or track.timestamp is None:
        return math.inf
    seconds = (timestamp - track.timestamp) / 1000
    if not 0 < seconds <= 1.5 or not _compatible(track.text, _text(detected)):
        return math.inf
    a, b = track.bbox, detected.bbox
    if min(a.width, a.height, b.width, b.height) <= 0 or not (
        0.5 <= a.width / b.width <= 2 and 0.5 <= a.height / b.height <= 2
    ):
        return math.inf
    x, y = _center(a)
    dx, dy = _center(b)
    error_x = abs(dx - x - track.velocity[0] * seconds) / max(a.width, b.width)
    error_y = abs(dy - y - track.velocity[1] * seconds) / max(a.height, b.height)
    identity = len(track.text) >= 7 and len(_text(detected)) >= 7
    limit = 2.5 if identity else 0.8
    if error_x > limit or error_y > min(limit, 1.5):
        return math.inf
    return math.hypot(error_x, error_y)


def _iou(left: BoundingBox, right: BoundingBox) -> float:
    intersection = max(
        0.0,
        min(left.x + left.width, right.x + right.width) - max(left.x, right.x),
    ) * max(
        0.0,
        min(left.y + left.height, right.y + right.height) - max(left.y, right.y),
    )
    union = left.width * left.height + right.width * right.height - intersection
    return 0.0 if union <= 0 else intersection / union
