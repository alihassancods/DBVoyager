"""PostgreSQL health checks for the report written by :mod:`v1`."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.statistics.statistics_inspector import StatisticsInspector
from src.models.schema.schema_model import DatabaseSchema
from src.models.statistics.statistics_snapshot_model import StatisticsSnapshot
import warnings 
warnings.filterwarnings("ignore", category=UserWarning, module="openai" )




LONG_TRANSACTIONS_SQL = """
SELECT pid, usename, now() - xact_start AS duration, state
FROM pg_stat_activity
WHERE xact_start < now() - interval '5 minutes' AND pid <> pg_backend_pid()
ORDER BY xact_start
"""

BLOCKING_SQL = """
SELECT blocked.pid AS blocked_pid, blocker.pid AS blocking_pid,
       now() - blocked.query_start AS wait_duration
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS blocker_pid(pid)
JOIN pg_stat_activity AS blocker ON blocker.pid = blocker_pid.pid
ORDER BY blocked.query_start
"""

AUTOVACUUM_SQL = """
SELECT relname, n_dead_tup, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
  AND (last_autovacuum IS NULL OR last_autovacuum < now() - interval '7 days')
ORDER BY n_dead_tup DESC
"""

CONNECTION_SQL = """
SELECT count(*) AS current_connections,
       current_setting('max_connections')::integer AS max_connections
FROM pg_stat_activity
"""

SETTINGS_SQL = """
SELECT name, setting, unit
FROM pg_settings
WHERE name IN (
    'shared_buffers', 'work_mem', 'effective_cache_size', 'max_wal_size',
    'checkpoint_completion_target', 'statement_timeout',
    'idle_in_transaction_session_timeout', 'ssl', 'password_encryption',
    'log_min_duration_statement', 'log_connections', 'log_disconnections',
    'logging_collector'
)
"""

CHECKPOINTS_LEGACY_SQL = """
SELECT checkpoints_timed, checkpoints_req, buffers_checkpoint
FROM pg_stat_bgwriter
"""

CHECKPOINTS_V17_SQL = """
SELECT num_timed, num_requested, buffers_written
FROM pg_stat_checkpointer
"""

WAL_GENERATION_SQL = "SELECT wal_bytes FROM pg_stat_wal"

DEADLOCKS_SQL = """
SELECT deadlocks
FROM pg_stat_database
WHERE datname = current_database()
"""

REPLICATION_SQL = """
SELECT application_name, state,
       EXTRACT(EPOCH FROM COALESCE(replay_lag, '0 seconds'::interval))::bigint
           AS replay_lag_seconds
FROM pg_stat_replication
"""

ARCHIVER_SQL = """
SELECT archived_count, failed_count, last_archived_time, last_failed_time
FROM pg_stat_archiver
"""

PGSTATTUPLE_SQL = "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgstattuple') AS enabled"
INDEX_BLOAT_SQL = """
SELECT indexrelid::regclass::text AS index_name,
       (pgstatindex(indexrelid)).avg_leaf_density AS leaf_density
FROM pg_stat_user_indexes
"""


"""So to improve this we will add the health score to detect the severity instead of using the llm to do this to save the
tokens"""

FINDING_IMPACT_SCORES = {
    "blocking": 100,
    "locks": 95,
    "deadlocks": 95,
    "replication": 90,

    "slow_queries": 85,
    "missing_indexes": 80,
    "table_bloat": 75,
    "autovacuum_analyze": 75,

    "foreign_key_indexes": 60,
    "timeouts": 55,
    "cache_efficiency": 50,

    "unused_indexes": 20,
    "database_size": 10,
    "memory_configuration": 5,
    "wal_generation": 5,
    "security_logging": 5,
}

# initialize the health score to 100 and then deduct points based on the severity of the findings
def calculate_health_score(
    findings: list[dict],
) -> int:

    score = 100

    for finding in findings:

        severity = finding["severity"]

        if severity == "critical":
            score -= 20

        elif severity == "warning":
            score -= 10

        elif severity == "info":
            score -= 1

    return max(score, 0)

def _finding(
    check: str,
    severity: str,
    message: str,
    action: str = "",
) -> dict[str, Any]:

    impact_score = FINDING_IMPACT_SCORES.get(
        check,
        10,  # default score
    )

    result = {
        "check": check,
        "severity": severity,
        "message": message,
        "impact_score": impact_score,
    }

    if action:
        result["action"] = action

    return result


def _snapshot_findings(snapshot: StatisticsSnapshot, schema: DatabaseSchema | None) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    database = snapshot.database_stats
    findings.append(_finding(
        "database_size", "info", f"Database size is {database.database_size_mb:.2f} MB.",
        "Keep result.txt from periodic runs to establish growth.",
    ))
    if database.cache_hit_ratio < 99:
        findings.append(_finding(
            "cache_efficiency", "warning",
            f"Cache hit ratio is {database.cache_hit_ratio:.1f}%.",
            "Review shared_buffers, indexes, and queries causing physical reads.",
        ))

    for query in sorted(snapshot.query_stats, key=lambda item: item.mean_exec_time, reverse=True)[:10]:
        if query.mean_exec_time >= 100:
            findings.append(_finding(
                "slow_queries", "warning",
                f"Query averages {query.mean_exec_time:.1f} ms over {query.calls:,} calls: {query.query}",
                "Run EXPLAIN (ANALYZE, BUFFERS) before adding an index.",
            ))
    for query in sorted(snapshot.query_stats, key=lambda item: item.calls, reverse=True)[:10]:
        if query.calls >= 1000:
            findings.append(_finding(
                "frequent_queries", "info",
                f"Query has run {query.calls:,} times: {query.query}",
                "Prioritize this query if its total execution time is material.",
            ))

    for table in snapshot.table_stats:
        total = table.n_live_tup + table.n_dead_tup
        if total and table.n_dead_tup / total > 0.2:
            findings.append(_finding(
                "table_bloat", "warning",
                f"{table.table_name} has {table.n_dead_tup / total:.0%} dead tuples.",
                "Run VACUUM (ANALYZE) and review autovacuum thresholds.",
            ))
        if table.n_live_tup >= 100_000 and table.seq_scan > table.idx_scan:
            findings.append(_finding(
                "missing_indexes", "warning",
                f"{table.table_name} has {table.seq_scan:,} sequential scans versus {table.idx_scan:,} index scans.",
                "Review frequent predicates with EXPLAIN before creating an index.",
            ))
    for index in snapshot.index_stats:
        if index.idx_scan == 0:
            findings.append(_finding(
                "unused_indexes", "info", f"{index.table_name}.{index.index_name} has no recorded scans.",
                "Confirm over a representative statistics-reset interval before dropping it.",
            ))
    for lock in snapshot.lock_stats:
        if not lock.granted:
            findings.append(_finding(
                "locks", "critical", f"Session {lock.pid} waits for {lock.mode} on {lock.relation or 'an unknown relation'}.",
                "Find and resolve the blocking transaction.",
            ))

    if schema is None:
        return findings
    primary_key_tables = {key.table_name for key in schema.primary_keys}
    for table in schema.tables:
        if table.table_type == "BASE TABLE" and table.table_name not in primary_key_tables:
            findings.append(_finding("primary_keys", "warning", f"{table.schema_name}.{table.table_name} has no primary key.", "Add an appropriate primary key."))
    indexed_prefixes = {(index.table_name, index.indexed_columns[0].strip('"')) for index in schema.indexes if index.indexed_columns}
    for foreign_key in schema.foreign_keys:
        if (foreign_key.source_table, foreign_key.source_column) not in indexed_prefixes:
            findings.append(_finding("foreign_key_indexes", "warning", f"{foreign_key.source_table}.{foreign_key.source_column} is a foreign key without a leading index.", "Create an index if deletes or joins on this key are slow."))
    seen: dict[tuple[str, tuple[str, ...]], str] = {}
    for index in schema.indexes:
        key = (index.table_name, tuple(index.indexed_columns))
        if key in seen:
            findings.append(_finding("duplicate_indexes", "warning", f"{index.index_name} duplicates {seen[key]} on {index.table_name}.", "Validate constraints and drop one duplicate index."))
        else:
            seen[key] = index.index_name
    return findings


def _sql_findings(cursor: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    cursor.execute(LONG_TRANSACTIONS_SQL)
    for raw in cursor.fetchall():
        row = _row(raw, ("pid", "usename", "duration", "state"))
        findings.append(_finding("long_transactions", "warning", f"Session {row['pid']} ({row['usename']}) has been in a transaction for {row['duration']}.", "Commit or roll back promptly."))
    cursor.execute(BLOCKING_SQL)
    for raw in cursor.fetchall():
        row = _row(raw, ("blocked_pid", "blocking_pid", "wait_duration"))
        findings.append(_finding("blocking", "critical", f"Session {row['blocking_pid']} blocks {row['blocked_pid']} for {row['wait_duration']}.", "Inspect the blocker before cancelling work."))
    cursor.execute(AUTOVACUUM_SQL)
    for raw in cursor.fetchall():
        row = _row(raw, ("relname", "n_dead_tup", "last_autovacuum", "last_autoanalyze"))
        findings.append(_finding("autovacuum_analyze", "warning", f"{row['relname']} has {int(row['n_dead_tup']):,} dead tuples; autovacuum: {row['last_autovacuum']}, autoanalyze: {row['last_autoanalyze']}.", "Run VACUUM (ANALYZE) and tune autovacuum if this persists."))
    cursor.execute(CONNECTION_SQL)
    raw = cursor.fetchone()
    if raw is not None:
        row = _row(raw, ("current_connections", "max_connections"))
        ratio = int(row["current_connections"]) / int(row["max_connections"])
        if ratio >= 0.8:
            findings.append(_finding("connections", "critical" if ratio >= 0.9 else "warning", f"{row['current_connections']} of {row['max_connections']} connections are in use ({ratio:.0%}).", "Investigate leaks or use a connection pooler."))
    cursor.execute(SETTINGS_SQL)
    settings = {str(row["name"]): str(row["setting"]) for raw in cursor.fetchall() for row in [_row(raw, ("name", "setting", "unit"))]}
    findings.append(_finding("memory_configuration", "info", "Memory settings: " + ", ".join(f"{name}={settings.get(name, 'unavailable')}" for name in ("shared_buffers", "work_mem", "effective_cache_size"))))
    findings.append(_finding(
        "server_resources", "info",
        "PostgreSQL does not expose host CPU or filesystem capacity; collect those from the database host monitor.",
        "Review CPU, RAM, and disk utilization alongside this report.",
    ))
    for name in ("statement_timeout", "idle_in_transaction_session_timeout"):
        if settings.get(name) == "0":
            findings.append(_finding("timeouts", "warning", f"{name} is disabled.", f"Set a workload-appropriate {name}."))
    if settings.get("ssl") != "on":
        findings.append(_finding("security", "warning", "SSL is not enabled.", "Enable SSL for network connections."))
    if settings.get("log_min_duration_statement") == "-1":
        findings.append(_finding("logging", "warning", "Slow-query logging is disabled.", "Set log_min_duration_statement to a suitable threshold."))
    findings.append(_finding(
        "security_logging", "info",
        "Security/log settings: " + ", ".join(
            f"{name}={settings.get(name, 'unavailable')}"
            for name in ("ssl", "password_encryption", "logging_collector", "log_connections", "log_disconnections")
        ),
    ))
    cursor.execute("SHOW server_version_num")
    version = cursor.fetchone()
    cursor.execute(
        CHECKPOINTS_V17_SQL
        if version is not None and int(version[0]) >= 170000
        else CHECKPOINTS_LEGACY_SQL
    )
    raw = cursor.fetchone()
    if raw is not None:
        row = _row(raw, ("checkpoints_timed", "checkpoints_req", "buffers_checkpoint"))
        total = int(row["checkpoints_timed"]) + int(row["checkpoints_req"])
        if total and int(row["checkpoints_req"]) / total > 0.3:
            findings.append(_finding("wal_checkpoints", "warning", f"{int(row['checkpoints_req']) / total:.0%} of checkpoints were requested.", "Review max_wal_size and checkpoint_completion_target."))
    cursor.execute(WAL_GENERATION_SQL)
    raw = cursor.fetchone()
    if raw is not None:
        row = _row(raw, ("wal_bytes",))
        findings.append(_finding("wal_generation", "info", f"WAL written since the statistics reset: {int(row['wal_bytes']):,} bytes.", "Compare periodic result.txt reports to identify unexpected WAL growth."))
    cursor.execute(DEADLOCKS_SQL)
    raw = cursor.fetchone()
    if raw is not None:
        row = _row(raw, ("deadlocks",))
        if int(row["deadlocks"]):
            findings.append(_finding("deadlocks", "warning", f"{row['deadlocks']} deadlocks have occurred since the statistics reset.", "Review application lock ordering and transaction scope."))
    cursor.execute(REPLICATION_SQL)
    for raw in cursor.fetchall():
        row = _row(raw, ("application_name", "state", "replay_lag_seconds"))
        if int(row["replay_lag_seconds"]) > 60:
            findings.append(_finding("replication", "critical" if int(row["replay_lag_seconds"]) > 300 else "warning", f"Replica {row['application_name']} is {row['replay_lag_seconds']} seconds behind ({row['state']}).", "Check replica resources, network, and WAL retention."))
    cursor.execute(ARCHIVER_SQL)
    raw = cursor.fetchone()
    if raw is not None:
        row = _row(raw, ("archived_count", "failed_count", "last_archived_time", "last_failed_time"))
        findings.append(_finding("backups", "info", f"WAL archive count is {row['archived_count']}; last archive: {row['last_archived_time']}.", "Run and restore-test a real backup; PostgreSQL cannot verify backup validity."))
        if int(row["failed_count"]):
            findings.append(_finding("backups_wal_archive", "critical", f"WAL archiving has failed {row['failed_count']} times; last failure: {row['last_failed_time']}.", "Fix archive_command and verify a restorable backup separately."))
    cursor.execute(PGSTATTUPLE_SQL)
    raw = cursor.fetchone()
    if raw and _row(raw, ("enabled",))["enabled"]:
        cursor.execute(INDEX_BLOAT_SQL)
        for raw in cursor.fetchall():
            row = _row(raw, ("index_name", "leaf_density"))
            if float(row["leaf_density"]) < 50:
                findings.append(_finding("index_bloat", "warning", f"{row['index_name']} has {float(row['leaf_density']):.0f}% leaf density.", "Consider REINDEX after confirming index bloat."))
    else:
        findings.append(_finding("index_bloat", "info", "Exact index-bloat measurement needs the pgstattuple extension.", "Install pgstattuple to measure index leaf density."))
    return findings


def audit_connection(connection: Any, statistics_snapshot: StatisticsSnapshot, schema: DatabaseSchema | None = None) -> list[dict[str, str]]:
    """Return plain report entries, reusing the already collected snapshots."""
    cursor = connection.cursor()
    try:
        findings = (
             _snapshot_findings(
                 statistics_snapshot,
                 schema,
             )
             + _sql_findings(cursor)
    )

        findings.sort(
            key=lambda x: x["impact_score"],
            reverse=True,
        )

        return findings
    finally:
        cursor.close()


def run_health_audit_sync(database_name: str | None = None, *, connection_factory: Callable[[str], Any] = get_connection) -> list[dict[str, str]]:
    """Collect snapshots and health checks for callers outside ``v1.py``."""
    database_name = database_name or os.getenv("DB_NAME")
    if not database_name:
        raise ValueError("database_name is required when DB_NAME is not configured")
    provider = lambda: connection_factory(database_name)
    snapshot = StatisticsInspector(provider).get_snapshot()
    schema = SchemaInspector.from_connection_provider(provider).inspect()
    connection = provider()
    try:
        return audit_connection(connection, snapshot, schema)
    finally:
        connection.close()


async def run_health_audit(database_name: str | None = None) -> list[dict[str, str]]:
    return await asyncio.to_thread(run_health_audit_sync, database_name)
