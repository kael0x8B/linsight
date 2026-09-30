"""Device-owned configuration journal; secrets never appear in SQLite plaintext."""

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

from ai_runtime.app.task.validation import ValidationRepository


class GatewayStore:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        key_path = root / "configuration.key"
        try:
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as output:
                output.write(Fernet.generate_key())
                output.flush()
                os.fsync(output.fileno())
            directory = os.open(root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        self._cipher = Fernet(key_path.read_bytes())
        path = root / "configuration.sqlite3"
        self._db = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS task_configuration ("
                "task_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, document BLOB NOT NULL)"
            )
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS mutation_receipt ("
                "request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, "
                "task_id INTEGER NOT NULL, revision INTEGER NOT NULL)"
            )
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS task_removal ("
                "task_id INTEGER PRIMARY KEY, document BLOB NOT NULL, "
                "acknowledged INTEGER NOT NULL DEFAULT 0)"
            )
            self._recover_legacy_removals()
        self.validation = ValidationRepository(self._db, self._cipher, root)

    def _recover_legacy_removals(self) -> None:
        # Older releases retained the exact remove fingerprint but did not notify
        # the platform. Recover only proven deletions, never infer one from absence.
        rows = self._db.execute(
            "SELECT r.* FROM mutation_receipt r "
            "WHERE NOT EXISTS (SELECT 1 FROM task_configuration t WHERE t.task_id=r.task_id) "
            "AND NOT EXISTS (SELECT 1 FROM task_removal d WHERE d.task_id=r.task_id) "
            "ORDER BY r.revision DESC"
        ).fetchall()
        for row in rows:
            fingerprint = hashlib.sha256(
                f"remove:{row['task_id']}:{row['revision']}".encode()
            ).hexdigest()
            if row["fingerprint"] != fingerprint:
                continue
            start = self._db.execute(
                "SELECT request_id FROM mutation_receipt WHERE task_id=? AND revision<=? "
                "AND request_id LIKE 'platform-start:%' ORDER BY revision DESC LIMIT 1",
                (row["task_id"], row["revision"]),
            ).fetchone()
            document = {
                "schemaVersion": "1.0",
                "taskId": row["task_id"],
                "gatewayRevision": row["revision"] + 1,
                "requestId": row["request_id"],
                "platformManaged": start is not None,
                "removedAt": datetime.now(UTC).isoformat(),
            }
            if start:
                _, run_id, version = start["request_id"].split(":")
                document.update(runId=run_id, configVersion=int(version))
            self._db.execute(
                "INSERT OR IGNORE INTO task_removal(task_id, document) VALUES (?, ?)",
                (row["task_id"], self.encrypt_document(document)),
            )

    def removals(self, pending_only: bool = False) -> list[dict]:
        return [
            self.decrypt_document(row[0])
            for row in self._db.execute(
                "SELECT document FROM task_removal WHERE (?=0 OR acknowledged=0) ORDER BY task_id",
                (int(pending_only),),
            ).fetchall()
        ]

    def is_removed(self, task_id: int) -> bool:
        return (
            self._db.execute("SELECT 1 FROM task_removal WHERE task_id=?", (task_id,)).fetchone()
            is not None
        )

    def acknowledge_removal(self, task_id: int, request_id: str, revision: int) -> None:
        with self._db:
            row = self._db.execute(
                "SELECT document FROM task_removal WHERE task_id=?", (task_id,)
            ).fetchone()
            if row is None:
                return
            document = self.decrypt_document(row[0])
            if document["requestId"] != request_id or document["gatewayRevision"] != revision:
                raise ValueError("removal acknowledgement does not match")
            self._db.execute("UPDATE task_removal SET acknowledged=1 WHERE task_id=?", (task_id,))

    def get(self, task_id: int) -> dict | None:
        row = self._db.execute(
            "SELECT document FROM task_configuration WHERE task_id = ?", (task_id,)
        ).fetchone()
        return None if row is None else json.loads(self._cipher.decrypt(row[0]))

    def all(self) -> list[dict]:
        return [
            json.loads(self._cipher.decrypt(row[0]))
            for row in self._db.execute(
                "SELECT document FROM task_configuration ORDER BY task_id"
            ).fetchall()
        ]

    def receipt(self, request_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM mutation_receipt WHERE request_id = ?", (request_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def save(self, document: dict, request_id: str, fingerprint: str) -> None:
        task_id, revision = document["config"]["taskId"], document["revision"]
        encrypted = self._cipher.encrypt(json.dumps(document).encode())
        with self._db:
            self._db.execute(
                "INSERT INTO task_configuration VALUES (?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET revision=excluded.revision, "
                "document=excluded.document",
                (task_id, revision, encrypted),
            )
            self._db.execute(
                "INSERT INTO mutation_receipt VALUES (?, ?, ?, ?)",
                (request_id, fingerprint, task_id, revision),
            )

    def remove(self, task_id: int, revision: int, request_id: str, fingerprint: str) -> None:
        with self._db:
            previous = self.get(task_id)
            if previous is None or previous["revision"] != revision:
                raise ValueError("configuration changed before removal")
            config = previous["config"]
            document = {
                "schemaVersion": "1.0",
                "taskId": task_id,
                "gatewayRevision": revision + 1,
                "configVersion": config["configVersion"],
                "runId": config["runId"],
                "requestId": request_id,
                "platformManaged": previous.get("platformManaged", True),
                "removedAt": datetime.now(UTC).isoformat(),
            }
            self._db.execute(
                "INSERT INTO task_removal(task_id, document) VALUES (?, ?)",
                (task_id, self.encrypt_document(document)),
            )
            self._db.execute(
                "DELETE FROM task_configuration WHERE task_id = ? AND revision = ?",
                (task_id, revision),
            )
            self._db.execute(
                "INSERT INTO mutation_receipt VALUES (?, ?, ?, ?)",
                (request_id, fingerprint, task_id, revision),
            )

    def close(self) -> None:
        self._db.close()

    def encrypt_document(self, document: dict) -> bytes:
        return self._cipher.encrypt(json.dumps(document, ensure_ascii=False).encode())

    def decrypt_document(self, document: bytes) -> dict:
        return json.loads(self._cipher.decrypt(document))
