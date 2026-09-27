"""Small durable store. Single process/replica, serialized short transactions.

Rollback journal is deliberate: no dependence on a host's WAL patch level.
Never call a model/network while holding transaction().
"""
from contextlib import contextmanager
import json
import sqlite3
import threading
import time
from typing import Any, Iterator
from .config import Settings

TABLES = ("contexts", "conversations", "recipients", "suppression", "replies", "receipts", "traces", "semantic", "meta")


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Store:
    def __init__(self, settings: Settings):
        settings.ensure_parent()
        self.lock = threading.RLock()
        self.retention_seconds = settings.retention_hours * 3600
        self.conn = sqlite3.connect(settings.db_path, timeout=4, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA secure_delete=ON")
        self.conn.execute("PRAGMA busy_timeout=4000")
        for table in TABLES:
            self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._expire_if_needed()

    def _expire_if_needed(self) -> None:
        last = self.get("meta", "last_activity")
        if last is not None and time.time() - float(last) > self.retention_seconds:
            self.wipe()

    @contextmanager
    def transaction(self) -> Iterator["Store"]:
        with self.lock:
            self._expire_if_needed()
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self
                self.put("meta", "last_activity", time.time())
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def get(self, table: str, key: str, default: Any = None) -> Any:
        assert table in TABLES
        row = self.conn.execute(f"SELECT value FROM {table} WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, table: str, key: str, value: Any) -> None:
        assert table in TABLES
        self.conn.execute(f"INSERT INTO {table}(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, canonical(value)))

    def items(self, table: str) -> list[tuple[str, Any]]:
        assert table in TABLES
        return [(k, json.loads(v)) for k, v in self.conn.execute(f"SELECT key,value FROM {table} ORDER BY key")]

    def keys(self, table: str) -> list[str]:
        assert table in TABLES
        return [row[0] for row in self.conn.execute(f"SELECT key FROM {table} ORDER BY key")]

    def size(self, table: str) -> int:
        assert table in TABLES
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def delete(self, table: str, key: str) -> None:
        assert table in TABLES
        self.conn.execute(f"DELETE FROM {table} WHERE key=?", (key,))

    def wipe(self) -> None:
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for table in TABLES:
                    self.conn.execute(f"DELETE FROM {table}")
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.conn.execute("VACUUM")

    def close(self) -> None:
        with self.lock:
            self.conn.close()


def context_key(scope: str, cid: str) -> str:
    return canonical([scope, cid])


def recipient_key(mid: str, cid: str | None) -> str:
    return canonical([mid, cid])
