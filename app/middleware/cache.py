import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings


@dataclass
class CacheEntry:
    """Cache entry with TTL support for in-memory backend."""

    data: Any
    timestamp: float
    ttl: int

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() - self.timestamp > self.ttl


class SimpleCache:
    """Simple in-memory cache with TTL support."""

    def __init__(self, default_ttl: int = 60):
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None

        if entry.is_expired():
            del self._cache[key]
            return None

        return entry.data

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        ttl = ttl or self._default_ttl
        self._cache[key] = CacheEntry(
            data=value,
            timestamp=time.time(),
            ttl=ttl,
        )

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def size(self) -> int:
        """Get number of items in cache."""
        return len(self._cache)


class SQLiteCache:
    """SQLite-backed shared cache for multi-worker deployments."""

    def __init__(self, db_path: str, default_ttl: int = 60, cleanup_every: int = 200):
        self._db_path = db_path
        self._default_ttl = default_ttl
        self._cleanup_every = cleanup_every
        self._writes_since_cleanup = 0
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        db_parent = Path(self._db_path).parent
        db_parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  expires_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cache_expires_at
                ON cache_entries(expires_at);
                """
            )
            conn.commit()

    def get(self, key: str) -> Optional[Any]:
        """Get value from SQLite cache if present and not expired."""
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache_entries WHERE key = ?",
                (key,),
            ).fetchone()

            if row is None:
                return None

            value_json, expires_at = row
            if expires_at <= now:
                conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                conn.commit()
                return None

            return json.loads(value_json)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in SQLite cache with TTL."""
        ttl = ttl or self._default_ttl
        expires_at = int(time.time()) + int(ttl)
        value_json = json.dumps(value)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache_entries(key, value, expires_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    expires_at=excluded.expires_at
                """,
                (key, value_json, expires_at),
            )
            conn.commit()

        self._writes_since_cleanup += 1
        if self._writes_since_cleanup >= self._cleanup_every:
            self.cleanup_expired()
            self._writes_since_cleanup = 0

    def delete(self, key: str) -> None:
        """Delete key from SQLite cache."""
        with self._connect() as conn:
            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            conn.commit()

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._connect() as conn:
            conn.execute("DELETE FROM cache_entries")
            conn.commit()

    def size(self) -> int:
        """Get number of items in cache table."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM cache_entries").fetchone()
            return int(row[0]) if row else 0

    def cleanup_expired(self) -> int:
        """Remove expired entries and return removed count."""
        now = int(time.time())
        with self._connect() as conn:
            before = conn.total_changes
            conn.execute("DELETE FROM cache_entries WHERE expires_at <= ?", (now,))
            conn.commit()
            after = conn.total_changes
        return max(0, after - before)


def _build_cache_backend() -> Any:
    # Force SQLite as the single cache backend so caches are shared
    # across workers and users.
    settings.cache_backend = "sqlite"
    return SQLiteCache(
        db_path=settings.cache_sqlite_path,
        default_ttl=settings.cache_ttl_seconds,
    )


# Global cache instance
cache = _build_cache_backend()
