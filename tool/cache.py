"""Tiny TTL cache. Thread-safe enough for our single-writer-per-key use."""
import time
from threading import Lock


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value):
        with self._lock:
            self._store[key] = (time.monotonic() + self.ttl, value)

    def invalidate(self, key: str | None = None):
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
