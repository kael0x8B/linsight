"""Authenticated live-only TCP event feed owned by one gateway."""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

LOGGER = logging.getLogger("linsight.gateway.event_stream")
MAX_LINE = 4096
IMAGE_URL_TTL_SECONDS = 3600
HEARTBEAT_INTERVAL_SECONDS = 30
EVENT_POLL_INTERVAL_SECONDS = 0.5


def timestamp(millis):
    return datetime.fromtimestamp(millis / 1000, UTC).isoformat(timespec="milliseconds")


class GatewayEventStream:
    def __init__(self, events, secret_store, media_root: Path, host: str, port: int,
                 image_http_port: int = 48901, image_http_enabled: bool = True):
        self.events, self.secret_store = events, secret_store
        self.media_root = media_root.resolve()
        self.host, self.port = host, port
        self.image_http_port = image_http_port
        self.image_http_enabled = image_http_enabled
        self.server = None
        self.clients = 0
        self._writers = set()
        with events.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS gateway_tcp_config (
                    id INTEGER PRIMARY KEY CHECK (id=1), enabled INTEGER NOT NULL,
                    revision INTEGER NOT NULL, secret BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gateway_tcp_event (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_event_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
                    snapshot_path TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_gateway_tcp_event_created
                    ON gateway_tcp_event(created_at);
            """)
            # 旧 V2 表只改内部列名；历史事件不会重发给 V3 订阅者。
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(gateway_tcp_event)").fetchall()
            }
            if "cursor" in columns and "sequence" not in columns:
                db.execute("ALTER TABLE gateway_tcp_event RENAME COLUMN cursor TO sequence")
            if not db.execute("SELECT 1 FROM gateway_tcp_config WHERE id=1").fetchone():
                db.execute(
                    "INSERT INTO gateway_tcp_config VALUES (1, 0, 0, ?)",
                    (secret_store.encrypt_document({"key": secrets.token_urlsafe(32)}),),
                )
            # Legacy HTTP deliveries are no longer processed. Keep their rows for
            # migration inspection, but release media pins held only by that queue.
            db.execute("DELETE FROM event_media_pin WHERE owner LIKE 'gateway:%'")
        events.on_event_created = self.capture

    def status(self):
        with self.events.transaction() as db:
            row = db.execute(
                "SELECT enabled,revision FROM gateway_tcp_config WHERE id=1"
            ).fetchone()
        return {
            "enabled": bool(row["enabled"]),
            "revision": row["revision"],
            "host": self.host,
            "port": self.port,
            "listening": self.server is not None,
            "clients": self.clients,
            "imageHttpPort": self.image_http_port,
            "imageHttpEnabled": self.image_http_enabled,
        }

    def configure(self, enabled: bool, rotate_key: bool, expected_revision: int):
        if not isinstance(enabled, bool) or not isinstance(rotate_key, bool):
            raise ValueError("invalid stream configuration")
        if enabled and (not self.image_http_enabled or not self.image_http_port):
            raise ValueError("event image HTTP service must be enabled")
        new_key = secrets.token_urlsafe(32) if rotate_key else None
        with self.events.transaction() as db:
            row = db.execute("SELECT * FROM gateway_tcp_config WHERE id=1").fetchone()
            if row["revision"] != expected_revision:
                raise ValueError("stream configuration changed")
            if enabled and row["revision"] == 0 and not rotate_key:
                raise ValueError("generate a subscriber key before enabling")
            db.execute(
                "UPDATE gateway_tcp_config SET enabled=?,revision=?,secret=? WHERE id=1",
                (
                    int(enabled),
                    expected_revision + 1,
                    self.secret_store.encrypt_document({"key": new_key})
                    if new_key
                    else row["secret"],
                ),
            )
        return {**self.status(), "key": new_key}

    def capture(self, db, event):
        source = event.payload
        names = source.get("taskSnapshot", {}).get("displayNames", {})
        location = source.get("taskSnapshot", {}).get("location", {})
        payload = {
            "type": "ai-video.event.created",  # 消息类型：新建识别事件
            "version": "3.0",  # TCP 实时订阅协议版本
            "sourceEventId": event.source_event_id,  # 事件唯一 ID，接收方幂等键
            "deliverySource": "GATEWAY",  # 事件来源：盒子本地
            "occurredAt": timestamp(source["occurredTime"]),  # 顶层事件发生时间
            "data": {
                "sourceEventId": event.source_event_id,  # 与顶层相同的事件 ID
                "eventType": source.get("eventType"),  # 业务事件类型，如车牌识别
                "severity": source.get("severity"),  # 事件严重程度
                "occurredAt": timestamp(source["occurredTime"]),  # 事件发生时间
                "taskId": source.get("taskId"),  # 识别任务 ID
                "taskName": names.get("task", ""),  # 任务显示名称
                "taskRunId": source.get("taskRunId"),  # 本次任务运行 ID
                "algorithmId": source.get("algorithmId"),  # 识别算法 ID
                "algorithmName": names.get("algorithm", ""),  # 算法显示名称
                "modelVersionId": source.get("modelVersionId"),  # 模型版本 ID
                "pipelineVersionId": source.get("pipelineVersionId"),  # Pipeline 版本 ID
                "ruleId": source.get("ruleId"),  # 触发规则 ID
                "ruleVersionId": source.get("ruleVersionId"),  # 规则版本 ID
                "cameraId": source.get("cameraId"),  # 发生事件的摄像头 ID
                # 摄像头名称：优先取任务中的位置快照。
                "cameraName": location.get("cameraName") or names.get("camera", ""),
                "location": location,  # 任务配置的位置属性；未配置时为空对象
                # 通用目标识别结果；attributes 为算法专有的可选扩展属性。
                "result": source.get("objectSnapshot", {}),
                "activityId": source.get("activityId"),  # 规则活动 ID
                "dedupKey": source.get("dedupKey"),  # 规则去重键
                "trackId": source.get("trackId"),  # 事件级目标跟踪 ID
                "firstSeenAt": timestamp(source["firstSeenTime"])
                if source.get("firstSeenTime") is not None
                else None,  # 目标首次观察时间
                "lastSeenAt": timestamp(source["lastSeenTime"])
                if source.get("lastSeenTime") is not None
                else None,  # 目标最近观察时间
                "durationMs": source.get("durationMs"),  # 持续时间，毫秒
                "maxConfidence": source.get("maxConfidence"),  # 确认期间最高置信度
            },
        }
        now = time.time_ns() // 1_000_000
        inserted = db.execute(
            "INSERT OR IGNORE INTO gateway_tcp_event"
            "(source_event_id,payload,snapshot_path,created_at) "
            "VALUES (?,?,?,?)",
            (
                event.source_event_id,
                json.dumps(payload, ensure_ascii=False),
                str(event.snapshot_path),
                now,
            ),
        )
        if inserted.rowcount:
            db.execute(
                "INSERT OR IGNORE INTO event_media_pin VALUES (?,?)",
                ("tcp:" + event.source_event_id, event.source_event_id),
            )

    def prune(self, days: int):
        cutoff = time.time_ns() // 1_000_000 - days * 86_400_000
        with self.events.transaction() as db:
            rows = db.execute(
                "SELECT source_event_id FROM gateway_tcp_event WHERE created_at<? "
                "ORDER BY sequence LIMIT 128",
                (cutoff,),
            ).fetchall()
            for row in rows:
                db.execute("DELETE FROM gateway_tcp_event WHERE source_event_id=?", (row[0],))
                db.execute("DELETE FROM event_media_pin WHERE owner=?", ("tcp:" + row[0],))

    async def start(self):
        if self.port:
            self.server = await asyncio.start_server(
                self._client, self.host, self.port, limit=MAX_LINE
            )

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        for writer in tuple(self._writers):
            writer.close()
        await asyncio.gather(
            *(writer.wait_closed() for writer in tuple(self._writers)), return_exceptions=True
        )
        self.events.on_event_created = None

    @staticmethod
    async def _write(writer, document):
        writer.write(
            (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        )
        await asyncio.wait_for(writer.drain(), 10)

    @staticmethod
    async def _read(reader):
        raw = await asyncio.wait_for(reader.readline(), 10)
        if not raw or len(raw) > MAX_LINE or not raw.endswith(b"\n"):
            raise ValueError("invalid or timed-out frame")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("object required")
        return value

    def _latest_sequence(self):
        with self.events.transaction() as db:
            return db.execute("SELECT max(sequence) FROM gateway_tcp_event").fetchone()[0] or 0

    def _rows(self, sequence):
        with self.events.transaction() as db:
            rows = db.execute(
                "SELECT * FROM gateway_tcp_event WHERE sequence>? ORDER BY sequence LIMIT 20",
                (sequence,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _with_image_url(self, row, image_host: str, key: bytes):
        path = Path(row["snapshot_path"]).resolve(strict=True)
        path.relative_to(self.media_root)
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("snapshot unavailable")
        with path.open("rb") as image:
            digest = hashlib.file_digest(image, "sha256").hexdigest()
        payload = json.loads(row["payload"])
        expires = int(time.time()) + IMAGE_URL_TTL_SECONDS
        source_id = row["source_event_id"]
        signature = hmac.new(
            key, f"snapshot:{source_id}:{expires}".encode(), hashlib.sha256
        ).hexdigest()
        payload["data"]["snapshot"] = {
            "contentType": "image/jpeg",  # HTTP 图片媒体类型
            # 限时签名下载地址；image_host 来自当前 TCP 连接的盒子本地地址，不是固定 IP。
            "url": (f"http://{image_host}:{self.image_http_port}/event-images/"
                    f"{source_id}?expires={expires}&signature={signature}"),
            "sha256": digest,  # 原始 JPEG 文件 SHA-256，小写十六进制
            "expiresAt": timestamp(expires * 1000),  # 图片地址失效时间
        }
        return payload

    def authorized_image_path(self, source_event_id: str, expires: int, signature: str) -> Path:
        """校验限时图片 URL，且只允许访问本地事件证据目录中的截图。"""
        source_id = str(UUID(source_event_id))
        if expires < int(time.time()) or expires > int(time.time()) + IMAGE_URL_TTL_SECONDS:
            raise ValueError("image link expired")
        if len(signature) != 64 or any(char not in "0123456789abcdef" for char in signature):
            raise ValueError("invalid image signature")
        with self.events.transaction() as db:
            row = db.execute("SELECT enabled,secret FROM gateway_tcp_config WHERE id=1").fetchone()
        if not row["enabled"]:
            raise ValueError("subscription disabled")
        key = self.secret_store.decrypt_document(row["secret"])["key"].encode()
        expected = hmac.new(
            key, f"snapshot:{source_id}:{expires}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid image signature")
        path = self.events.history_media(source_id, "snapshot")
        path.relative_to(self.media_root)
        if not path.is_file():
            raise ValueError("snapshot unavailable")
        return path

    async def _client(self, reader, writer):
        if self.clients >= 16:
            writer.close()
            return
        self.clients += 1
        self._writers.add(writer)
        try:
            with self.events.transaction() as db:
                row = db.execute("SELECT * FROM gateway_tcp_config WHERE id=1").fetchone()
            if not row["enabled"]:
                await self._write(writer, {"type": "error", "code": "DISABLED"})
                return
            revision = row["revision"]
            key = self.secret_store.decrypt_document(row["secret"])["key"].encode()
            nonce = secrets.token_hex(24)
            await self._write(writer, {"type": "challenge", "version": "3.0", "nonce": nonce})
            auth = await self._read(reader)
            expected = hmac.new(key, nonce.encode(), hashlib.sha256).hexdigest()
            if auth.get("type") != "auth" or not hmac.compare_digest(
                str(auth.get("hmac", "")), expected
            ):
                await self._write(writer, {"type": "error", "code": "UNAUTHORIZED"})
                return
            await self._write(writer, {"type": "authenticated"})
            subscription = await self._read(reader)
            if subscription.get("type") != "subscribe":
                raise ValueError("subscribe required")
            if "cursor" in subscription:
                raise ValueError("cursor is not supported by live subscriptions")
            task_ids = subscription.get("taskIds", [])
            event_types = subscription.get("eventTypes", [])
            if (
                not isinstance(task_ids, list)
                or len(task_ids) > 100
                or any(type(v) is not int or v <= 0 for v in task_ids)
                or not isinstance(event_types, list)
                or len(event_types) > 100
                or any(not isinstance(v, str) or len(v) > 100 for v in event_types)
            ):
                raise ValueError("invalid subscription")
            if not self.image_http_enabled or not self.image_http_port:
                await self._write(writer, {"type": "error", "code": "IMAGE_HTTP_UNAVAILABLE"})
                return
            # 以当前序号为边界，只发送订阅确认后新产生的事件。
            sequence = self._latest_sequence()
            image_host = writer.get_extra_info("sockname")[0]
            await self._write(writer, {"type": "subscribed"})
            next_heartbeat_at = time.monotonic()
            while True:
                with self.events.transaction() as db:
                    current = db.execute(
                        "SELECT enabled,revision FROM gateway_tcp_config WHERE id=1"
                    ).fetchone()
                if not current["enabled"] or current["revision"] != revision:
                    await self._write(writer, {"type": "error", "code": "CONFIG_CHANGED"})
                    return
                rows = self._rows(sequence)
                for row in rows:
                    data = json.loads(row["payload"])["data"]
                    if (not task_ids or data["taskId"] in task_ids) and (
                        not event_types or data["eventType"] in event_types
                    ):
                        try:
                            payload = await asyncio.to_thread(
                                self._with_image_url, row, image_host, key
                            )
                        except (OSError, ValueError):
                            await self._write(
                                writer,
                                {
                                    "type": "error",
                                    "code": "SNAPSHOT_UNAVAILABLE",
                                    "sourceEventId": row["source_event_id"],
                                },
                            )
                            return
                        await self._write(writer, payload)
                    sequence = row["sequence"]
                # 心跳按 30 秒节奏发送；事件仍按 0.5 秒轮询，不因心跳变慢。
                if time.monotonic() >= next_heartbeat_at:
                    await self._write(writer, {"type": "heartbeat"})
                    next_heartbeat_at = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS
                if not rows:
                    await asyncio.sleep(EVENT_POLL_INTERVAL_SECONDS)
        except (ValueError, json.JSONDecodeError, TimeoutError) as error:
            with suppress(OSError, ConnectionError, TimeoutError):
                await self._write(writer, {"type": "error", "code": "BAD_REQUEST"})
            LOGGER.info("TCP subscriber rejected: %s", type(error).__name__)
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            self.clients -= 1
            self._writers.discard(writer)
            writer.close()
            with suppress(ConnectionError, OSError):
                await writer.wait_closed()
