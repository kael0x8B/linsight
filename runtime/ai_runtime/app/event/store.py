import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, Field


class PendingEvent(BaseModel):
    source_event_id: str = Field(alias="sourceEventId")
    payload: dict
    snapshot_path: Path = Field(alias="snapshotPath")
    video_path: Path | None = Field(default=None, alias="videoPath")
    finalized: bool
    capture_error: str | None = Field(default=None, alias="captureError")
    delivery_attempts: int = Field(default=0, alias="deliveryAttempts", ge=0)


class PendingTransition(BaseModel):
    delivery_key: str = Field(alias="deliveryKey")
    payload: dict
    delivery_attempts: int = Field(default=0, alias="deliveryAttempts", ge=0)


class PendingDeliveryBatch(BaseModel):
    events: list[PendingEvent]
    transitions: list[PendingTransition]


class OfflineEventStore:
    def __init__(self, path: Path, retain_history: bool = False) -> None:
        self._retain_history = retain_history
        self.local_task_ids: set[int] = set()
        self.on_event_created = None
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._media_root = path.parent.resolve()
        with self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_event (
                    source_event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    snapshot_path TEXT NOT NULL,
                    video_path TEXT,
                    finalized INTEGER NOT NULL DEFAULT 0,
                    capture_error TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_transition (
                    delivery_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letter_transition (
                    delivery_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    delivery_attempts INTEGER NOT NULL,
                    dead_lettered_at_millis INTEGER NOT NULL
                )
                """
            )
            self._ensure_delivery_columns("pending_event")
            self._ensure_delivery_columns("pending_transition")
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS delivered_media_cleanup ("
                "path TEXT PRIMARY KEY, source_event_id TEXT NOT NULL)"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS local_event_history ("
                "source_event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                "snapshot_path TEXT NOT NULL, video_path TEXT, finalized INTEGER NOT NULL, "
                "capture_error TEXT, stored_at INTEGER NOT NULL, "
                "delivered INTEGER NOT NULL DEFAULT 0)"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS event_media_pin ("
                "owner TEXT PRIMARY KEY, source_event_id TEXT NOT NULL)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_event_media_pin_source "
                "ON event_media_pin(source_event_id)"
            )
        self.cleanup_delivered_media()

    @contextmanager
    def transaction(self):
        """Share the event transaction with durable local delivery consumers."""
        with self._lock, self._connection:
            yield self._connection

    def _ensure_delivery_columns(self, table: str) -> None:
        columns = {
            row["name"]
            for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "delivery_attempts" not in columns:
            self._connection.execute(
                f"ALTER TABLE {table} ADD COLUMN delivery_attempts INTEGER NOT NULL DEFAULT 0"
            )
        if "next_attempt_at_millis" not in columns:
            self._connection.execute(
                f"ALTER TABLE {table} ADD COLUMN next_attempt_at_millis INTEGER NOT NULL DEFAULT 0"
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def upsert_event(self, value: PendingEvent) -> None:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT 1 FROM local_event_history WHERE source_event_id=? "
                "UNION ALL SELECT 1 FROM pending_event WHERE source_event_id=? LIMIT 1",
                (value.source_event_id, value.source_event_id),
            ).fetchone()
            if existing is None and self.on_event_created is not None:
                self.on_event_created(self._connection, value)
            self._connection.execute(
                """
                INSERT INTO pending_event
                    (source_event_id, payload, snapshot_path, video_path, finalized, capture_error)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_event_id) DO UPDATE SET
                    payload=excluded.payload,
                    snapshot_path=excluded.snapshot_path,
                    video_path=excluded.video_path,
                    finalized=excluded.finalized,
                    capture_error=excluded.capture_error
                """,
                (
                    value.source_event_id,
                    json.dumps(value.payload, ensure_ascii=False),
                    str(value.snapshot_path),
                    None if value.video_path is None else str(value.video_path),
                    int(value.finalized),
                    value.capture_error,
                ),
            )

            if self._retain_history:
                self._connection.execute(
                    "INSERT INTO local_event_history VALUES (?, ?, ?, ?, ?, ?, ?, 0) "
                    "ON CONFLICT(source_event_id) DO UPDATE SET payload=excluded.payload, "
                    "snapshot_path=excluded.snapshot_path, video_path=excluded.video_path, "
                    "finalized=excluded.finalized, capture_error=excluded.capture_error",
                    (
                        value.source_event_id,
                        json.dumps(value.payload, ensure_ascii=False),
                        str(value.snapshot_path),
                        None if value.video_path is None else str(value.video_path),
                        int(value.finalized),
                        value.capture_error,
                        _now_millis(),
                    ),
                )

            if value.payload.get("taskId") in self.local_task_ids:
                self._connection.execute(
                    "UPDATE local_event_history SET delivered=2 WHERE source_event_id=?",
                    (value.source_event_id,),
                )
                self._connection.execute(
                    "DELETE FROM pending_event WHERE source_event_id=?", (value.source_event_id,)
                )

    def finalize_event(
        self, source_event_id: str, video_path: Path | None, capture_error: str | None
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE pending_event SET video_path = ?, finalized = 1, capture_error = ?
                WHERE source_event_id = ?
                """,
                (None if video_path is None else str(video_path), capture_error, source_event_id),
            )

            if self._retain_history:
                self._connection.execute(
                    "UPDATE local_event_history SET video_path=?, finalized=1, capture_error=? "
                    "WHERE source_event_id=?",
                    (
                        None if video_path is None else str(video_path),
                        capture_error,
                        source_event_id,
                    ),
                )

    def list_events(self, limit: int = 100, now_millis: int | None = None) -> list[PendingEvent]:
        self.cleanup_delivered_media()
        due = _now_millis() if now_millis is None else now_millis
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM pending_event WHERE next_attempt_at_millis <= ? "
                "ORDER BY next_attempt_at_millis, rowid LIMIT ?",
                (due, limit),
            ).fetchall()
        return [
            PendingEvent.model_validate(
                {
                    "sourceEventId": row["source_event_id"],
                    "payload": json.loads(row["payload"]),
                    "snapshotPath": row["snapshot_path"],
                    "videoPath": row["video_path"],
                    "finalized": bool(row["finalized"]),
                    "captureError": row["capture_error"],
                    "deliveryAttempts": row["delivery_attempts"],
                }
            )
            for row in rows
        ]

    def acknowledge_event(self, source_event_id: str) -> None:
        # The Agent calls this only after the control plane has stored every
        # available media object. Persist cleanup intent together with the ACK,
        # so a crash or temporary filesystem error cannot leave permanent copies.
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT snapshot_path, video_path, finalized FROM pending_event "
                "WHERE source_event_id = ?",
                (source_event_id,),
            ).fetchone()
            if row is not None:
                if not row["finalized"]:
                    raise ValueError("event capture is not finalized")
                for value in (
                    () if self._retain_history else (row["snapshot_path"], row["video_path"])
                ):
                    if value:
                        self._connection.execute(
                            "INSERT OR IGNORE INTO delivered_media_cleanup VALUES (?, ?)",
                            (value, source_event_id),
                        )
            self._connection.execute(
                "UPDATE local_event_history SET delivered=1 WHERE source_event_id=?",
                (source_event_id,),
            )
            self._connection.execute(
                "DELETE FROM pending_event WHERE source_event_id = ?", (source_event_id,)
            )
        self.cleanup_delivered_media()

    def cleanup_delivered_media(self) -> None:
        """Reclaim only acknowledged media in this store's own event directory."""
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT path, source_event_id FROM delivered_media_cleanup LIMIT 128"
            ).fetchall()
            for row in rows:
                path = Path(row["path"])
                source_id = row["source_event_id"]
                if self._connection.execute(
                    "SELECT 1 FROM event_media_pin WHERE source_event_id=? LIMIT 1", (source_id,)
                ).fetchone():
                    continue
                # Do not follow symlinks, accept arbitrary queue paths or remove
                # frame spools while an encoder still owns the event directory.
                if (
                    Path(source_id).name != source_id
                    or source_id in ("", ".", "..")
                    or path.name not in ("snapshot.jpg", "evidence.mp4")
                    or path.parent != self._media_root / source_id
                    or path.parent.is_symlink()
                    or path.is_symlink()
                ):
                    continue
                referenced = self._connection.execute(
                    "SELECT 1 FROM pending_event WHERE source_event_id = ? "
                    "OR snapshot_path = ? OR video_path = ? LIMIT 1",
                    (source_id, str(path), str(path)),
                ).fetchone()
                if referenced is not None:
                    continue
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    continue  # Keep the durable receipt and retry on the next poll.
                self._connection.execute(
                    "DELETE FROM delivered_media_cleanup WHERE path = ?", (str(path),)
                )
                try:
                    path.parent.rmdir()  # Only empty directories; never recursive deletion.
                except OSError:
                    pass

    def history(self, page: int = 1, size: int = 20) -> dict:
        with self._lock:
            total = self._connection.execute("SELECT count(*) FROM local_event_history").fetchone()[
                0
            ]
            rows = self._connection.execute(
                "SELECT * FROM local_event_history ORDER BY stored_at DESC, source_event_id "
                "LIMIT ? OFFSET ?",
                (size, (page - 1) * size),
            ).fetchall()
        return {
            "total": total,
            "list": [
                {
                    "sourceEventId": r["source_event_id"],
                    "payload": json.loads(r["payload"]),
                    "finalized": bool(r["finalized"]),
                    "delivered": r["delivered"] == 1,
                    "localOnly": r["delivered"] == 2,
                    "hasSnapshot": Path(r["snapshot_path"]).is_file(),
                    "hasVideo": bool(r["video_path"]) and Path(r["video_path"]).is_file(),
                    "captureError": r["capture_error"],
                }
                for r in rows
            ],
        }

    def history_media(self, source_event_id: str, kind: str) -> Path:
        column = {"snapshot": "snapshot_path", "video": "video_path"}.get(kind)
        if column is None:
            raise KeyError(kind)
        with self._lock:
            row = self._connection.execute(
                "SELECT snapshot_path, video_path FROM local_event_history WHERE source_event_id=?",
                (source_event_id,),
            ).fetchone()
        if row is None or not row[column]:
            raise KeyError(source_event_id)
        path = Path(row[column]).resolve(strict=True)
        path.relative_to(self._media_root)
        return path

    def prune_history(self, days: int):
        # Pending uploads are never evicted merely to satisfy a display retention setting.
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT * FROM local_event_history WHERE delivered IN (1,2) "
                "AND finalized=1 AND stored_at<? LIMIT 128",
                (_now_millis() - days * 86_400_000,),
            ).fetchall()
            for row in rows:
                if self._connection.execute(
                    "SELECT 1 FROM event_media_pin WHERE source_event_id=? LIMIT 1",
                    (row["source_event_id"],),
                ).fetchone():
                    continue
                for value in (row["snapshot_path"], row["video_path"]):
                    if value:
                        self._connection.execute(
                            "INSERT OR IGNORE INTO delivered_media_cleanup VALUES (?, ?)",
                            (value, row["source_event_id"]),
                        )
                self._connection.execute(
                    "DELETE FROM local_event_history WHERE source_event_id=?",
                    (row["source_event_id"],),
                )
        self.cleanup_delivered_media()

    def defer_event(self, source_event_id: str, now_millis: int | None = None) -> None:
        self._defer("pending_event", "source_event_id", source_event_id, now_millis)

    def enqueue_transition(self, payload: dict) -> None:
        with self._lock:
            local = self._connection.execute(
                "SELECT 1 FROM local_event_history WHERE source_event_id=? AND delivered=2",
                (payload["sourceEventId"],),
            ).fetchone()
        if local:
            return
        key = f"{payload['sourceEventId']}:{payload['state']}"
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO pending_transition (delivery_key, payload) VALUES (?, ?)",
                (key, json.dumps(payload, ensure_ascii=False)),
            )

    def list_transitions(
        self, limit: int = 100, now_millis: int | None = None
    ) -> list[PendingTransition]:
        due = _now_millis() if now_millis is None else now_millis
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM pending_transition WHERE next_attempt_at_millis <= ? "
                "ORDER BY next_attempt_at_millis, rowid LIMIT ?",
                (due, limit),
            ).fetchall()
        return [
            PendingTransition.model_validate(
                {
                    "deliveryKey": row["delivery_key"],
                    "payload": json.loads(row["payload"]),
                    "deliveryAttempts": row["delivery_attempts"],
                }
            )
            for row in rows
        ]

    def acknowledge_transition(self, delivery_key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM pending_transition WHERE delivery_key = ?", (delivery_key,)
            )

    def defer_transition(self, delivery_key: str, now_millis: int | None = None) -> None:
        self._defer("pending_transition", "delivery_key", delivery_key, now_millis)

    def dead_letter_transition(
        self, delivery_key: str, reason: str, now_millis: int | None = None
    ) -> None:
        """Quarantine an unrecoverable transition without silently deleting its payload.

        A transition cannot be quarantined while its source event is still queued. That guard
        prevents a temporary event-delivery backoff from turning an out-of-order transition into
        permanent data loss.
        """
        now = _now_millis() if now_millis is None else now_millis
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT payload, delivery_attempts FROM pending_transition WHERE delivery_key = ?",
                (delivery_key,),
            ).fetchone()
            if row is None:
                return
            payload = json.loads(row["payload"])
            source_event_id = payload.get("sourceEventId")
            if not isinstance(source_event_id, str) or not source_event_id:
                raise ValueError("transition source event id is invalid")
            source_pending = self._connection.execute(
                "SELECT 1 FROM pending_event WHERE source_event_id = ? LIMIT 1",
                (source_event_id,),
            ).fetchone()
            if source_pending is not None:
                raise ValueError("source event is still pending delivery")
            self._connection.execute(
                """
                INSERT INTO dead_letter_transition
                    (delivery_key, payload, reason, delivery_attempts, dead_lettered_at_millis)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(delivery_key) DO UPDATE SET
                    payload=excluded.payload,
                    reason=excluded.reason,
                    delivery_attempts=excluded.delivery_attempts,
                    dead_lettered_at_millis=excluded.dead_lettered_at_millis
                """,
                (delivery_key, row["payload"], reason, int(row["delivery_attempts"]), now),
            )
            self._connection.execute(
                "DELETE FROM pending_transition WHERE delivery_key = ?", (delivery_key,)
            )

    def stats(self, now_millis: int | None = None) -> dict[str, int]:
        now = _now_millis() if now_millis is None else now_millis
        with self._lock:
            events = self._connection.execute(
                "SELECT payload, snapshot_path, video_path, finalized, capture_error, "
                "delivery_attempts, next_attempt_at_millis FROM pending_event"
            ).fetchall()
            transitions = self._connection.execute(
                "SELECT delivery_attempts, next_attempt_at_millis FROM pending_transition"
            ).fetchall()
            dead_letter_transitions = self._connection.execute(
                "SELECT COUNT(*) FROM dead_letter_transition"
            ).fetchone()[0]
        media_paths = [
            Path(value)
            for row in events
            for value in (row["snapshot_path"], row["video_path"])
            if value
        ]
        evidence_bytes = 0
        missing_media = 0
        for path in media_paths:
            try:
                if not path.is_file():
                    missing_media += 1
                    continue
                evidence_bytes += path.stat().st_size
            except OSError:
                # Evidence can be removed by retention or an operator between the
                # existence check and stat. Report it as missing instead of making
                # the observability endpoint fail.
                missing_media += 1
        attempts = [int(row["delivery_attempts"]) for row in (*events, *transitions)]
        occurred_times = []
        for row in events:
            try:
                payload = json.loads(row["payload"])
                occurred = payload.get("occurredTime")
                if isinstance(occurred, (int, float)) and not isinstance(occurred, bool):
                    occurred_times.append(int(occurred))
            except (json.JSONDecodeError, TypeError):
                continue
        return {
            "pendingEvents": len(events),
            "pendingTransitions": len(transitions),
            "deadLetterTransitions": int(dead_letter_transitions),
            "retryingEvents": sum(row["next_attempt_at_millis"] > now for row in events),
            "retryingTransitions": sum(row["next_attempt_at_millis"] > now for row in transitions),
            "maxDeliveryAttempts": max(attempts, default=0),
            "totalRetryCount": sum(attempts),
            "oldestEventAgeSeconds": max(0, (now - min(occurred_times)) // 1000)
            if occurred_times
            else 0,
            "evidenceBacklogBytes": evidence_bytes,
            "missingMediaFiles": missing_media,
            "captureErrors": sum(bool(row["capture_error"]) for row in events),
            "unfinalizedEvents": sum(not bool(row["finalized"]) for row in events),
        }

    def _defer(self, table: str, key_column: str, key: str, now_millis: int | None) -> None:
        if (table, key_column) == ("pending_event", "source_event_id"):
            select_sql = "SELECT delivery_attempts FROM pending_event WHERE source_event_id = ?"
            update_sql = (
                "UPDATE pending_event SET delivery_attempts = ?, next_attempt_at_millis = ? "
                "WHERE source_event_id = ?"
            )
        elif (table, key_column) == ("pending_transition", "delivery_key"):
            select_sql = "SELECT delivery_attempts FROM pending_transition WHERE delivery_key = ?"
            update_sql = (
                "UPDATE pending_transition SET delivery_attempts = ?, next_attempt_at_millis = ? "
                "WHERE delivery_key = ?"
            )
        else:
            raise ValueError("unsupported delivery queue")
        now = _now_millis() if now_millis is None else now_millis
        with self._lock, self._connection:
            row = self._connection.execute(select_sql, (key,)).fetchone()
            if row is None:
                return
            attempts = int(row["delivery_attempts"]) + 1
            delay = min(300_000, 1_000 * (2 ** min(attempts - 1, 8)))
            self._connection.execute(update_sql, (attempts, now + delay, key))


def _now_millis() -> int:
    return time.time_ns() // 1_000_000
