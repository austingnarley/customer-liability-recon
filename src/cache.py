from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class ResponseCache:
    """Tiny SQLite-backed response cache keyed by request URL."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )

    def get(self, key: str) -> str | None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM responses WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            value, expires_at = row
            if expires_at < now:
                conn.execute("DELETE FROM responses WHERE key = ?", (key,))
                return None
            return str(value)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO responses (key, value, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at
                """,
                (key, value, expires_at),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)
