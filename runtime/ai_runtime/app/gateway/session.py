"""Durable, revocable local sessions; only token hashes are stored on disk."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

SESSION_TTL = 30 * 24 * 3600
RENEW_INTERVAL = 24 * 3600


class GatewaySessions:
    def __init__(self, root: Path):
        self.path = root / "local-sessions.sqlite3"
        descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS session "
                "(token_hash TEXT PRIMARY KEY, expires REAL NOT NULL, digest BLOB NOT NULL)"
            )

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, digest: bytes, previous: str = "") -> str:
        token = secrets.token_urlsafe(32)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "DELETE FROM session WHERE expires <= ? OR digest != ? OR token_hash = ?",
                (time.time(), digest, self.token_hash(previous)),
            )
            if connection.execute("SELECT COUNT(*) FROM session").fetchone()[0] >= 64:
                raise ValueError("登录会话已满")
            connection.execute(
                "INSERT INTO session VALUES (?, ?, ?)",
                (self.token_hash(token), time.time() + SESSION_TTL, digest),
            )
        return token

    def validate(self, token: str, digest: bytes) -> tuple[bool, bool]:
        """Return authentication and cookie-renewal flags; renew at most once a day."""
        if not token or len(token) > 128:
            return False, False
        key = self.token_hash(token)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "SELECT expires, digest FROM session WHERE token_hash = ?", (key,)
            ).fetchone()
            if row is None:
                return False, False
            if row[0] <= time.time() or not hmac.compare_digest(row[1], digest):
                connection.execute("DELETE FROM session WHERE token_hash = ?", (key,))
                return False, False
            renew = row[0] <= time.time() + SESSION_TTL - RENEW_INTERVAL
            if renew:
                connection.execute(
                    "UPDATE session SET expires = ? WHERE token_hash = ?",
                    (time.time() + SESSION_TTL, key),
                )
            return True, renew

    def revoke(self, token: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "DELETE FROM session WHERE token_hash = ?", (self.token_hash(token),)
            )
