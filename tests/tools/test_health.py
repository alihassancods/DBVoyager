"""Checks for the plain result.txt health entries."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.health import audit_connection


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""
        self.closed = False

    def execute(self, query: str) -> None:
        self.query = query

    def fetchall(self) -> list[tuple[object, ...]]:
        if "pg_stat_user_tables" in self.query:
            return [("events", 50_000, None, None)]
        if "pg_settings" in self.query:
            return [
                ("shared_buffers", "128MB", "8kB"),
                ("work_mem", "4MB", "kB"),
                ("effective_cache_size", "4GB", "8kB"),
                ("statement_timeout", "0", "ms"),
                ("idle_in_transaction_session_timeout", "0", "ms"),
                ("ssl", "on", None),
                ("log_min_duration_statement", "-1", "ms"),
            ]
        return []

    def fetchone(self) -> tuple[object, ...] | None:
        if "max_connections" in self.query:
            return (90, 100)
        if "pg_stat_bgwriter" in self.query:
            return (100, 50, 2000)
        if "pg_stat_archiver" in self.query:
            return (10, 0, None, None)
        return None

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_audit_connection_reuses_snapshots_and_returns_plain_entries() -> None:
    snapshot = SimpleNamespace(
        database_stats=SimpleNamespace(database_size_mb=100.0, cache_hit_ratio=95.0),
        query_stats=[SimpleNamespace(query="SELECT * FROM orders", mean_exec_time=120.0, calls=1_500)],
        table_stats=[SimpleNamespace(table_name="orders", n_live_tup=100_000, n_dead_tup=30_000, seq_scan=200, idx_scan=10)],
        index_stats=[SimpleNamespace(table_name="orders", index_name="orders_old_idx", idx_scan=0)],
        lock_stats=[SimpleNamespace(pid=42, mode="ExclusiveLock", relation="orders", granted=False)],
    )
    schema = SimpleNamespace(
        tables=[SimpleNamespace(table_name="orders", schema_name="public", table_type="BASE TABLE")],
        primary_keys=[],
        foreign_keys=[SimpleNamespace(source_table="orders", source_column="customer_id")],
        indexes=[SimpleNamespace(table_name="orders", index_name="orders_customer_a", indexed_columns=["customer_id"]), SimpleNamespace(table_name="orders", index_name="orders_customer_b", indexed_columns=["customer_id"])],
    )
    connection = FakeConnection()

    findings = audit_connection(connection, snapshot, schema)

    assert all(isinstance(finding, dict) and "check" in finding for finding in findings)
    assert {finding["check"] for finding in findings} >= {
        "database_size", "slow_queries", "frequent_queries", "table_bloat",
        "missing_indexes", "unused_indexes", "locks", "primary_keys",
        "duplicate_indexes", "autovacuum_analyze", "connections", "wal_checkpoints",
    }
    assert connection.cursor_instance.closed is True
