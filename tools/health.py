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
from src.db_engine.inspectors.statistics.statistics_inspector import StatisticsInspector
from src.db_engine.queries.statistics_queries import (
    GET_CHECKPOINT_STATS_QUERY,
    GET_IDLE_CONNECTIONS_QUERY,
    GET_REPLICATION_LAG_QUERY,
    GET_TEMP_SPILLING_QUERY,
    GET_TIMEOUT_CONFIG_QUERY,
    GET_WRAPAROUND_AGE_QUERY,
)
from src.models.statistics.statistics_snapshot_model import StatisticsSnapshot


logger = logging.getLogger(__name__)

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

BLOCKING_GRAPH_SQL = """
    SELECT blocked.pid AS blocked_pid, blocked.usename AS blocked_user,
           blocker.pid AS blocking_pid, blocker.usename AS blocking_user,
           now() - blocked.query_start AS wait_duration
    FROM pg_stat_activity AS blocked
    CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
    JOIN pg_stat_activity AS blocker ON blocker.pid = blocking_pid.pid
    ORDER BY blocked.query_start
"""

TABLE_SIZE_RANKING_SQL = """
    SELECT schemaname, relname, pg_total_relation_size(relid) AS total_size,
           pg_size_pretty(pg_total_relation_size(relid)) AS total_size_pretty
    FROM pg_statio_user_tables
    ORDER BY pg_total_relation_size(relid) DESC
    LIMIT 10
"""
# ===== New health check queries =====

MISSING_PRIMARY_KEY_SQL = """
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_type = 'BASE TABLE'
      AND table_name NOT IN (
          SELECT table_name
          FROM information_schema.table_constraints
          WHERE constraint_type = 'PRIMARY KEY'
            AND table_schema = 'public'
      )
    ORDER BY table_name;
"""

MISSING_FK_INDEX_SQL = """
    SELECT
        tc.table_schema,
        tc.table_name,
        kcu.column_name,
        ccu.table_name AS target_table,
        ccu.column_name AS target_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_catalog = kcu.constraint_catalog
        AND tc.constraint_schema = kcu.constraint_schema
        AND tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_catalog = ccu.constraint_catalog
        AND tc.constraint_schema = ccu.constraint_schema
        AND tc.constraint_name = ccu.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
    ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position;
"""

GET_DUPLICATE_INDEX_DEFS_SQL = """
    SELECT
        indrelid::regclass::text AS table_name,
        indexrelid::regclass::text AS index_name,
        pg_get_indexdef(indexrelid) AS index_definition
    FROM pg_index
    WHERE NOT indisprimary
    ORDER BY indrelid, indexrelid;
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
        # New checks
        "missing_primary_key",
        "missing_fk_index",
        "wraparound_age",
        "redundant_index",
        "checkpoint_frequency",
        "replication_lag",
        "temp_spilling",
        "timeout_config",
        "idle_timeout",
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

def _check_missing_primary_keys(cursor: object) -> list[HealthFinding]:
    """Flag tables that have no primary key defined."""
    findings: list[HealthFinding] = []
    cursor.execute(MISSING_PRIMARY_KEY_SQL)
    for row in cursor.fetchall():
        table = _as_mapping(row, ("table_schema", "table_name"))
        findings.append(HealthFinding(
            severity="warning",
            category="missing_primary_key",
            title=f"Table {table['table_name']} has no primary key",
            description=f"Table {table['table_schema']}.{table['table_name']} is a BASE TABLE without a primary key constraint.",
            suggested_fix="Add a PRIMARY KEY using an appropriate column (typically an 'id' BIGSERIAL column).",
        ))
    return findings


def _check_missing_fk_indexes(cursor: object) -> list[HealthFinding]:
    """Flag foreign key columns that lack an index."""
    findings: list[HealthFinding] = []
    cursor.execute(MISSING_FK_INDEX_SQL)
    foreign_keys = cursor.fetchall()

    # Get all existing indexes
    cursor.execute("""
        SELECT tablename, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
    """)
    indexes = cursor.fetchall()
    indexed_columns: dict[str, set[str]] = {}
    for idx_row in indexes:
        idx = _as_mapping(idx_row, ("tablename", "indexdef"))
        table = str(idx["tablename"])
        # Parse column names from index definition
        defn = str(idx["indexdef"])
        if "(" in defn and ")" in defn:
            cols_part = defn.split("(")[1].split(")")[0]
            for col in cols_part.split(","):
                indexed_columns.setdefault(table, set()).add(col.strip().strip('"'))

    for row in foreign_keys:
        fk = _as_mapping(row, ("table_schema", "table_name", "column_name", "target_table", "target_column"))
        table = str(fk["table_name"])
        column = str(fk["column_name"])
        if table not in indexed_columns or column not in indexed_columns[table]:
            findings.append(HealthFinding(
                severity="warning",
                category="missing_fk_index",
                title=f"Missing index on FK column {table}.{column}",
                description=f"Foreign key column {table}.{column} references {fk['target_table']}.{fk['target_column']} but has no index.",
                suggested_fix=f"CREATE INDEX idx_{table}_{column} ON {table}({column});",
            ))
    return findings


def _check_wraparound_age(cursor: object) -> list[HealthFinding]:
    """Flag databases approaching transaction ID wraparound."""
    findings: list[HealthFinding] = []
    cursor.execute(GET_WRAPAROUND_AGE_QUERY)
    for row in cursor.fetchall():
        db = _as_mapping(row, ("datname", "wraparound_age", "pct_to_wraparound"))
        pct = float(db["pct_to_wraparound"])
        if pct > 80:
            findings.append(HealthFinding(
                severity="critical",
                category="wraparound_age",
                title=f"Database {db['datname']} at {pct}% of wraparound limit",
                description=f"Transaction age is {db['wraparound_age']:,} ({pct}% of autovacuum_freeze_max_age).",
                suggested_fix="Run VACUUM FREEZE immediately or schedule aggressive autovacuum freezing.",
            ))
        elif pct > 50:
            findings.append(HealthFinding(
                severity="warning",
                category="wraparound_age",
                title=f"Database {db['datname']} at {pct}% of wraparound limit",
                description=f"Transaction age is {db['wraparound_age']:,} ({pct}% of autovacuum_freeze_max_age).",
                suggested_fix="Review autovacuum freeze settings and ensure regular VACUUM cycles.",
            ))
    return findings


def _check_redundant_indexes(cursor: object) -> list[HealthFinding]:
    """Detect potentially redundant/duplicate indexes."""
    findings: list[HealthFinding] = []
    cursor.execute(GET_DUPLICATE_INDEX_DEFS_SQL)
    rows = cursor.fetchall()

    # Group index definitions by table
    from collections import defaultdict
    table_indexes: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        idx = _as_mapping(row, ("table_name", "index_name", "index_definition"))
        table_indexes[str(idx["table_name"])].append({
            "name": str(idx["index_name"]),
            "def": str(idx["index_definition"]),
        })

    for table_name, indexes_list in table_indexes.items():
        for i in range(len(indexes_list)):
            for j in range(i + 1, len(indexes_list)):
                a = indexes_list[i]["def"]
                b = indexes_list[j]["def"]
                # Simple heuristic: same columns in same order after stripping name
                a_cols = a.split("(")[1].rstrip(")") if "(" in a else ""
                b_cols = b.split("(")[1].rstrip(")") if "(" in b else ""
                if a_cols and a_cols == b_cols:
                    findings.append(HealthFinding(
                        severity="warning",
                        category="redundant_index",
                        title=f"Duplicate indexes on {table_name}",
                        description=f"Indexes {indexes_list[i]['name']} and {indexes_list[j]['name']} cover identical columns.",
                        suggested_fix=f"Drop one of the duplicate indexes: DROP INDEX IF EXISTS {indexes_list[j]['name']};",
                    ))
                elif a_cols and b_cols.startswith(a_cols + ","):
                    findings.append(HealthFinding(
                        severity="info",
                        category="redundant_index",
                        title=f"Redundant index on {table_name}",
                        description=f"Index {indexes_list[i]['name']} is a prefix of {indexes_list[j]['name']}.",
                        suggested_fix=f"Consider whether {indexes_list[i]['name']} is still needed.",
                    ))
    return findings


def _check_checkpoint_frequency(cursor: object) -> list[HealthFinding]:
    """Flag excessive checkpoint activity."""
    findings: list[HealthFinding] = []
    cursor.execute(GET_CHECKPOINT_STATS_QUERY)
    row = cursor.fetchone()
    if row is not None:
        stats = _as_mapping(row, (
            "checkpoints_timed", "checkpoints_req",
            "checkpoint_write_time", "checkpoint_sync_time",
            "buffers_checkpoint",
        ))
        timed = int(stats["checkpoints_timed"])
        req = int(stats["checkpoints_req"])
        total = timed + req
        if total > 0 and req / total > 0.3:
            findings.append(HealthFinding(
                severity="warning",
                category="checkpoint_frequency",
                title="High ratio of requested checkpoints",
                description=f"{req} of {total} checkpoints were requested (not timed) — {req / total:.0%}.",
                suggested_fix="Increase max_wal_size or checkpoint_completion_target to reduce forced checkpoints.",
            ))
    return findings


def _check_replication_lag(cursor: object) -> list[HealthFinding]:
    """Flag replication lag on standby servers."""
    findings: list[HealthFinding] = []
    cursor.execute(GET_REPLICATION_LAG_QUERY)
    row = cursor.fetchone()
    if row is not None:
        status = _as_mapping(row, ("role", "replication_lag_seconds"))
        if str(status["role"]) == "standby":
            lag = int(status["replication_lag_seconds"])
            if lag > 60:
                findings.append(HealthFinding(
                    severity="critical" if lag > 300 else "warning",
                    category="replication_lag",
                    title=f"Replication lag is {lag} seconds",
                    description=f"The standby server is {lag} seconds behind the primary.",
                    suggested_fix="Check network bandwidth, WAL archiving, and standby resources.",
                ))
    return findings


def _check_temp_spilling(cursor: object) -> list[HealthFinding]:
    """Flag queries that spill to temp files (work_mem too low)."""
    findings: list[HealthFinding] = []
    cursor.execute(GET_TEMP_SPILLING_QUERY)
    for row in cursor.fetchall():
        query = _as_mapping(row, ("query", "calls", "total_exec_time", "temp_mb_written"))
        temp_mb = float(query["temp_mb_written"])
        if temp_mb > 100:
            findings.append(HealthFinding(
                severity="warning",
                category="temp_spilling",
                title=f"Query spilled {temp_mb:.0f} MB to temp disk",
                description=f"A query spilled {temp_mb:.0f} MB to temporary disk storage ({query['calls']} calls, {query['total_exec_time']:.0f} ms total).",
                suggested_fix="Increase work_mem for this session or consider optimizing the query plan.",
            ))
    return findings


def _check_timeout_config(cursor: object) -> list[HealthFinding]:
    """Flag risky timeout configurations."""
    findings: list[HealthFinding] = []
    cursor.execute(GET_TIMEOUT_CONFIG_QUERY)
    for row in cursor.fetchall():
        setting = _as_mapping(row, ("name", "setting", "unit", "short_desc"))
        if str(setting["name"]) == "statement_timeout" and str(setting["setting"]) == "0":
            findings.append(HealthFinding(
                severity="warning",
                category="timeout_config",
                title="Statement timeout is disabled",
                description="statement_timeout is set to 0 (no limit). Long-running queries can run indefinitely.",
                suggested_fix="Set statement_timeout to a reasonable limit, e.g., '30s' or '5min'.",
            ))
        if str(setting["name"]) == "idle_in_transaction_session_timeout" and str(setting["setting"]) == "0":
            findings.append(HealthFinding(
                severity="warning",
                category="timeout_config",
                title="Idle-in-transaction timeout is disabled",
                description="idle_in_transaction_session_timeout is set to 0. Idle transactions can hold locks indefinitely.",
                suggested_fix="Set idle_in_transaction_session_timeout to a reasonable value, e.g., '5min'.",
            ))
    return findings


def _check_idle_connections(cursor: object) -> list[HealthFinding]:
    """Flag connections idle for extended periods."""
    findings: list[HealthFinding] = []
    cursor.execute(GET_IDLE_CONNECTIONS_QUERY)
    for row in cursor.fetchall():
        conn = _as_mapping(row, ("pid", "datname", "usename", "state", "idle_seconds", "query"))
        idle_min = int(conn["idle_seconds"]) / 60
        findings.append(HealthFinding(
            severity="info",
            category="idle_timeout",
            title=f"Session {conn['pid']} idle for {idle_min:.0f} minutes",
            description=f"User {conn['usename']} in {conn['datname']} has been idle for {idle_min:.0f} minutes.",
            suggested_fix="Consider terminating long-idle connections or configuring idle_in_transaction_session_timeout.",
        ))
    return findings

class _BorrowedConnection:
    """Prevent inspectors from closing a connection owned by ``audit_connection``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def cursor(self, *args: object, **kwargs: object) -> object:
        return self._connection.cursor(*args, **kwargs)

    def close(self) -> None:
        """Inspectors own their connections normally; this lease owns nothing."""


def _statistics_findings(
    snapshot: StatisticsSnapshot, connection: object, cursor: object
) -> list[HealthFinding]:
    """Apply health thresholds to data collected by ``StatisticsInspector``."""
    findings: list[HealthFinding] = []

    for statement in snapshot.query_stats:
        findings.append(HealthFinding(
            severity="warning", category="slow_query",
            title="High mean execution time query",
            description=f"This statement averages {statement.mean_exec_time:.2f} ms per execution.",
            suggested_fix="Inspect its execution plan and reduce unnecessary I/O or row processing.",
        ))
        findings.extend(_scan_query_plan(connection, cursor, statement.query, statement.mean_exec_time))

    for table in snapshot.table_stats:
        total_tuples = table.n_live_tup + table.n_dead_tup
        dead_tuple_ratio = table.n_dead_tup / total_tuples if total_tuples else 0
        if dead_tuple_ratio > 0.2:
            findings.append(HealthFinding(
                severity="warning", category="bloat",
                title=f"High dead tuple ratio on {table.table_name}",
                description=(f"{table.table_name} has {table.n_dead_tup:,} dead tuples "
                             f"({dead_tuple_ratio:.1%} of estimated tuples)."),
                suggested_fix="Run VACUUM (ANALYZE) and review autovacuum thresholds for this table.",
            ))
        if table.seq_scan > 100 and table.n_live_tup > 100_000:
            findings.append(HealthFinding(
                severity="warning", category="sequential_scan",
                title=f"Heavy sequential scan activity on {table.table_name}",
                description=(f"{table.table_name} has {table.seq_scan:,} sequential scans "
                             f"and an estimated {table.n_live_tup:,} live rows."),
                suggested_fix="Review frequent predicates and verify whether an index improves the real query plan.",
            ))

    for index in snapshot.index_stats:
        if index.idx_scan == 0:
            findings.append(HealthFinding(
                severity="info", category="index_usage",
                title=f"Unused index {index.index_name}",
                description=f"Index {index.table_name}.{index.index_name} has no recorded scans.",
                suggested_fix="Validate over a representative workload before dropping the index.",
            ))

    for lock in snapshot.lock_stats:
        if not lock.granted:
            findings.append(HealthFinding(
                severity="critical", category="lock",
                title=f"Session {lock.pid} is waiting on a lock",
                description=f"Session {lock.pid} is waiting for {lock.mode} on {lock.relation or 'an unknown relation'}.",
                suggested_fix="Identify the blocking session and end or optimize the blocking transaction.",
            ))

    database = snapshot.database_stats
    if database.cache_hit_ratio < 99:
        findings.append(HealthFinding(
            severity="warning", category="cache_hit_ratio", title="Low PostgreSQL cache hit ratio",
            description=f"The current database cache hit ratio is {database.cache_hit_ratio:.1f}%.",
            suggested_fix="Review shared_buffers, working set size, indexes, and queries causing unnecessary reads.",
        ))
    findings.append(HealthFinding(
        severity="info", category="database_size", title="Database size baseline",
        description=f"The database currently occupies {database.database_size_mb:.2f} MB.",
        suggested_fix="Store this result periodically to calculate growth and plan storage capacity.",
    ))
    return findings


def audit_connection(
    connection: object, statistics_snapshot: StatisticsSnapshot | None = None
) -> list[HealthFinding]:
    """Audit an already-open connection without reimplementing statistics queries.

    Supplying a snapshot avoids extra queries.  When omitted, the existing
    ``StatisticsInspector`` is used with a non-closing lease of this connection.
    The caller's connection remains open when this function returns.
    """
    if statistics_snapshot is None:
        statistics_snapshot = StatisticsInspector(
            lambda: _BorrowedConnection(connection)
        ).get_snapshot()

    cursor = connection.cursor()
    try:
        findings = _statistics_findings(statistics_snapshot, connection, cursor)

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

        cursor.execute(BLOCKING_GRAPH_SQL)
        for row in cursor.fetchall():
            block = _as_mapping(row, ("blocked_pid", "blocked_user", "blocking_pid", "blocking_user", "wait_duration"))
            findings.append(HealthFinding(
                severity="critical", category="blocking_process", title=f"Session {block['blocking_pid']} is blocking session {block['blocked_pid']}",
                description=f"{block['blocking_user']} is blocking {block['blocked_user']} for {block['wait_duration']}.",
                suggested_fix="Inspect the blocker transaction and resolve it before cancelling blocked work.",
            ))

        cursor.execute(TABLE_SIZE_RANKING_SQL)
        for row in cursor.fetchall():
            table = _as_mapping(row, ("schemaname", "relname", "total_size", "total_size_pretty"))
            findings.append(HealthFinding(
                severity="info", category="table_size", title=f"Large table: {table['schemaname']}.{table['relname']}",
                description=f"This table and its indexes use {table['total_size_pretty']} ({int(table['total_size']):,} bytes).",
                suggested_fix="Track this ranking over time and archive, partition, or retain less data where appropriate.",
            ))
                # === New health checks ===
        findings.extend(_check_missing_primary_keys(cursor))
        findings.extend(_check_missing_fk_indexes(cursor))
        findings.extend(_check_wraparound_age(cursor))
        findings.extend(_check_redundant_indexes(cursor))
        findings.extend(_check_checkpoint_frequency(cursor))
        findings.extend(_check_replication_lag(cursor))
        findings.extend(_check_temp_spilling(cursor))
        findings.extend(_check_timeout_config(cursor))
        findings.extend(_check_idle_connections(cursor))
        return findings
    finally:
        cursor.close()


def run_health_audit_sync(
    database_name: str | None = None,
    *,
    connection_factory: Callable[[str], object] = get_connection,
) -> list[HealthFinding]:
    """Run the audit synchronously and return typed findings.

    ``connection_factory`` is injectable and must return a fresh connection for
    each call because the reusable inspectors close their own connections. If
    ``database_name`` is omitted, ``DB_NAME`` is used.
    """
    target_database = database_name or os.getenv("DB_NAME")
    if not target_database:
        raise ValueError("database_name is required when DB_NAME is not configured")

    connection_provider = lambda: connection_factory(target_database)
    statistics_snapshot = StatisticsInspector(connection_provider).get_snapshot()
    connection = connection_provider()
    try:
        return audit_connection(connection, statistics_snapshot)
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
