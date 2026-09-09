from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class CapturedFrame:
    data: bytes
    timestamp_millis: int
    stream_id: str | None = None
    source_pts: int | None = None
    decode_millis: float | None = None
    image: Image.Image | None = None
    frame_key: str | None = None
