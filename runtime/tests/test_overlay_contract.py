from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_runtime.app.stream.overlay import OverlayEnvelope


def valid_overlay() -> dict[str, object]:
    return {
        "type": "preview.overlay.frame",
        "version": "1.0",
        "messageId": "message-1",
        "occurredAt": datetime.now(UTC),
        "traceId": "trace-1",
        "data": {
            "sessionId": "session-1",
            "cameraId": 7,
            "frameId": "frame-42",
            "timestamp": datetime.now(UTC),
            "sourceWidth": 1920,
            "sourceHeight": 1080,
            "objects": [
                {
                    "trackId": "track-9",
                    "class": "person",
                    "confidence": 0.93,
                    "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                    "attributes": {"helmet": "unknown"},
                }
            ],
        },
    }


def test_overlay_contract_preserves_frame_and_normalized_coordinates() -> None:
    envelope = OverlayEnvelope.model_validate(valid_overlay())

    assert envelope.data.frame_id == "frame-42"
    assert envelope.data.objects[0].bbox.width == 0.3
    assert envelope.data.objects[0].track_id == "track-9"


def test_overlay_rejects_bbox_outside_normalized_frame() -> None:
    payload = valid_overlay()
    payload["data"]["objects"][0]["bbox"] = {  # type: ignore[index]
        "x": 0.9,
        "y": 0.2,
        "width": 0.2,
        "height": 0.4,
    }

    with pytest.raises(ValidationError):
        OverlayEnvelope.model_validate(payload)
