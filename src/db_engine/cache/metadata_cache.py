"""In-memory TTL cache for database schema and statistics metadata."""

import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class MetadataTTLCache:
    """Thread-safe in-memory TTL cache for schema and statistics snapshots."""

    def __init__(self, default_ttl_seconds: float = 30.0) -> None:
        self._default_ttl = default_ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    def get_or_compute(
        self, key: str, fetch_fn: Callable[[], T], ttl_seconds: float | None = None
    ) -> T:
        """Return cached object if fresh; otherwise execute fetch_fn and cache result."""
        now = time.monotonic()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl

        if key in self._cache:
            timestamp, cached_data = self._cache[key]
            if now - timestamp < ttl:
                return cached_data

        fresh_data = fetch_fn()
        self._cache[key] = (now, fresh_data)
        return fresh_data

    def invalidate(self, key: str | None = None) -> None:
        """Invalidate a specific key or purge all cached snapshots."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


# Global singleton instance
metadata_cache = MetadataTTLCache(default_ttl_seconds=30.0)