"""Live performance and latency benchmark for StatisticsInspector against Supabase."""

import os
import time
import pytest
from dotenv import load_dotenv

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.statistics.database_stats_inspector import (
    DatabaseStatsInspector,
)
from src.db_engine.inspectors.statistics.index_stats_inspector import (
    IndexStatsInspector,
)
from src.db_engine.inspectors.statistics.lock_stats_inspector import (
    LockStatsInspector,
)
from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)
from src.db_engine.inspectors.statistics.statistics_inspector import (
    StatisticsInspector,
)
from src.db_engine.inspectors.statistics.table_stats_inspector import (
    TableStatsInspector,
)

load_dotenv()


def _get_conn():
    return get_connection()


@pytest.mark.skipif(
    not (os.getenv("DB_HOST") or os.getenv("DATABASE_URL")),
    reason="Supabase database credentials not configured in .env",
)
def test_supabase_statistics_benchmark():
    """Profiles network connection time, individual stat sub-inspectors, and total snapshot latency."""

    print("\n" + "=" * 65)
    print("🚀 DBVoyager: Supabase Statistics Inspector Performance Profile")
    print("=" * 65)

    # 1. Connection Handshake Latency
    t0 = time.perf_counter()
    conn = _get_conn()
    conn.close()
    conn_time_ms = (time.perf_counter() - t0) * 1000
    print(f"🔌 Supabase Handshake Time : {conn_time_ms:.2f} ms")
    print("-" * 65)

    print(f"{'Inspector Component':<25} | {'Latency (ms)':<15} | {'Count'}")
    print("-" * 65)

    total_sub_ms = 0.0

    # 2. Query Stats Inspector
    t_start = time.perf_counter()
    q_stats = QueryStatsInspector(_get_conn).get_query_stats()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'QueryStatsInspector':<25} | {elapsed:>10.2f} ms     | {len(q_stats)} items")

    # 3. Table Stats Inspector
    t_start = time.perf_counter()
    t_stats = TableStatsInspector(_get_conn).get_table_stats()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'TableStatsInspector':<25} | {elapsed:>10.2f} ms     | {len(t_stats)} items")

    # 4. Index Stats Inspector
    t_start = time.perf_counter()
    i_stats = IndexStatsInspector(_get_conn).get_index_stats()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'IndexStatsInspector':<25} | {elapsed:>10.2f} ms     | {len(i_stats)} items")

    # 5. Lock Stats Inspector
    t_start = time.perf_counter()
    l_stats = LockStatsInspector(_get_conn).get_lock_stats()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'LockStatsInspector':<25} | {elapsed:>10.2f} ms     | {len(l_stats)} items")

    # 6. Database Stats Inspector
    t_start = time.perf_counter()
    d_stats = DatabaseStatsInspector(_get_conn).get_database_stats()
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'DatabaseStatsInspector':<25} | {elapsed:>10.2f} ms     | {len(d_stats)} items")

    print("-" * 65)

    # 7. Orchestrated StatisticsSnapshot Run
    t_full_start = time.perf_counter()
    full_inspector = StatisticsInspector(_get_conn)
    snapshot = full_inspector.get_snapshot()
    full_elapsed_ms = (time.perf_counter() - t_full_start) * 1000

    print(f"⚡ Cumulative Sequential Total  : {total_sub_ms:.2f} ms")
    print(f"🚀 Total StatisticsInspector Run : {full_elapsed_ms:.2f} ms ({full_elapsed_ms / 1000:.2f} s)")
    print("-" * 65)
    print(
        f"📊 Snapshot: {len(snapshot.query_stats)} query stats, "
        f"{len(snapshot.table_stats)} table stats, {len(snapshot.index_stats)} index stats, "
        f"{len(snapshot.lock_stats)} lock stats"
    )
    print("=" * 65)

    assert snapshot is not None


if __name__ == "__main__":
    test_supabase_statistics_benchmark()