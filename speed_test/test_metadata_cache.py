"""Unit tests for the MetadataTTLCache thread-safe in-memory cache."""

import time
from unittest.mock import MagicMock
from src.db_engine.cache.metadata_cache import MetadataTTLCache


def test_cache_hit_and_miss():
    cache = MetadataTTLCache(default_ttl_seconds=30.0)
    fetch_fn = MagicMock(return_value={"tables": ["users", "orders"]})

    # 1. First call -> Cache miss, executes fetch_fn
    data1 = cache.get_or_compute(key="test_key", fetch_fn=fetch_fn)
    assert data1 == {"tables": ["users", "orders"]}
    assert fetch_fn.call_count == 1

    # 2. Second call within TTL -> Cache hit, skips fetch_fn
    data2 = cache.get_or_compute(key="test_key", fetch_fn=fetch_fn)
    assert data2 == {"tables": ["users", "orders"]}
    assert fetch_fn.call_count == 1  # Still 1


def test_cache_ttl_expiration():
    # Set short TTL of 0.1s for testing
    cache = MetadataTTLCache(default_ttl_seconds=0.1)
    fetch_fn = MagicMock(side_effect=[100, 200])

    val1 = cache.get_or_compute(key="short_ttl", fetch_fn=fetch_fn)
    assert val1 == 100

    # Sleep past the TTL
    time.sleep(0.15)

    # Cache should be expired -> re-computes fetch_fn
    val2 = cache.get_or_compute(key="short_ttl", fetch_fn=fetch_fn)
    assert val2 == 200
    assert fetch_fn.call_count == 2


def test_cache_invalidation():
    cache = MetadataTTLCache(default_ttl_seconds=30.0)
    fetch_fn = MagicMock(return_value="data")

    cache.get_or_compute(key="k1", fetch_fn=fetch_fn)
    cache.get_or_compute(key="k2", fetch_fn=fetch_fn)

    # Invalidate specific key
    cache.invalidate("k1")
    cache.get_or_compute(key="k1", fetch_fn=fetch_fn)
    assert fetch_fn.call_count == 3  # Initial k1, initial k2, re-fetched k1

    # Invalidate all keys
    cache.invalidate()
    cache.get_or_compute(key="k2", fetch_fn=fetch_fn)
    assert fetch_fn.call_count == 4