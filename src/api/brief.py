"""Bounded, evidence-first PostgreSQL collection for the dashboard."""

from collections.abc import Callable
from typing import Any

from psycopg2.extras import RealDictCursor


def collect_brief(connection_provider: Callable[[], Any], progress: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    def emit(message: str) -> None:
        if progress:
            progress("brief", message)

    connection = connection_provider()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            emit("Collecting database health.")
            cursor.execute("""SELECT count(*) AS num_connections, current_setting('max_connections')::int AS max_connections,
                              pg_database_size(current_database()) / 1024.0 / 1024.0 AS database_size_mb,
                              round(sum(blks_hit) * 100.0 / nullif(sum(blks_hit + blks_read), 0), 2) AS cache_hit_ratio
                              FROM pg_stat_database WHERE datname = current_database()""")
            database = dict(cursor.fetchone() or {})
            cursor.execute("""SELECT pid, mode, relation::regclass::text AS relation FROM pg_locks
                              WHERE NOT granted ORDER BY pid LIMIT 20""")
            locks = [dict(row) for row in cursor.fetchall()]
            emit("Collecting highest-impact table signals.")
            cursor.execute("""SELECT relname AS table_name, n_live_tup, n_dead_tup, seq_scan, idx_scan
                              FROM pg_stat_user_tables
                              ORDER BY (n_dead_tup::numeric / nullif(n_live_tup + n_dead_tup, 0)) DESC NULLS LAST, seq_scan DESC
                              LIMIT 20""")
            tables = [dict(row) for row in cursor.fetchall()]
            emit("Collecting top query signals.")
            try:
                cursor.execute("""SELECT left(query, 1000) AS query, calls, total_exec_time, mean_exec_time, rows AS rows_returned
                                  FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20""")
                queries, telemetry = [dict(row) for row in cursor.fetchall()], True
            except Exception:
                connection.rollback()
                queries, telemetry = [], False
    finally:
        connection.close()

    insights: list[dict[str, Any]] = []
    if database.get("max_connections") and database.get("num_connections", 0) / database["max_connections"] >= 0.8:
        insights.append({"severity": "warning", "title": "Connection pressure", "evidence": database, "action": "Review connection pooling and long-lived sessions."})
    for lock in locks:
        insights.append({"severity": "critical", "title": "Blocked database session", "evidence": lock, "action": "Inspect the blocking transaction before cancelling work."})
    for table in tables:
        live, dead = table.get("n_live_tup", 0), table.get("n_dead_tup", 0)
        if live + dead and dead / (live + dead) >= 0.2:
            insights.append({"severity": "warning", "title": f"Table bloat risk: {table['table_name']}", "evidence": table, "action": "Review autovacuum and run VACUUM (ANALYZE) if appropriate."})
        elif table.get("seq_scan", 0) > table.get("idx_scan", 0) and live >= 100_000:
            insights.append({"severity": "warning", "title": f"Sequential scan pressure: {table['table_name']}", "evidence": table, "action": "Review frequent predicates with EXPLAIN before adding an index."})
    for query in queries[:5]:
        if query.get("mean_exec_time", 0) >= 100:
            insights.append({"severity": "warning", "title": "Slow query", "evidence": query, "action": "Open Query Optimizer for an evidence-backed recommendation."})
    if not telemetry:
        insights.append({"severity": "info", "title": "Query telemetry unavailable", "evidence": {}, "action": "Enable pg_stat_statements to unlock slow-query insights."})
    order = {"critical": 0, "warning": 1, "info": 2}
    return {"database_stats": database, "tables": tables, "queries": queries, "insights": sorted(insights, key=lambda item: order[item["severity"]])[:10], "query_telemetry_available": telemetry}
