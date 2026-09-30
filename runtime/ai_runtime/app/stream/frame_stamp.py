"""H.264 user-data SEI carrying a non-secret source clock through WebRTC."""

import hashlib
import re
import struct
from uuid import UUID

# Versioned application UUID. Payload: stream UUID (16 bytes), 90 kHz PTS (uint64).
STAMP_UUID = UUID("b60519ab-079c-4e19-9428-f40aef3c91ec").bytes


def stamp_h264(data: bytes, stream_id: str, source_pts: int, frame_key: str | None = None) -> bytes:
    if not 0 <= source_pts <= 2**53 - 1:
        raise ValueError("source PTS is outside the browser-safe integer range")
    payload = STAMP_UUID + UUID(stream_id).bytes + struct.pack(">Q", source_pts)
    if frame_key is not None:
        payload += bytes.fromhex(frame_key)
    rbsp = bytes([5, len(payload)]) + payload + b"\x80"
    escaped = bytearray()
    zeros = 0
    for value in rbsp:
        if zeros >= 2 and value <= 3:
            escaped.append(3)
            zeros = 0
        escaped.append(value)
        zeros = zeros + 1 if value == 0 else 0
    return b"\x00\x00\x00\x01\x06" + bytes(escaped) + data


def h264_frame_key(data: bytes) -> str | None:
    """Exact VCL content identity, independent of RTSP session PTS and SEI/SPS wrappers.

    Different substreams/encoders deliberately do not match. Never infer clock
    equivalence from host arrival time or from a similar-looking decoded image.
    """
    units = re.split(b"\x00\x00(?:\x00)?\x01", data)
    if len(units) == 1:
        units = []
        offset = 0
        while offset + 4 <= len(data):
            size = int.from_bytes(data[offset : offset + 4], "big")
            offset += 4
            if size <= 0 or offset + size > len(data):
                return None
            units.append(data[offset : offset + size])
            offset += size
        if offset != len(data):
            return None
    slices = [unit for unit in units if unit and (unit[0] & 31) in (1, 5)]
    if not slices:
        return None
    content = b"".join(len(unit).to_bytes(4, "big") + unit for unit in slices)
    return hashlib.sha256(content).hexdigest()[:32]
