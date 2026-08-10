"""Integration and mock tests for SchemaInspector and StatisticsInspector caching behavior."""

import time
from unittest.mock import MagicMock, patch
from src.db_engine.cache.metadata_cache import metadata_cache
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.statistics.statistics_inspector import (
    StatisticsInspector,
)
from src.models.schema.schema_model import DatabaseSchema
from src.models.statistics.database_stats_model import DatabaseStats
from src.models.statistics.statistics_snapshot_model import StatisticsSnapshot


def test_schema_inspector_uses_cache():
    metadata_cache.invalidate()
    mock_conn = MagicMock()
    inspector = SchemaInspector(connection_provider=lambda: mock_conn)

    dummy_schema = DatabaseSchema(
        tables=[], columns=[], primary_keys=[], foreign_keys=[], indexes=[], relations=[]
    )

    with patch.object(
        inspector, "_inspect_from_db", return_value=dummy_schema
    ) as mock_db_inspect:
        res1 = inspector.inspect(use_cache=True, cache_key="schema_test")
        assert res1 == dummy_schema
        assert mock_db_inspect.call_count == 1

        res2 = inspector.inspect(use_cache=True, cache_key="schema_test")
        assert res2 == dummy_schema
        assert mock_db_inspect.call_count == 1

        res3 = inspector.inspect(use_cache=False, cache_key="schema_test")
        assert res3 == dummy_schema
        assert mock_db_inspect.call_count == 2


def test_statistics_inspector_uses_cache():
    metadata_cache.invalidate()
    mock_conn = MagicMock()
    inspector = StatisticsInspector(connection_provider=lambda: mock_conn)

    dummy_db_stats = DatabaseStats(
        database_name="test_db",
        num_connections=3,
        database_size_mb=10.0,
        cache_hit_ratio=99.5,
    )

    dummy_snapshot = StatisticsSnapshot(
        query_stats=[],
        table_stats=[],
        index_stats=[],
        lock_stats=[],
        database_stats=dummy_db_stats,
    )

    with patch.object(
        inspector, "_get_snapshot_from_db", return_value=dummy_snapshot
    ) as mock_db_stats:
        res1 = inspector.get_snapshot(use_cache=True, cache_key="stats_test")
        assert res1 == dummy_snapshot
        assert mock_db_stats.call_count == 1

        res2 = inspector.get_snapshot(use_cache=True, cache_key="stats_test")
        assert res2 == dummy_snapshot
        assert mock_db_stats.call_count == 1


def test_real_timing_latency_difference():
    """Verify that a cached lookup is significantly faster than simulated network latency."""
    metadata_cache.invalidate()
    mock_conn = MagicMock()
    inspector = SchemaInspector(connection_provider=lambda: mock_conn)

    def slow_db_fetch(progress=None):
        time.sleep(0.05)  # Simulate 50ms network call
        return DatabaseSchema(
            tables=[], columns=[], primary_keys=[], foreign_keys=[], indexes=[], relations=[]
        )

    with patch.object(inspector, "_inspect_from_db", side_effect=slow_db_fetch):
        t0 = time.perf_counter()
        inspector.inspect(use_cache=True, cache_key="timing_test")
        miss_latency_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        inspector.inspect(use_cache=True, cache_key="timing_test")
        hit_latency_ms = (time.perf_counter() - t0) * 1000

        assert miss_latency_ms >= 50.0
        assert hit_latency_ms < 2.0  # RAM read executes in sub-millisecond time