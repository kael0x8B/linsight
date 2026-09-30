"""Device-owned, explicitly routed delivery; independent of the platform upload ACK."""

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import re
import socket
import time
from contextlib import suppress
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

LOGGER = logging.getLogger("linsight.gateway.delivery")
INTERNAL_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


class DeliveryConflict(ValueError):
    pass


class TargetChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    expected_revision: int = Field(alias="expectedRevision", ge=0)
    request_id: UUID = Field(alias="requestId")
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    network: Literal["INTERNAL", "PUBLIC"] = "PUBLIC"
    enabled: bool = False
    auth_header: str = Field(default="Authorization", alias="authHeader", max_length=100)
    auth_value: SecretStr | None = Field(default=None, alias="authValue", max_length=2048)
    clear_auth: bool = Field(default=False, alias="clearAuth")
    timeout_ms: int = Field(default=5000, alias="timeoutMs", ge=500, le=10000)
    max_attempts: int = Field(default=5, alias="maxAttempts", ge=1, le=10)

    @model_validator(mode="after")
    def validate_destination(self):
        parsed = urlsplit(self.url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (self.network == "PUBLIC" and parsed.scheme != "https")
        ):
            raise ValueError("invalid destination")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("invalid port")
        if (
            not re.fullmatch(r"[A-Za-z0-9-]+", self.auth_header)
            or self.auth_header.lower()
            in {
                "host",
                "content-length",
                "content-type",
                "connection",
                "transfer-encoding",
            }
            or self.auth_header.lower().startswith("x-linsight-")
        ):
            raise ValueError("invalid authentication header")
        if self.auth_value and any(c in self.auth_value.get_secret_value() for c in "\r\n"):
            raise ValueError("invalid authentication value")
        return self


class RouteChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: int = Field(alias="taskId", gt=0)
    expected_revision: int = Field(alias="expectedRevision", ge=0)
    request_id: UUID = Field(alias="requestId")
    enabled: bool = False
    target_ids: list[UUID] = Field(alias="targetIds", default_factory=list, max_length=10)
    event_types: list[str] = Field(alias="eventTypes", default_factory=list, max_length=50)
    location_code: str = Field(alias="locationCode", default="", max_length=64)
    location_name: str = Field(alias="locationName", default="", max_length=100)
    camera_name: str = Field(alias="cameraName", default="", max_length=100)

    @model_validator(mode="after")
    def validate_targets(self):
        if self.enabled and not self.target_ids:
            raise ValueError("an enabled route needs an explicit target")
        if len(set(self.target_ids)) != len(self.target_ids):
            raise ValueError("duplicate target")
        if any(not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value) for value in self.event_types):
            raise ValueError("invalid event type")
        return self


def _millis():
    return time.time_ns() // 1_000_000


def _timestamp(millis):
    return datetime.fromtimestamp(millis / 1000, UTC).isoformat(timespec="milliseconds")


def _safe_address(address: str, network: str) -> bool:
    ip = ipaddress.ip_address(address)
    ip = getattr(ip, "ipv4_mapped", None) or ip
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return False
    return ip.is_global if network == "PUBLIC" else any(ip in net for net in INTERNAL_NETWORKS)


async def _resolve_target(target):
    """Pin the validated IP for this attempt, preserving Host/SNI for TLS validation."""
    url = httpx.URL(target["url"])
    port = url.port or (443 if url.scheme == "https" else 80)
    addresses = await asyncio.to_thread(socket.getaddrinfo, url.host, port, type=socket.SOCK_STREAM)
    hosts = list(dict.fromkeys(item[4][0] for item in addresses))
    if not hosts or any(not _safe_address(host, target["network"]) for host in hosts):
        raise ValueError("DESTINATION_ADDRESS_REJECTED")
    return url.copy_with(host=hosts[0]), url.netloc.decode("ascii"), url.host


class GatewayEventDelivery:
    def __init__(self, events, secrets, media_root: Path):
        self.events, self.secrets = events, secrets
        self.media_root = media_root.resolve()
        self._worker = None
        with events.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS gateway_event_target (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, enabled INTEGER NOT NULL,
                    document BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gateway_event_route (
                    task_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gateway_delivery_receipt (
                    request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gateway_event_delivery (
                    id TEXT PRIMARY KEY, source_event_id TEXT NOT NULL, target_id TEXT NOT NULL,
                    target_name TEXT NOT NULL, target_revision INTEGER NOT NULL,
                    target_document BLOB NOT NULL, payload TEXT NOT NULL,
                    snapshot_path TEXT NOT NULL,
                    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt INTEGER NOT NULL, created_at INTEGER NOT NULL,
                    last_attempt INTEGER, response_status INTEGER, last_error TEXT,
                    UNIQUE(source_event_id, target_id)
                );
                CREATE INDEX IF NOT EXISTS ix_gateway_delivery_due
                    ON gateway_event_delivery(status, next_attempt);
            """)
            db.execute("UPDATE gateway_event_delivery SET status='RETRY' WHERE status='SENDING'")
        events.on_event_created = self.capture

    async def start(self):
        self._worker = asyncio.create_task(self._run(), name="gateway-event-delivery")

    async def close(self):
        if self._worker:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
        self.events.on_event_created = None

    def _receipt(self, db, request_id, document):
        fingerprint = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        receipt = db.execute(
            "SELECT * FROM gateway_delivery_receipt WHERE request_id=?", (str(request_id),)
        ).fetchone()
        if receipt and receipt["fingerprint"] != fingerprint:
            raise DeliveryConflict("request identity changed")
        return fingerprint, json.loads(receipt["result"]) if receipt else None

    @staticmethod
    def _record_receipt(db, request_id, fingerprint, result):
        db.execute(
            "INSERT INTO gateway_delivery_receipt VALUES (?, ?, ?)",
            (str(request_id), fingerprint, json.dumps(result)),
        )

    @staticmethod
    def _public_target(document, revision):
        return {
            **{k: v for k, v in document.items() if k != "authValue"},
            "revision": revision,
            "authConfigured": bool(document.get("authValue")),
        }

    def targets(self):
        with self.events.transaction() as db:
            return [
                self._public_target(self.secrets.decrypt_document(row["document"]), row["revision"])
                for row in db.execute("SELECT * FROM gateway_event_target ORDER BY rowid")
            ]

    def save_target(self, change: TargetChange):
        body = change.model_dump(
            mode="json",
            by_alias=True,
            exclude={"request_id", "expected_revision", "auth_value", "clear_auth"},
        )
        auth = change.auth_value.get_secret_value() if change.auth_value else None
        with self.events.transaction() as db:
            fingerprint, receipt = self._receipt(
                db,
                change.request_id,
                {
                    **body,
                    "auth": auth,
                    "clear": change.clear_auth,
                    "revision": change.expected_revision,
                },
            )
            if receipt:
                return receipt
            old = db.execute(
                "SELECT * FROM gateway_event_target WHERE id=?", (str(change.id),)
            ).fetchone()
            revision = old["revision"] if old else 0
            if revision != change.expected_revision:
                raise DeliveryConflict("target changed")
            previous = self.secrets.decrypt_document(old["document"]) if old else {}
            body["authValue"] = "" if change.clear_auth else (auth or previous.get("authValue", ""))
            db.execute(
                "INSERT INTO gateway_event_target VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision, "
                "enabled=excluded.enabled, document=excluded.document",
                (
                    str(change.id),
                    revision + 1,
                    int(change.enabled),
                    self.secrets.encrypt_document(body),
                ),
            )
            result = self._public_target(body, revision + 1)
            self._record_receipt(db, change.request_id, fingerprint, result)
            return result

    def route(self, task_id):
        with self.events.transaction() as db:
            row = db.execute(
                "SELECT * FROM gateway_event_route WHERE task_id=?", (task_id,)
            ).fetchone()
            return (
                {**self._route_document(row["document"]), "revision": row["revision"]}
                if row
                else {
                    "taskId": task_id,
                    "revision": 0,
                    "enabled": False,
                    "targetIds": [],
                    "eventTypes": [],
                    "locationCode": "",
                    "locationName": "",
                    "cameraName": "",
                }
            )

    @staticmethod
    def _route_document(raw):
        route = json.loads(raw)
        # Read configs saved by the initial scene-specific preview without losing their location.
        route.setdefault("locationCode", route.pop("siloCode", ""))
        route.setdefault("locationName", route.pop("siloName", ""))
        route.setdefault("eventTypes", [])
        return route

    def save_route(self, change: RouteChange):
        body = change.model_dump(
            mode="json", by_alias=True, exclude={"request_id", "expected_revision"}
        )
        with self.events.transaction() as db:
            fingerprint, receipt = self._receipt(
                db, change.request_id, {**body, "revision": change.expected_revision}
            )
            if receipt:
                return receipt
            row = db.execute(
                "SELECT revision FROM gateway_event_route WHERE task_id=?", (change.task_id,)
            ).fetchone()
            revision = row[0] if row else 0
            if revision != change.expected_revision:
                raise DeliveryConflict("route changed")
            for target_id in change.target_ids:
                if (
                    db.execute(
                        "SELECT 1 FROM gateway_event_target WHERE id=?", (str(target_id),)
                    ).fetchone()
                    is None
                ):
                    raise ValueError("target does not exist")
            db.execute(
                "INSERT INTO gateway_event_route VALUES (?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET revision=excluded.revision, "
                "document=excluded.document",
                (change.task_id, revision + 1, json.dumps(body)),
            )
            result = {**body, "revision": revision + 1}
            self._record_receipt(db, change.request_id, fingerprint, result)
            return result

    def capture(self, db, event):
        """Called inside the event's transaction, before either upload consumer sees it."""
        source = event.payload
        row = db.execute(
            "SELECT * FROM gateway_event_route WHERE task_id=?", (source.get("taskId"),)
        ).fetchone()
        if row is None:
            return
        route = self._route_document(row["document"])
        names = source.get("taskSnapshot", {}).get("displayNames", {})
        location = {
            key: route.get(key, "") for key in ("locationCode", "locationName", "cameraName")
        }
        location["cameraName"] = location["cameraName"] or names.get("camera", "")
        source.setdefault("taskSnapshot", {})["location"] = location
        if not route["enabled"] or (
            route["eventTypes"] and source.get("eventType") not in route["eventTypes"]
        ):
            return
        now = _millis()
        for target_id in route["targetIds"]:
            target = db.execute(
                "SELECT * FROM gateway_event_target WHERE id=? AND enabled=1", (target_id,)
            ).fetchone()
            if target is None:
                continue
            config = self.secrets.decrypt_document(target["document"])
            delivery_id = str(uuid4())
            payload = {
                "type": "ai-video.event.created",
                "version": "1.0",
                "messageId": delivery_id,
                "sourceEventId": event.source_event_id,
                "deliverySource": "GATEWAY",
                "occurredAt": _timestamp(source["occurredTime"]),
                "data": {
                    "eventType": source["eventType"],
                    "sourceEventId": event.source_event_id,
                    "severity": source.get("severity"),
                    "occurredAt": _timestamp(source["occurredTime"]),
                    "taskId": source["taskId"],
                    "taskName": names.get("task", ""),
                    "algorithmId": source.get("algorithmId"),
                    "algorithmName": names.get("algorithm", ""),
                    "cameraId": source["cameraId"],
                    "cameraName": location["cameraName"],
                    "location": location,
                    "result": source.get("objectSnapshot", {}),
                },
            }
            inserted = db.execute(
                "INSERT OR IGNORE INTO gateway_event_delivery "
                "(id,source_event_id,target_id,target_name,target_revision,target_document,payload,"
                "snapshot_path,status,next_attempt,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    delivery_id,
                    event.source_event_id,
                    target_id,
                    config["name"],
                    target["revision"],
                    target["document"],
                    json.dumps(payload, ensure_ascii=False),
                    str(event.snapshot_path),
                    "PENDING",
                    now,
                    now,
                ),
            )
            if inserted.rowcount:
                db.execute(
                    "INSERT OR IGNORE INTO event_media_pin VALUES (?, ?)",
                    ("gateway:" + delivery_id, event.source_event_id),
                )

    def records(self, page=1, size=20):
        if page < 1 or not 1 <= size <= 100:
            raise ValueError("invalid page")
        with self.events.transaction() as db:
            total = db.execute("SELECT count(*) FROM gateway_event_delivery").fetchone()[0]
            rows = db.execute(
                "SELECT d.*, t.enabled AS target_enabled FROM gateway_event_delivery d "
                "JOIN gateway_event_target t ON t.id=d.target_id "
                "ORDER BY d.created_at DESC, d.id LIMIT ? OFFSET ?",
                (size, (page - 1) * size),
            ).fetchall()
        return {
            "total": total,
            "list": [
                {
                    "id": r["id"],
                    "sourceEventId": r["source_event_id"],
                    "targetName": r["target_name"],
                    "targetRevision": r["target_revision"],
                    "targetEnabled": bool(r["target_enabled"]),
                    "status": r["status"],
                    "attempts": r["attempts"],
                    "createdAt": _timestamp(r["created_at"]),
                    "responseStatus": r["response_status"],
                    "lastError": r["last_error"],
                    "nextAttemptAt": _timestamp(r["next_attempt"]),
                    "data": json.loads(r["payload"])["data"],
                }
                for r in rows
            ],
        }

    def retry(self, delivery_id, request_id):
        identity = str(UUID(delivery_id))
        with self.events.transaction() as db:
            fingerprint, receipt = self._receipt(db, UUID(request_id), {"retry": identity})
            if receipt:
                return receipt
            row = db.execute(
                "SELECT status FROM gateway_event_delivery WHERE id=?", (identity,)
            ).fetchone()
            if row is None or row[0] != "DEAD":
                raise ValueError("only failed deliveries can be replayed")
            db.execute(
                "UPDATE gateway_event_delivery SET status='PENDING', attempts=0, next_attempt=?, "
                "last_error=NULL WHERE id=?",
                (_millis(), identity),
            )
            result = {"queued": True}
            self._record_receipt(db, request_id, fingerprint, result)
            return result

    def _request_body(self, row):
        path = Path(row["snapshot_path"]).resolve(strict=True)
        path.relative_to(self.media_root)
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("snapshot unavailable")
        with Image.open(path) as picture:
            picture.thumbnail((1920, 1080))
            output = BytesIO()
            picture.convert("RGB").save(output, "JPEG", quality=85)
        content = output.getvalue()
        if len(content) > 2 * 1024 * 1024:
            raise ValueError("snapshot exceeds delivery size limit")
        payload = json.loads(row["payload"])
        payload["data"]["snapshot"] = {
            "contentType": "image/jpeg",
            "base64": base64.b64encode(content).decode(),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        return payload

    async def _send(self, target, payload, source_id):
        url, host, sni = await asyncio.wait_for(_resolve_target(target), timeout=5)
        headers = {
            "Host": host,
            "X-LInsight-Source-Event-Id": source_id,
            "X-LInsight-Delivery-Source": "GATEWAY",
            "X-LInsight-Event-Id": source_id,
        }
        if target.get("authValue"):
            headers[target["authHeader"]] = target["authValue"]
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=target["timeoutMs"] / 1000
        ) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers, extensions={"sni_hostname": sni}
            ) as response:
                # Do not persist receiver response bodies: they can echo credentials and images.
                return response.status_code

    async def deliver_once(self):
        with self.events.transaction() as db:
            rows = db.execute(
                "SELECT d.* FROM gateway_event_delivery d JOIN gateway_event_target t "
                "ON t.id=d.target_id WHERE d.status IN ('PENDING','RETRY') "
                "AND d.next_attempt<=? AND t.enabled=1 ORDER BY d.next_attempt LIMIT 4",
                (_millis(),),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE gateway_event_delivery SET status='SENDING' WHERE id=?", (row["id"],)
                )
        await asyncio.gather(*(self._deliver(dict(row)) for row in rows))

    async def _deliver(self, row):
        max_attempts = 1
        status_code, error = None, None
        try:
            target = self.secrets.decrypt_document(row["target_document"])
            max_attempts = target["maxAttempts"]
            body = await asyncio.to_thread(self._request_body, row)
            status_code = await asyncio.wait_for(
                self._send(target, body, row["source_event_id"]),
                target["timeoutMs"] / 1000 + 6,
            )
            if not 200 <= status_code < 300:
                error = f"HTTP_{status_code}"
        except (ValueError, OSError, Image.DecompressionBombError):
            error = "DESTINATION_OR_SNAPSHOT_INVALID"
        except (httpx.HTTPError, TimeoutError):
            error = "NETWORK_OR_TIMEOUT"
        except Exception as cause:
            LOGGER.warning("Gateway attempt failed errorType=%s", type(cause).__name__)
            error = "DELIVERY_FAILED"
        attempts = row["attempts"] + 1
        status = "SUCCEEDED" if error is None else "DEAD" if attempts >= max_attempts else "RETRY"
        now = _millis()
        with self.events.transaction() as db:
            db.execute(
                "UPDATE gateway_event_delivery SET status=?, attempts=?, next_attempt=?, "
                "last_attempt=?, response_status=?, last_error=? WHERE id=?",
                (
                    status,
                    attempts,
                    now + min(3600, 5 * 2 ** (attempts - 1)) * 1000,
                    now,
                    status_code,
                    error,
                    row["id"],
                ),
            )
            if status == "SUCCEEDED":
                db.execute("DELETE FROM event_media_pin WHERE owner=?", ("gateway:" + row["id"],))

    async def _run(self):
        while True:
            try:
                await self.deliver_once()
            except Exception as error:
                LOGGER.warning("Gateway delivery deferred errorType=%s", type(error).__name__)
            await asyncio.sleep(1)
