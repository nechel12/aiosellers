"""Durable key/value state for listeners."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StateStore(Protocol):
    """Minimal async storage for cursors and dedup windows."""

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def close(self) -> None: ...


class MemoryStateStore:
    """Process-local store. Values go through JSON, like :class:`SQLiteStateStore`."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def get(self, key: str) -> Any | None:
        raw = self._values.get(key)
        return None if raw is None else json.loads(raw)

    async def set(self, key: str, value: Any) -> None:
        self._values[key] = _encode(value)

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)

    async def close(self) -> None:
        self._values.clear()


class SQLiteStateStore:
    """SQLite-backed store that survives process restarts.

    One connection is guarded by a lock; queries run in worker threads so a
    slow disk does not block the event loop.
    """

    def __init__(self, path: str | Path) -> None:
        raw_path = str(path)
        self.path = raw_path if raw_path == ":memory:" else str(Path(raw_path).expanduser())
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS state ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        self._conn.commit()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            raw = await asyncio.to_thread(self._read, key)
        return None if raw is None else json.loads(raw)

    async def set(self, key: str, value: Any) -> None:
        payload = _encode(value)
        async with self._lock:
            await asyncio.to_thread(self._write, key, payload)

    async def delete(self, key: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._remove, key)

    async def close(self) -> None:
        async with self._lock:
            conn, self._conn = self._conn, None
            if conn is not None:
                await asyncio.to_thread(conn.close)

    def _read(self, key: str) -> str | None:
        row = self._connection().execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return None if row is None else row[0]

    def _write(self, key: str, payload: str) -> None:
        conn = self._connection()
        conn.execute(
            "INSERT INTO state (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, payload, time.time()),
        )
        conn.commit()

    def _remove(self, key: str) -> None:
        conn = self._connection()
        conn.execute("DELETE FROM state WHERE key = ?", (key,))
        conn.commit()

    def _connection(self) -> sqlite3.Connection:
        conn = self._conn
        if conn is None:
            raise RuntimeError("State store is closed")
        return conn


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
