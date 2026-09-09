import json
import logging
import re
import threading
import time
from collections import OrderedDict, deque
from typing import Any
from uuid import uuid4


class BufferedLogHandler(logging.Handler):
    def __init__(self, capacity: int = 2000, repeat_window_seconds: float = 60) -> None:
        super().__init__(level=logging.INFO)
        self._entries: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._entries_lock = threading.Lock()
        self._repeat_window = repeat_window_seconds
        self._repeats: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
        self._repeat_capacity = min(capacity, 1000)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)[:2000]
            if record.levelno < logging.WARNING and (
                message.startswith("Heartbeat accepted nodeId=")
                or re.match(r'^HTTP Request: .*"HTTP/[0-9.]+ 2[0-9]{2}[^"]*"$', message)
            ):
                return
            context = {"logger": record.name}
            error_type = getattr(record, "errorType", None)
            if error_type:
                context["errorType"] = str(error_type)
            entry = {
                "entryId": str(uuid4()),
                "taskId": getattr(record, "taskId", None),
                "runId": getattr(record, "runId", None),
                "component": str(getattr(record, "component", "EDGE_AGENT")),
                "level": _level(record.levelno),
                "message": message,
                "contextJson": json.dumps(context, ensure_ascii=False),
                "diagnosticId": getattr(record, "diagnosticId", None),
                "timestampMillis": int(record.created * 1000),
            }
            with self._entries_lock:
                now = time.monotonic()
                self._flush_repeats(now)
                if record.levelno >= logging.WARNING:
                    key = (record.name, entry["component"], entry["level"], message,
                           entry["taskId"], entry["runId"], entry["diagnosticId"])
                    if key in self._repeats:
                        self._repeats[key]["count"] += 1
                        return
                    if len(self._repeats) >= self._repeat_capacity:
                        _, oldest = self._repeats.popitem(last=False)
                        self._append_summary(oldest)
                    self._repeats[key] = {"entry": entry, "since": now, "count": 0}
                self._entries.append(entry)
        except (TypeError, ValueError):
            self.handleError(record)

    def _append_summary(self, state: dict[str, Any]) -> None:
        if not state["count"]:
            return
        original = state["entry"]
        context = json.loads(original["contextJson"])
        context.update(repeatCount=state["count"], windowSeconds=self._repeat_window)
        self._entries.append({
            **original, "entryId": str(uuid4()),
            "message": f"{original['message'][:1850]} （另有 {state['count']} 次重复，已合并）",
            "contextJson": json.dumps(context, ensure_ascii=False),
            "timestampMillis": int(time.time() * 1000),
        })

    def _flush_repeats(self, now: float) -> None:
        while self._repeats:
            key, state = next(iter(self._repeats.items()))
            if now - state["since"] < self._repeat_window:
                break
            self._repeats.pop(key)
            self._append_summary(state)

    def peek(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._entries_lock:
            self._flush_repeats(time.monotonic())
            return list(self._entries)[:limit]

    def acknowledge(self, entries: list[dict[str, Any]]) -> None:
        entry_ids = {entry["entryId"] for entry in entries}
        with self._entries_lock:
            self._entries = deque(
                (entry for entry in self._entries if entry["entryId"] not in entry_ids),
                maxlen=self._entries.maxlen,
            )


def _level(value: int) -> str:
    if value >= logging.ERROR:
        return "ERROR"
    if value >= logging.WARNING:
        return "WARN"
    if value >= logging.INFO:
        return "INFO"
    return "DEBUG"


def log_record(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    component: str,
    task_id: int | None = None,
    run_id: str | None = None,
    diagnostic_id: str | None = None,
    error_type: str | None = None,
) -> None:
    logger.log(
        level,
        message,
        extra={
            "component": component,
            "taskId": task_id,
            "runId": run_id,
            "diagnosticId": diagnostic_id,
            "errorType": error_type,
        },
    )
