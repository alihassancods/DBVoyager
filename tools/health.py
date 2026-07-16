"""PostgreSQL health-audit tool for identifying actionable performance risks."""

import argparse
import asyncio
import json
import logging
import os
from collections.abc import Iterable
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from src.db_engine.connection import get_connection


logger = logging.getLogger(__name__)

TOP_STATEMENTS_SQL = """
    SELECT query, mean_exec_time
    FROM pg_stat_statements
    WHERE query NOT ILIKE 'EXPLAIN %'
    ORDER BY mean_exec_time DESC
    LIMIT 10
"""

BLOATED_TABLES_SQL = """
    SELECT relname,
           n_live_tup,
           n_dead_tup,
           n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) AS dead_tuple_ratio
    FROM pg_stat_user_tables
    WHERE n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) > 0.2
    ORDER BY dead_tuple_ratio DESC
"""

LOCK_WAITS_SQL = """
    SELECT pid,
           datname,
           usename,
           wait_event,
           now() - query_start AS wait_duration
    FROM pg_stat_activity
    WHERE wait_event_type = 'Lock'
      AND state <> 'idle'
    ORDER BY query_start
"""

LONG_RUNNING_QUERIES_SQL = """
    SELECT pid, datname, usename, now() - query_start AS duration, query
    FROM pg_stat_activity
    WHERE state = 'active' AND query_start IS NOT NULL
      AND now() - query_start > interval '5 minutes'
      AND pid <> pg_backend_pid()
    ORDER BY query_start
"""

IDLE_IN_TRANSACTION_SQL = """
    SELECT pid, datname, usename, now() - state_change AS idle_duration
    FROM pg_stat_activity
    WHERE state = 'idle in transaction'
      AND now() - state_change > interval '5 minutes'
    ORDER BY state_change
"""

AUTOVACUUM_SQL = """
    SELECT relname, n_dead_tup, last_autovacuum
    FROM pg_stat_user_tables
    WHERE n_dead_tup > 10000
      AND (last_autovacuum IS NULL OR last_autovacuum < now() - interval '7 days')
    ORDER BY n_dead_tup DESC
"""

CONNECTION_UTILIZATION_SQL = """
    SELECT count(*) AS current_connections,
           current_setting('max_connections')::integer AS max_connections
    FROM pg_stat_activity
"""

CACHE_HIT_RATIO_SQL = """
    SELECT sum(blks_hit)::numeric / NULLIF(sum(blks_hit) + sum(blks_read), 0) AS cache_hit_ratio
    FROM pg_stat_database
    WHERE datname = current_database()
"""

UNUSED_INDEXES_SQL = """
    SELECT schemaname, relname, indexrelname, idx_scan, pg_relation_size(indexrelid) AS index_size
    FROM pg_stat_user_indexes
    WHERE idx_scan = 0
      AND indexrelname NOT LIKE '%_pkey'
      AND pg_relation_size(indexrelid) > 10 * 1024 * 1024
    ORDER BY pg_relation_size(indexrelid) DESC
"""

SEQUENTIAL_SCAN_STATS_SQL = """
    SELECT relname, seq_scan, seq_tup_read, n_live_tup
    FROM pg_stat_user_tables
    WHERE seq_scan > 100
      AND seq_tup_read > 100000
    ORDER BY seq_tup_read DESC
"""

BLOCKING_GRAPH_SQL = """
    SELECT blocked.pid AS blocked_pid, blocked.usename AS blocked_user,
           blocker.pid AS blocking_pid, blocker.usename AS blocking_user,
           now() - blocked.query_start AS wait_duration
    FROM pg_stat_activity AS blocked
    CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
    JOIN pg_stat_activity AS blocker ON blocker.pid = blocking_pid.pid
    ORDER BY blocked.query_start
"""

DATABASE_SIZE_SQL = """
    SELECT pg_database_size(current_database()) AS database_size,
           pg_size_pretty(pg_database_size(current_database())) AS database_size_pretty
"""

TABLE_SIZE_RANKING_SQL = """
    SELECT schemaname, relname, pg_total_relation_size(relid) AS total_size,
           pg_size_pretty(pg_total_relation_size(relid)) AS total_size_pretty
    FROM pg_statio_user_tables
    ORDER BY pg_total_relation_size(relid) DESC
    LIMIT 10
"""


class HealthFinding(BaseModel):
    """A single actionable observation produced by the health audit."""

    severity: Literal["critical", "warning", "info"]
    category: Literal[
        "slow_query",
        "query_plan",
        "missing_index",
        "lock",
        "long_running_query",
        "idle_transaction",
        "bloat",
        "autovacuum",
        "connection_utilization",
        "cache_hit_ratio",
        "index_usage",
        "sequential_scan",
        "blocking_process",
        "database_size",
        "table_size",
    ]
    title: str
    description: str
    suggested_fix: str


def _as_mapping(row: object, columns: tuple[str, ...]) -> dict[str, object]:
    """Normalize tuple- and mapping-based cursor rows for internal processing."""
    if isinstance(row, dict):
        return row
    if isinstance(row, tuple):
        return dict(zip(columns, row, strict=True))
    raise TypeError(f"Unsupported database row type: {type(row).__name__}")


def _find_seq_scans(plan: object) -> Iterable[dict[str, object]]:
    """Yield sequential-scan plan nodes from PostgreSQL's nested JSON plan."""
    if isinstance(plan, dict):
        if plan.get("Node Type") == "Seq Scan":
            yield plan
        for value in plan.values():
            yield from _find_seq_scans(value)
    elif isinstance(plan, list):
        for item in plan:
            yield from _find_seq_scans(item)


def _find_plan_nodes(plan: object, node_type: str) -> Iterable[dict[str, object]]:
    """Yield nodes of one type from a nested PostgreSQL JSON execution plan."""
    if isinstance(plan, dict):
        if plan.get("Node Type") == node_type:
            yield plan
        for value in plan.values():
            yield from _find_plan_nodes(value, node_type)
    elif isinstance(plan, list):
        for item in plan:
            yield from _find_plan_nodes(item, node_type)


def _table_row_estimate(cursor: object, relation: str) -> int:
    """Return PostgreSQL's estimated row count for a relation, or zero if unknown."""
    cursor.execute(
        "SELECT COALESCE(reltuples, 0)::bigint FROM pg_class WHERE oid = to_regclass(%s)",
        (relation,),
    )
    row = cursor.fetchone()
    return int(row[0]) if row is not None else 0


def _scan_query_plan(
    connection: object,
    cursor: object,
    query: str,
    mean_exec_time: float,
) -> list[HealthFinding]:
    """Analyze a statement plan and report sequential scans on large relations."""
    statement = query.strip().rstrip(";")
    if not statement or ";" in statement:
        logger.info("Skipping multi-statement pg_stat_statements entry")
        return []

    try:
        cursor.execute(f"EXPLAIN (FORMAT JSON, ANALYZE FALSE) {statement}")
        explain_row = cursor.fetchone()
    except Exception as error:
        connection.rollback()
        logger.info("Skipping plan analysis for pg_stat_statements entry: %s", error)
        return []

    if explain_row is None:
        return []

    findings: list[HealthFinding] = []
    plan = explain_row[0]
    for node in _find_seq_scans(plan):
        table_name = str(node.get("Relation Name", "unknown table"))
        schema_name = node.get("Schema")
        relation = f"{schema_name}.{table_name}" if schema_name else table_name
        row_estimate = _table_row_estimate(cursor, relation)
        if row_estimate <= 100_000:
            continue
        findings.append(
            HealthFinding(
                severity="warning",
                category="missing_index",
                title=f"Sequential scan on large table {relation}",
                description=(
                    f"A query averaging {mean_exec_time:.2f} ms performs a sequential "
                    f"scan on {relation}, which has an estimated {row_estimate:,} rows."
                ),
                suggested_fix=(
                    "Review the query predicates and run EXPLAIN ANALYZE; create an "
                    "appropriate index only when it improves the observed plan."
                ),
            )
        )
    for node in _find_plan_nodes(plan, "Sort"):
        rows = int(node.get("Plan Rows", 0))
        if rows >= 100_000:
            findings.append(
                HealthFinding(
                    severity="warning",
                    category="query_plan",
                    title="Expensive sort in execution plan",
                    description=(
                        f"A query averaging {mean_exec_time:.2f} ms sorts an estimated "
                        f"{rows:,} rows."
                    ),
                    suggested_fix="Check whether an index can satisfy the ORDER BY or reduce rows before sorting.",
                )
            )
    for node in _find_plan_nodes(plan, "Nested Loop"):
        rows = int(node.get("Plan Rows", 0))
        if rows >= 100_000:
            findings.append(
                HealthFinding(
                    severity="warning",
                    category="query_plan",
                    title="Large nested-loop join in execution plan",
                    description=f"A nested-loop join is estimated to produce {rows:,} rows.",
                    suggested_fix="Review join predicates, table statistics, and indexes on join keys.",
                )
            )
    return findings


def audit_connection(connection: object) -> list[HealthFinding]:
    """Audit an already-open PostgreSQL connection.

    This is the most useful entry point for tests and custom scripts that manage
    their own connection lifecycle.  The supplied connection remains open when
    this function returns.
    """
    cursor = connection.cursor()
    try:
        findings: list[HealthFinding] = []

        cursor.execute(TOP_STATEMENTS_SQL)
        for row in cursor.fetchall():
            statement = _as_mapping(row, ("query", "mean_exec_time"))
            query = str(statement["query"])
            mean_exec_time = float(statement["mean_exec_time"])
            findings.append(
                HealthFinding(
                    severity="warning",
                    category="slow_query",
                    title="High mean execution time query",
                    description=f"This statement averages {mean_exec_time:.2f} ms per execution.",
                    suggested_fix="Inspect its execution plan and reduce unnecessary I/O or row processing.",
                )
            )
            findings.extend(_scan_query_plan(connection, cursor, query, mean_exec_time))

        cursor.execute(BLOATED_TABLES_SQL)
        for row in cursor.fetchall():
            table = _as_mapping(row, ("relname", "n_live_tup", "n_dead_tup", "dead_tuple_ratio"))
            ratio = float(table["dead_tuple_ratio"])
            findings.append(
                HealthFinding(
                    severity="warning",
                    category="bloat",
                    title=f"High dead tuple ratio on {table['relname']}",
                    description=(
                        f"{table['relname']} has {int(table['n_dead_tup']):,} dead tuples "
                        f"({ratio:.1%} of estimated tuples)."
                    ),
                    suggested_fix="Run VACUUM (ANALYZE) and review autovacuum thresholds for this table.",
                )
            )

        cursor.execute(LOCK_WAITS_SQL)
        for row in cursor.fetchall():
            lock = _as_mapping(row, ("pid", "datname", "usename", "wait_event", "wait_duration"))
            findings.append(
                HealthFinding(
                    severity="critical",
                    category="lock",
                    title=f"Session {lock['pid']} is waiting on a lock",
                    description=(
                        f"User {lock['usename']} in database {lock['datname']} has waited "
                        f"{lock['wait_duration']} for {lock['wait_event']}."
                    ),
                    suggested_fix="Identify the blocking session and end or optimize the blocking transaction.",
                )
            )

        cursor.execute(LONG_RUNNING_QUERIES_SQL)
        for row in cursor.fetchall():
            query = _as_mapping(row, ("pid", "datname", "usename", "duration", "query"))
            findings.append(HealthFinding(
                severity="warning", category="long_running_query",
                title=f"Long-running query in session {query['pid']}",
                description=f"User {query['usename']} has run a query for {query['duration']}.",
                suggested_fix="Inspect the query plan, cancel runaway work, or move batch work off peak hours.",
            ))

        cursor.execute(IDLE_IN_TRANSACTION_SQL)
        for row in cursor.fetchall():
            session = _as_mapping(row, ("pid", "datname", "usename", "idle_duration"))
            findings.append(HealthFinding(
                severity="warning", category="idle_transaction",
                title=f"Session {session['pid']} is idle in transaction",
                description=f"User {session['usename']} has held an open transaction for {session['idle_duration']}.",
                suggested_fix="Commit or roll back promptly; configure application transaction timeouts.",
            ))

        cursor.execute(AUTOVACUUM_SQL)
        for row in cursor.fetchall():
            table = _as_mapping(row, ("relname", "n_dead_tup", "last_autovacuum"))
            findings.append(HealthFinding(
                severity="warning", category="autovacuum",
                title=f"Autovacuum may be behind on {table['relname']}",
                description=f"The table has {int(table['n_dead_tup']):,} dead tuples; last autovacuum: {table['last_autovacuum']}.",
                suggested_fix="Run VACUUM (ANALYZE) and tune per-table autovacuum thresholds or scale factors.",
            ))

        cursor.execute(CONNECTION_UTILIZATION_SQL)
        connection_row = cursor.fetchone()
        if connection_row is not None:
            usage = _as_mapping(connection_row, ("current_connections", "max_connections"))
            current, maximum = int(usage["current_connections"]), int(usage["max_connections"])
            ratio = current / maximum if maximum else 0
            if ratio >= 0.8:
                findings.append(HealthFinding(
                    severity="critical" if ratio >= 0.9 else "warning", category="connection_utilization",
                    title="High database connection utilization",
                    description=f"{current} of {maximum} available connections are in use ({ratio:.0%}).",
                    suggested_fix="Investigate connection leaks, use a pooler, and keep headroom for administrative connections.",
                ))

        cursor.execute(CACHE_HIT_RATIO_SQL)
        cache_row = cursor.fetchone()
        if cache_row is not None and cache_row[0] is not None:
            cache_ratio = float(cache_row[0])
            if cache_ratio < 0.99:
                findings.append(HealthFinding(
                    severity="warning", category="cache_hit_ratio", title="Low PostgreSQL cache hit ratio",
                    description=f"The current database cache hit ratio is {cache_ratio:.1%}.",
                    suggested_fix="Review shared_buffers, working set size, indexes, and queries causing unnecessary reads.",
                ))

        cursor.execute(UNUSED_INDEXES_SQL)
        for row in cursor.fetchall():
            index = _as_mapping(row, ("schemaname", "relname", "indexrelname", "idx_scan", "index_size"))
            findings.append(HealthFinding(
                severity="info", category="index_usage", title=f"Unused index {index['indexrelname']}",
                description=f"Index {index['schemaname']}.{index['indexrelname']} on {index['relname']} has no recorded scans and uses {int(index['index_size']):,} bytes.",
                suggested_fix="Validate over a representative workload before dropping the index.",
            ))

        cursor.execute(SEQUENTIAL_SCAN_STATS_SQL)
        for row in cursor.fetchall():
            table = _as_mapping(row, ("relname", "seq_scan", "seq_tup_read", "n_live_tup"))
            findings.append(HealthFinding(
                severity="warning", category="sequential_scan", title=f"Heavy sequential scan activity on {table['relname']}",
                description=f"{table['relname']} has read {int(table['seq_tup_read']):,} rows through {int(table['seq_scan']):,} sequential scans.",
                suggested_fix="Review frequent predicates and verify whether an index improves the real query plan.",
            ))

        cursor.execute(BLOCKING_GRAPH_SQL)
        for row in cursor.fetchall():
            block = _as_mapping(row, ("blocked_pid", "blocked_user", "blocking_pid", "blocking_user", "wait_duration"))
            findings.append(HealthFinding(
                severity="critical", category="blocking_process", title=f"Session {block['blocking_pid']} is blocking session {block['blocked_pid']}",
                description=f"{block['blocking_user']} is blocking {block['blocked_user']} for {block['wait_duration']}.",
                suggested_fix="Inspect the blocker transaction and resolve it before cancelling blocked work.",
            ))

        cursor.execute(DATABASE_SIZE_SQL)
        size_row = cursor.fetchone()
        if size_row is not None:
            size = _as_mapping(size_row, ("database_size", "database_size_pretty"))
            findings.append(HealthFinding(
                severity="info", category="database_size", title="Database size baseline",
                description=f"The database currently occupies {size['database_size_pretty']} ({int(size['database_size']):,} bytes).",
                suggested_fix="Store this result periodically to calculate growth and plan storage capacity.",
            ))

        cursor.execute(TABLE_SIZE_RANKING_SQL)
        for row in cursor.fetchall():
            table = _as_mapping(row, ("schemaname", "relname", "total_size", "total_size_pretty"))
            findings.append(HealthFinding(
                severity="info", category="table_size", title=f"Large table: {table['schemaname']}.{table['relname']}",
                description=f"This table and its indexes use {table['total_size_pretty']} ({int(table['total_size']):,} bytes).",
                suggested_fix="Track this ranking over time and archive, partition, or retain less data where appropriate.",
            ))
        return findings
    finally:
        cursor.close()


def run_health_audit_sync(
    database_name: str | None = None,
    *,
    connection_factory: Callable[[str], object] = get_connection,
) -> list[HealthFinding]:
    """Run the audit synchronously and return typed findings.

    ``connection_factory`` is injectable so unit tests can pass a fake factory
    instead of requiring PostgreSQL.  If ``database_name`` is omitted, ``DB_NAME``
    is used.
    """
    target_database = database_name or os.getenv("DB_NAME")
    if not target_database:
        raise ValueError("database_name is required when DB_NAME is not configured")

    connection = connection_factory(target_database)
    try:
        return audit_connection(connection)
    finally:
        connection.close()


async def run_health_audit(database_name: str | None = None) -> list[dict[str, str]]:
    """Return slow-query, indexing, bloat, and lock-wait findings for one database.

    When no database name is supplied, the target is read from ``DB_NAME``. The
    synchronous psycopg2 connector is isolated in a worker thread so callers do
    not block the event loop.
    """
    target_database = database_name or os.getenv("DB_NAME")
    if not target_database:
        raise ValueError("database_name is required when DB_NAME is not configured")

    findings = await asyncio.to_thread(run_health_audit_sync, target_database)
    return [finding.model_dump() for finding in findings]


def main() -> None:
    """Print a JSON health report for use from a shell or custom script."""
    parser = argparse.ArgumentParser(description="Audit PostgreSQL database health")
    parser.add_argument("--database", help="Database name (defaults to DB_NAME)")
    args = parser.parse_args()
    findings = run_health_audit_sync(args.database)
    print(json.dumps([finding.model_dump() for finding in findings], indent=2))


if __name__ == "__main__":
    main()
