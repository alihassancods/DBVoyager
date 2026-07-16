"""Unit tests for the reusable health-audit interfaces."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import health


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False

    def execute(self, query: str, _parameters: object = None) -> None:
        self.executed.append(query)

    def fetchall(self) -> list[tuple[object, ...]]:
        query = self.executed[-1]
        if "pg_stat_statements" in query:
            return [("SELECT * FROM orders WHERE customer_id = 1", 125.5)]
        if "dead_tuple_ratio" in query:
            return [("orders", 800, 300, 0.2727)]
        if "wait_event_type = 'Lock'" in query:
            return [(42, "demo", "app", "transactionid", "00:01:10")]
        if "state = 'active'" in query:
            return [(43, "demo", "app", "00:10:00", "SELECT * FROM orders")]
        if "idle in transaction" in query:
            return [(44, "demo", "app", "00:08:00")]
        if "last_autovacuum" in query:
            return [("events", 50_000, None)]
        if "pg_stat_user_indexes" in query:
            return [("public", "orders", "orders_old_idx", 0, 20_000_000)]
        if "seq_tup_read" in query:
            return [("orders", 200, 500_000, 300_000)]
        if "pg_blocking_pids" in query:
            return [(45, "api", 46, "worker", "00:02:00")]
        if "pg_statio_user_tables" in query:
            return [("public", "orders", 100_000_000, "95 MB")]
        if "table_constraints" in query:
            return [("public", "orders"), ("public", "products")]
        if "constraint_type = 'FOREIGN KEY'" in query:
            return [("public", "order_items", "order_id", "orders", "id")]
        if "age(datfrozenxid)" in query:
            return [("postgres", 500_000_000, 75.0)]
        if "pg_index" in query and "indisprimary" in query:
            return [
                ("orders", "orders_pkey", "CREATE INDEX orders_pkey ON orders USING btree (id)"),
                ("orders", "idx_orders_customer", "CREATE INDEX idx_orders_customer ON orders USING btree (customer_id)"),
            ]
        if "pg_stat_bgwriter" in query:
            return [(100, 50, 500000, 30000, 2000)]
        if "pg_is_in_recovery" in query:
            return [("primary", 0)]
        if "temp_blks_written" in query:
            return [("SELECT * FROM large_table", 5, 12000.0, 512)]
        if "pg_settings" in query:
            return [
                ("statement_timeout", "0", "ms", "Sets the maximum allowed duration of each statement."),
                ("idle_in_transaction_session_timeout", "0", "ms", "Sets the maximum allowed duration of each idle-in-transaction session."),
            ]
        if "state = 'idle'" in query:
            return [(99, "postgres", "app", "idle", 7200, "SELECT 1")]
        return []

    def fetchone(self) -> object:
        query = self.executed[-1]
        if query.startswith("EXPLAIN"):
            return ([{"Plan": {
                "Node Type": "Nested Loop", "Plan Rows": 200_000,
                "Plans": [
                    {"Node Type": "Seq Scan", "Relation Name": "orders"},
                    {"Node Type": "Sort", "Plan Rows": 200_000},
                ],
            }}],)
        if "pg_class" in query:
            return (250_000,)
        if "current_setting('max_connections')" in query:
            return (90, 100)
        if "sum(blks_hit)" in query:
            return (0.95,)
        if "pg_database_size" in query:
            return (1_000_000_000, "954 MB")
        if "pg_index" in query and "pg_get_indexdef" in query:
            return None  # covered by fetchall
        return None

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
        self.closed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_audit_connection_returns_all_finding_categories_and_keeps_connection_open() -> None:
    connection = FakeConnection()

    findings = health.audit_connection(connection)

    assert {finding.category for finding in findings} == {
        "slow_query", "query_plan", "missing_index", "lock", "long_running_query",
        "idle_transaction", "bloat", "autovacuum", "connection_utilization",
        "cache_hit_ratio", "index_usage", "sequential_scan", "blocking_process",
        "database_size", "table_size",
        # New
        "missing_primary_key", "missing_fk_index", "wraparound_age",
        "redundant_index", "checkpoint_frequency", "replication_lag",
        "temp_spilling", "timeout_config", "idle_timeout",
    }
    assert connection.closed is False
    assert connection.cursor_instance.closed is True


def test_sync_audit_uses_injected_connection_factory_and_closes_connection() -> None:
    connection = FakeConnection()

    findings = health.run_health_audit_sync("test_database", connection_factory=lambda _: connection)

    assert len(findings) == 25  # was 16, now includes 9 new checks
    assert connection.closed is True


def test_async_agent_wrapper_returns_json_serializable_dictionaries(monkeypatch: object) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        health,
        "run_health_audit_sync",
        lambda _database: health.audit_connection(connection),
    )

    result = asyncio.run(health.run_health_audit("test_database"))

    assert result[0]["category"] == "slow_query"
    assert any(finding["severity"] == "critical" for finding in result)


def test_plan_analysis_skips_multi_statement_queries() -> None:
    connection = FakeConnection()

    findings = health._scan_query_plan(connection, connection.cursor(), "SELECT 1; SELECT 2", 1.0)

    assert findings == []
