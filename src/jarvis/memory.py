"""Persistent conversation memory backed by SQLite.

Each Jarvis process attaches to a single "active" session. All chat messages
are appended verbatim (as JSON payloads) so the brain can rehydrate the exact
tool-calling structure the model expects.

The store is intentionally tiny: one row per message, one row per session. A
rolling-summary strategy can be added later without changing the schema.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading as _threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    created_at TEXT NOT NULL,
    role TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Memory:
    """SQLite-backed message log with a single active session.

    The connection is shared across threads because the voice-mode pipeline
    writes from a worker thread while the main thread handles input. A
    lock serialises every access so the shared connection stays consistent.
    """

    def __init__(self, path: str | Path) -> None:
        raw = str(path)
        self._in_memory = raw == ":memory:"
        if not self._in_memory:
            resolved = Path(raw).expanduser()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            raw = str(resolved)
        self._path = raw
        self._lock = _threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys=ON")
        if not self._in_memory:
            self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
        self._session_id = self._ensure_active_session()

    @property
    def path(self) -> str:
        return self._path

    @property
    def session_id(self) -> int:
        return self._session_id

    def _ensure_active_session(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is not None:
            return int(row[0])
        return self._start_session()

    def _start_session(self) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO sessions(started_at) VALUES(?)", (_utcnow(),)
            )
            return int(cur.lastrowid)

    def load(self) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT payload FROM messages WHERE session_id=? ORDER BY id",
                (self._session_id,),
            )
            rows = cur.fetchall()
        return [json.loads(row[0]) for row in rows]

    def append(self, message: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO messages(session_id, created_at, role, payload) "
                "VALUES(?,?,?,?)",
                (
                    self._session_id,
                    _utcnow(),
                    str(message.get("role", "")),
                    json.dumps(message, ensure_ascii=False),
                ),
            )

    def reset(self) -> int:
        """Close the current session and open a fresh one. Returns the new id."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE sessions SET ended_at=? WHERE id=?",
                (_utcnow(), self._session_id),
            )
        self._session_id = self._start_session()
        return self._session_id

    def visible_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent user/assistant turns for display (newest last)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT payload FROM messages WHERE session_id=? "
                "AND role IN ('user','assistant') ORDER BY id DESC LIMIT ?",
                (self._session_id, max(1, limit)),
            )
            rows = list(reversed(cur.fetchall()))
        return [json.loads(row[0]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
