from dataclasses import dataclass

from ai_runtime.app.model.contracts import BoundingBox, DetectionObject


@dataclass
class _Track:
    track_id: str
    bbox: BoundingBox
    missed: int = 0


class IoUTracker:
    """Small deterministic tracker used by the first area-intrusion vertical slice."""

    def __init__(self, minimum_iou: float = 0.2, maximum_missed_frames: int = 5) -> None:
        self.minimum_iou = minimum_iou
        self.maximum_missed_frames = maximum_missed_frames
        self._tracks: dict[str, _Track] = {}
        self._sequence = 0

    def update(self, objects: list[DetectionObject]) -> list[DetectionObject]:
        remaining = set(self._tracks)
        tracked: list[DetectionObject] = []
        for detected in sorted(objects, key=lambda item: item.confidence, reverse=True):
            candidate = max(
                (
                    (track_id, _iou(track.bbox, detected.bbox))
                    for track_id, track in self._tracks.items()
                    if track_id in remaining
                ),
                key=lambda item: item[1],
                default=("", 0.0),
            )
            if candidate[1] >= self.minimum_iou:
                track_id = candidate[0]
                remaining.remove(track_id)
                track = self._tracks[track_id]
                track.bbox = detected.bbox
                track.missed = 0
            else:
                self._sequence += 1
                track_id = f"track-{self._sequence}"
                self._tracks[track_id] = _Track(track_id, detected.bbox)
            tracked.append(detected.model_copy(update={"track_id": track_id}))
        for track_id in remaining:
            self._tracks[track_id].missed += 1
        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if track.missed <= self.maximum_missed_frames
        }
        return tracked


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
