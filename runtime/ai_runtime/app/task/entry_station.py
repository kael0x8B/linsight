"""Lease-bound entrance presence detection; identity extraction stays in finite ENTRY_FACE scans."""

import asyncio
import io
import logging
import time
import traceback
from typing import Literal
from uuid import uuid4

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.contracts import BoundingBox, DetectionObject
from ai_runtime.app.rule.face_zone import FaceZoneTrigger


class EntryStationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: int = Field(alias="entryId", gt=0)
    version: int = Field(gt=0)
    camera_id: int = Field(alias="cameraId", gt=0)
    model_version_id: int = Field(alias="modelVersionId", gt=0)
    source_url: SecretStr = Field(alias="sourceUrl")
    roi: BoundingBox
    trigger_mode: Literal["FACE_ZONE"] = Field(alias="triggerMode")

    @model_validator(mode="after")
    def valid_zone(self):
        r = self.roi
        if (
            r.width <= 0
            or r.height <= 0
            or r.width * r.height > 0.5
            or r.x + r.width > 1
            or r.y + r.height > 1
        ):
            raise ValueError("a dedicated entrance ROI covering at most half the image is required")
        return self


class StationSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stations: list[EntryStationConfig] = Field(max_length=2)

    @model_validator(mode="after")
    def unique(self):
        if len({x.entry_id for x in self.stations}) != len(self.stations) or len(
            {x.camera_id for x in self.stations}
        ) != len(self.stations):
            raise ValueError("duplicate entrance or camera")
        return self


class StationAck(BaseModel):
    entry_id: int = Field(alias="entryId", gt=0)
    encounter_id: str = Field(alias="encounterId", pattern=r"^[0-9a-f-]{36}$")
    completed: bool = False


def is_positioned(face, width: int, height: int) -> bool:
    x1, y1, x2, y2 = face.box
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height or min(x2 - x1, y2 - y1) < 64:
        return False
    points = np.asarray(face.landmarks)
    eye_span = float(abs(points[1, 0] - points[0, 0]))
    if eye_span < 10:
        return False
    # Facing the marked scan position, not merely passing through its background.
    return (
        abs(float(points[0, 1] - points[1, 1])) / eye_span < 0.25
        and abs(float(points[2, 0] - (points[0, 0] + points[1, 0]) / 2)) / eye_span < 0.3
    )


class EntryStationManager:
    def __init__(self, tasks, pool):
        self.tasks, self.pool = tasks, pool
        self.entries = {}

    async def sync(self, request: StationSyncRequest):
        desired = {x.entry_id: x for x in request.stations}
        for key, row in list(self.entries.items()):
            if key not in desired or row["config"] != desired[key] or row["job"].done():
                row["job"].cancel()
                await asyncio.gather(row["job"], return_exceptions=True)
                self.entries.pop(key)
        for key, config in desired.items():
            if key not in self.entries:
                row = {
                    "config": config,
                    "gate": FaceZoneTrigger(),
                    "lease": time.monotonic() + 15,
                    "error": None,
                    "observed": 0,
                    "tracker": IoUTracker(maximum_missed_frames=1),
                    "runId": str(uuid4()),
                    "frame": None,
                }
                self.entries[key] = row
                row["job"] = asyncio.create_task(self._run(row))
            self.entries[key]["lease"] = time.monotonic() + 15
        return self.snapshot()

    def snapshot(self):
        return [
            {
                "entryId": key,
                "version": row["config"].version,
                "state": row["error"] or row["gate"].state,
                "encounterId": row["gate"].encounter_id,
                "observedAtMillis": row["gate"].triggered_at or row["observed"],
                "frame": row.get("frame"),
            }
            for key, row in self.entries.items()
        ]

    def acknowledge(self, request: StationAck):
        row = self.entries.get(request.entry_id)
        if row:
            row["gate"].acknowledge(request.encounter_id, request.completed)

    async def close(self):
        for row in self.entries.values():
            row["job"].cancel()
        await asyncio.gather(*(row["job"] for row in self.entries.values()), return_exceptions=True)
        self.entries.clear()

    async def _run(self, row):
        config, gate = row["config"], row["gate"]
        while time.monotonic() < row["lease"]:
            try:
                async with self.tasks.camera_samples(config.camera_id, config.source_url) as queue:
                    last = 0
                    while time.monotonic() < row["lease"]:
                        try:
                            frame = await asyncio.wait_for(queue.get(), 2)
                        except TimeoutError:
                            row["error"] = "NO_FRESH_FRAME"
                            gate.finish()
                            continue
                        now = time.time_ns() // 1_000_000
                        if not 0 <= now - frame.timestamp_millis <= 2000:
                            row["error"] = "NO_FRESH_FRAME"
                            gate.finish()
                            continue
                        if frame.timestamp_millis - last < 400:
                            continue
                        last = frame.timestamp_millis
                        with Image.open(io.BytesIO(frame.data)) as image:
                            r = config.roi
                            crop = image.crop(
                                (
                                    round(r.x * image.width),
                                    round(r.y * image.height),
                                    round((r.x + r.width) * image.width),
                                    round((r.y + r.height) * image.height),
                                )
                            )
                            faces = await self.pool.locate_faces(config.model_version_id, crop)
                            ready = len(faces) == 1 and is_positioned(
                                faces[0], crop.width, crop.height
                            )
                        objects = []
                        for face in faces[:16]:
                            x1, y1, x2, y2 = face.box
                            ox, oy = round(r.x * image.width), round(r.y * image.height)
                            x1 = max(0, min(image.width, ox + x1))
                            x2 = max(0, min(image.width, ox + x2))
                            y1 = max(0, min(image.height, oy + y1))
                            y2 = max(0, min(image.height, oy + y2))
                            if x2 > x1 and y2 > y1:
                                objects.append(
                                    DetectionObject(
                                        **{
                                            "class": "face",
                                            "confidence": float(face.score),
                                            "bbox": {
                                                "x": x1 / image.width,
                                                "y": y1 / image.height,
                                                "width": (x2 - x1) / image.width,
                                                "height": (y2 - y1) / image.height,
                                            },
                                        }
                                    )
                                )
                        tracked = row["tracker"].update(objects)
                        row["frame"] = {
                            "frameId": f"{row['runId']}:{frame.timestamp_millis}",
                            "runId": row["runId"],
                            "cameraId": config.camera_id,
                            "timestamp": frame.timestamp_millis,
                            "sourceWidth": image.width,
                            "sourceHeight": image.height,
                            "streamId": frame.stream_id,
                            "sourcePts": frame.source_pts,
                            "frameKey": frame.frame_key,
                            "faces": [
                                {
                                    **o.bbox.model_dump(),
                                    "confidence": o.confidence,
                                    "trackId": o.track_id,
                                }
                                for o in tracked
                            ],
                        }
                        row["observed"] = now
                        row["error"] = (
                            "MULTIPLE_FACES"
                            if len(faces) > 1 and gate.state not in {"TRIGGERED", "SCANNING"}
                            else None
                        )
                        gate.observe(now, bool(faces), ready)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if row.get("errorType") != type(error).__name__:
                    logging.getLogger("linsight.entry_station").warning(
                        "Entrance analysis failed entryId=%s errorType=%s",
                        config.entry_id,
                        type(error).__name__,
                    )
                    logging.getLogger("linsight.entry_station").warning(
                        "Entrance failure locations=%s",
                        [
                            (PathName.filename.rsplit("/", 1)[-1], PathName.lineno)
                            for PathName in traceback.extract_tb(error.__traceback__)
                        ],
                    )
                row["errorType"] = type(error).__name__
                row["error"] = "STATION_UNAVAILABLE"
                gate.finish()
                await asyncio.sleep(2)
        row["error"] = "OFFLINE"
