"""Device-owned configuration journal; secrets never appear in SQLite plaintext."""

import json
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet


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

    def close(self) -> None:
        self._db.close()
