import asyncio
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from ai_runtime.app.event.evidence import EvidenceBuffer
from ai_runtime.app.event.store import OfflineEventStore, PendingEvent
from ai_runtime.app.rule.contracts import RuleTransition
from ai_runtime.app.task.contracts import TaskStartRequest


def task_request() -> TaskStartRequest:
    return TaskStartRequest.model_validate(
        {
            "taskId": 8,
            "runId": "22222222-2222-2222-2222-222222222222",
            "configVersion": 1,
            "cameraId": 9,
            "sourceUrl": "rtsp://camera.invalid/live",
            "algorithmId": 10,
            "pipelineVersionId": 11,
            "pipeline": {"schemaVersion": "1.0", "nodes": [], "edges": []},
            "displayNames": {
                "task": "东门区域入侵",
                "camera": "东门摄像头",
                "algorithm": "区域入侵",
            },
            "modelVersionId": 12,
            "modelBindings": {"person-detector": 12, "face-recognizer": 15},
            "ruleId": 13,
            "ruleVersionId": 14,
            "rule": {
                "schemaVersion": "1.0",
                "eventType": "AREA_INTRUSION",
                "severity": "MAJOR",
                "regions": [
                    {
                        "id": "main",
                        "name": "主区域",
                        "type": "POLYGON",
                        "sourceWidth": 1920,
                        "sourceHeight": 1080,
                        "pointMode": "FOOT",
                        "overlapThreshold": 0,
                        "points": [
                            {"x": 0.1, "y": 0.1},
                            {"x": 0.9, "y": 0.1},
                            {"x": 0.9, "y": 0.9},
                            {"x": 0.1, "y": 0.9},
                        ],
                    }
                ],
                "schedule": {
                    "timezone": "Asia/Shanghai",
                    "weekly": [{"days": [1, 2, 3, 4, 5, 6, 7], "start": "00:00", "end": "23:59"}],
                },
                "condition": {
                    "type": "AND",
                    "children": [
                        {"type": "ROI_ENTER", "regionId": "main", "objectClasses": ["person"]},
                        {"type": "DURATION", "seconds": 2},
                    ],
                },
                "cooldownSeconds": 30,
                "recoverySeconds": 5,
                "dedup": {"scope": "TRACK", "windowSeconds": 30},
            },
            "parameters": {"schemaVersion": "1.0", "sampleFps": 1},
        }
    )


def transition() -> RuleTransition:
    return RuleTransition.model_validate(
        {
            "state": "ALARM",
            "eventType": "AREA_INTRUSION",
            "severity": "MAJOR",
            "occurredAtMillis": 2_000,
            "trackId": "track-1",
            "dedupKey": "9:8:AREA_INTRUSION:track-1",
            "activityId": "11111111-1111-1111-1111-111111111111",
            "sourceEventId": "11111111-1111-1111-1111-111111111111",
            "objectSnapshot": {
                "class": "person",
                "confidence": 0.92,
                "bbox": {"x": 0.4, "y": 0.3, "width": 0.1, "height": 0.2},
            },
            "ruleSnapshot": task_request().rule.model_dump(by_alias=True),
        }
    )


def jpeg() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), "#334155").save(stream, "JPEG")
    return stream.getvalue()


def test_offline_store_persists_and_acknowledges_deliveries(tmp_path: Path) -> None:
    store = OfflineEventStore(tmp_path / "events.sqlite3")
    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(jpeg())
    store.upsert_event(
        PendingEvent.model_validate(
            {
                "sourceEventId": "source-1",
                "payload": {"eventType": "AREA_INTRUSION"},
                "snapshotPath": snapshot,
                "finalized": False,
            }
        )
    )
    store.enqueue_transition({"sourceEventId": "source-1", "state": "CLOSED", "occurredTime": 3000})

    assert store.list_events()[0].payload["eventType"] == "AREA_INTRUSION"
    delivery_key = store.list_transitions()[0].delivery_key
    store.acknowledge_transition(delivery_key)
    store.finalize_event("source-1", None, None)
    store.acknowledge_event("source-1")
    assert store.list_events() == []
    assert store.list_transitions() == []
    store.close()


def test_offline_store_persists_backoff_and_does_not_block_later_items(
    tmp_path: Path,
) -> None:
    database = tmp_path / "events.sqlite3"
    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(jpeg())
    store = OfflineEventStore(database)
    for source_id in ("poison", "healthy"):
        store.upsert_event(
            PendingEvent.model_validate(
                {
                    "sourceEventId": source_id,
                    "payload": {"sourceEventId": source_id},
                    "snapshotPath": snapshot,
                    "finalized": True,
                }
            )
        )
    store.defer_event("poison", now_millis=1_000)
    assert [event.source_event_id for event in store.list_events(now_millis=1_500)] == ["healthy"]
    store.close()

    reopened = OfflineEventStore(database)
    retry = reopened.list_events(now_millis=2_000)
    assert {event.source_event_id for event in retry} == {"poison", "healthy"}
    poison = next(event for event in retry if event.source_event_id == "poison")
    assert poison.delivery_attempts == 1
    reopened.close()


def test_offline_store_exponential_retry_is_capped(tmp_path: Path) -> None:
    store = OfflineEventStore(tmp_path / "events.sqlite3")
    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(jpeg())
    store.upsert_event(
        PendingEvent.model_validate(
            {
                "sourceEventId": "source-1",
                "payload": {},
                "snapshotPath": snapshot,
                "finalized": True,
            }
        )
    )
    now = 0
    for _ in range(12):
        store.defer_event("source-1", now_millis=now)
        now += 300_000
    event = store.list_events(now_millis=now)[0]
    assert event.delivery_attempts == 12
    store.close()


def test_offline_store_stats_cover_deferred_items_and_media_integrity(tmp_path: Path) -> None:
    store = OfflineEventStore(tmp_path / "events.sqlite3")
    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(jpeg())
    missing_video = tmp_path / "missing.mp4"
    store.upsert_event(
        PendingEvent.model_validate(
            {
                "sourceEventId": "source-1",
                "payload": {},
                "snapshotPath": snapshot,
                "videoPath": missing_video,
                "finalized": False,
                "captureError": "ENCODE_FAILED",
            }
        )
    )
    store.enqueue_transition({"sourceEventId": "source-1", "state": "CLOSED"})
    store.defer_event("source-1", now_millis=1_000)
    store.defer_transition("source-1:CLOSED", now_millis=1_000)

    assert store.stats(now_millis=1_500) == {
        "pendingEvents": 1,
        "pendingTransitions": 1,
        "deadLetterTransitions": 0,
        "retryingEvents": 1,
        "retryingTransitions": 1,
        "maxDeliveryAttempts": 1,
        "totalRetryCount": 2,
        "oldestEventAgeSeconds": 0,
        "evidenceBacklogBytes": snapshot.stat().st_size,
        "missingMediaFiles": 1,
        "captureErrors": 1,
        "unfinalizedEvents": 1,
    }
    store.close()


def test_transition_dead_letter_preserves_payload_and_rejects_pending_source(
    tmp_path: Path,
) -> None:
    database = tmp_path / "events.sqlite3"
    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(jpeg())
    store = OfflineEventStore(database)
    store.upsert_event(
        PendingEvent.model_validate(
            {
                "sourceEventId": "source-1",
                "payload": {"sourceEventId": "source-1"},
                "snapshotPath": snapshot,
                "finalized": True,
            }
        )
    )
    payload = {"sourceEventId": "source-1", "state": "CLOSED", "occurredTime": 3_000}
    store.enqueue_transition(payload)

    with pytest.raises(ValueError, match="still pending"):
        store.dead_letter_transition("source-1:CLOSED", "CONTROL_PLANE_EVENT_NOT_FOUND")

    store.acknowledge_event("source-1")
    store.dead_letter_transition(
        "source-1:CLOSED", "CONTROL_PLANE_EVENT_NOT_FOUND", now_millis=4_000
    )
    assert store.list_transitions(now_millis=4_000) == []
    assert store.stats(now_millis=4_000)["deadLetterTransitions"] == 1
    row = store._connection.execute(
        "SELECT payload, reason, dead_lettered_at_millis FROM dead_letter_transition"
    ).fetchone()
    assert row is not None
    assert row["payload"] == (
        '{"sourceEventId": "source-1", "state": "CLOSED", "occurredTime": 3000}'
    )
    assert row["reason"] == "CONTROL_PLANE_EVENT_NOT_FOUND"
    assert row["dead_lettered_at_millis"] == 4_000
    store.close()


def test_thirty_minute_outage_replays_events_and_transitions_exactly_once(
    tmp_path: Path,
) -> None:
    database = tmp_path / "thirty-minute-outage.sqlite3"
    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(jpeg())
    interval_millis = 10_000
    outage_millis = 30 * 60 * 1_000
    expected_ids = {
        f"source-{occurred_millis // interval_millis:03d}"
        for occurred_millis in range(0, outage_millis, interval_millis)
    }

    store = OfflineEventStore(database)
    for occurred_millis in range(0, outage_millis, interval_millis):
        source_id = f"source-{occurred_millis // interval_millis:03d}"
        store.upsert_event(
            PendingEvent.model_validate(
                {
                    "sourceEventId": source_id,
                    "payload": {
                        "sourceEventId": source_id,
                        "occurredAtMillis": occurred_millis,
                    },
                    "snapshotPath": snapshot,
                    "finalized": True,
                }
            )
        )
        store.enqueue_transition(
            {
                "sourceEventId": source_id,
                "state": "CLOSED",
                "occurredTime": occurred_millis + 5_000,
            }
        )
        store.defer_event(source_id, now_millis=occurred_millis)
        store.defer_transition(f"{source_id}:CLOSED", now_millis=occurred_millis)
        if occurred_millis == outage_millis // 2:
            store.close()
            store = OfflineEventStore(database)

    reconnect_millis = outage_millis + 300_000
    pending_events = store.list_events(limit=1_000, now_millis=reconnect_millis)
    pending_transitions = store.list_transitions(limit=1_000, now_millis=reconnect_millis)
    assert {event.source_event_id for event in pending_events} == expected_ids
    transition_source_ids = {
        transition.payload["sourceEventId"] for transition in pending_transitions
    }
    assert transition_source_ids == expected_ids
    assert all(event.delivery_attempts == 1 for event in pending_events)
    assert all(transition.delivery_attempts == 1 for transition in pending_transitions)

    delivered_events: set[str] = set()
    delivered_transitions: set[str] = set()
    for event in pending_events:
        assert event.source_event_id not in delivered_events
        delivered_events.add(event.source_event_id)
        store.acknowledge_event(event.source_event_id)
    for transition in pending_transitions:
        assert transition.delivery_key not in delivered_transitions
        delivered_transitions.add(transition.delivery_key)
        store.acknowledge_transition(transition.delivery_key)

    assert delivered_events == expected_ids
    assert len(delivered_transitions) == len(expected_ids)
    assert store.list_events(limit=1_000, now_millis=reconnect_millis) == []
    assert store.list_transitions(limit=1_000, now_millis=reconnect_millis) == []
    store.close()

    reopened = OfflineEventStore(database)
    assert reopened.list_events(limit=1_000, now_millis=reconnect_millis) == []
    assert reopened.list_transitions(limit=1_000, now_millis=reconnect_millis) == []
    reopened.close()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_evidence_buffer_writes_snapshot_and_playable_mp4(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = OfflineEventStore(tmp_path / "delivery.sqlite3")
        buffer = EvidenceBuffer(
            request=task_request(),
            store=store,
            root=tmp_path,
            ffmpeg_binary="ffmpeg",
            pre_seconds=10,
            post_seconds=0,
            fps=5,
        )
        await buffer.observe_frame(jpeg(), 1_900)
        await buffer.observe_frame(jpeg(), 2_000)
        await buffer.start(transition())
        await buffer.close()

        pending = store.list_events()[0]
        assert pending.finalized is True
        assert pending.snapshot_path.stat().st_size > 0
        assert pending.video_path is not None
        assert pending.video_path.stat().st_size > 0
        assert pending.payload["durationMs"] == 2_000
        assert pending.payload["taskSnapshot"]["modelBindings"] == {
            "person-detector": 12,
            "face-recognizer": 15,
        }
        assert pending.payload["taskSnapshot"]["displayNames"]["task"] == "东门区域入侵"
        assert pending.payload["modelSnapshot"]["modelBindings"]["face-recognizer"] == 15
        store.close()

    asyncio.run(scenario())


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)
def test_slow_irregular_inference_preserves_evidence_wall_clock_duration(tmp_path: Path) -> None:
    """A 30-second field window must not become a two-second fast-forward clip."""

    async def scenario() -> Path:
        store = OfflineEventStore(tmp_path / "delivery.sqlite3")
        buffer = EvidenceBuffer(
            request=task_request(),
            store=store,
            root=tmp_path,
            ffmpeg_binary="ffmpeg",
            pre_seconds=10,
            post_seconds=20,
            fps=5,
        )
        before = [0, 2_400, 4_900, 7_600, 10_200]
        after = [12_700, 15_400, 18_200, 21_500, 24_600, 27_700, 30_300]
        for timestamp in before:
            await buffer.observe_frame(jpeg(), timestamp)
        await buffer.start(transition().model_copy(update={"occurred_at_millis": 10_200}))
        for timestamp in after:
            await buffer.observe_frame(jpeg(), timestamp)
        await buffer.close()
        pending = store.list_events()[0]
        assert pending.finalized and pending.capture_error is None
        assert pending.video_path is not None
        store.close()
        return pending.video_path

    video = asyncio.run(scenario())
    ffprobe = shutil.which("ffprobe")
    assert ffprobe is not None
    probe = subprocess.run(  # noqa: S603 - resolved binary and locally generated test video
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    assert duration == pytest.approx(30.3 + 1 / 5, abs=0.2)


def test_video_encoding_does_not_hold_up_new_analysis_frames(tmp_path: Path, monkeypatch) -> None:
    import threading

    started = threading.Event()
    release = threading.Event()

    def slow_encode(self, capture):
        started.set()
        assert release.wait(5)
        self.store.finalize_event(capture.transition.source_event_id, None, None)

    monkeypatch.setattr(EvidenceBuffer, "_finalize", slow_encode)

    async def scenario():
        store = OfflineEventStore(tmp_path / "delivery.sqlite3")
        buffer = EvidenceBuffer(task_request(), store, tmp_path, "ffmpeg", 10, 1, 5)
        await buffer.observe_frame(jpeg(), 2000)
        await buffer.start(transition())
        try:
            await asyncio.wait_for(buffer.observe_frame(jpeg(), 3100), 0.5)
            assert await asyncio.to_thread(started.wait, 2)
            await asyncio.wait_for(buffer.observe_frame(jpeg(), 3200), 0.5)
            assert buffer._ring[-1][0] == 3200
            assert not store.list_events()[0].finalized
        finally:
            release.set()
            await buffer.close()
        assert store.list_events()[0].finalized
        store.close()

    asyncio.run(scenario())


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_same_millisecond_frames_do_not_discard_the_alarm_video(tmp_path: Path) -> None:
    async def scenario():
        store = OfflineEventStore(tmp_path / "delivery.sqlite3")
        buffer = EvidenceBuffer(task_request(), store, tmp_path, "ffmpeg", 10, 1, 5)
        for timestamp in (1000, 1000, 1500, 2000):
            await buffer.observe_frame(jpeg(), timestamp)
        await buffer.start(transition())
        for timestamp in (2200, 2200, 2500, 3100):
            await buffer.observe_frame(jpeg(), timestamp)
        await buffer.close()
        pending = store.list_events()[0]
        assert pending.finalized and pending.capture_error is None
        assert pending.video_path is not None and pending.video_path.stat().st_size > 0
        store.close()

    asyncio.run(scenario())
