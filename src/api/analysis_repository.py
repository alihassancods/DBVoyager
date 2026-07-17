"""Persist and retrieve analysis runs for monitored databases."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Any

import psycopg2
from fastapi import HTTPException, status
from psycopg2.extras import Json

from src.agent import TableBusinessSummaryAgent, TableSummaryInput
from v1 import build_report


ConnectionProvider = Callable[[], Any]
ProgressCallback = Callable[[str, str], None]
_progress_events: dict[str, list[dict[str, str]]] = {}
_progress_lock = Lock()


def get_analysis_progress(run_id: str, offset: int) -> tuple[list[dict[str, str]], int]:
    with _progress_lock:
        events = _progress_events.get(run_id, [])
        return events[offset:], len(events)


def _record_progress(run_id: str, stage: str, message: str) -> None:
    with _progress_lock:
        _progress_events.setdefault(run_id, []).append({"stage": stage, "message": message})


def _app_connection() -> Any:
    database_url = os.getenv("APP_DATABASE_URL")
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APP_DATABASE_URL is not configured",
        )
    try:
        return psycopg2.connect(database_url, connect_timeout=10)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=502, detail="Could not reach the application database") from exc


def create_analysis_run(connection_id: str, trigger: str) -> str:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO analysis_runs (monitored_database_id, trigger)
                VALUES (%s, %s)
                RETURNING id
                """,
                (connection_id, trigger),
            )
            return str(cursor.fetchone()[0])


def run_analysis(
    run_id: str,
    connection_id: str,
    database_name: str,
    connection_provider: ConnectionProvider,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    _set_running(run_id)
    try:
        report = build_report(database_name, connection_provider, progress)
        if progress:
            progress("persistence", "Saving analysis results.")
        _persist_report(run_id, connection_id, report, progress)
        if progress:
            progress("persistence", "Analysis results saved.")
        return report
    except Exception as exc:
        _mark_failed(run_id, f"{type(exc).__name__}: {exc}")
        raise


def run_analysis_in_background(
    run_id: str,
    connection_id: str,
    database_name: str,
    connection_provider: ConnectionProvider,
) -> None:
    try:
        _record_progress(run_id, "analysis", "Starting database analysis.")
        run_analysis(
            run_id,
            connection_id,
            database_name,
            connection_provider,
            lambda stage, message: _record_progress(run_id, stage, message),
        )
        _record_progress(run_id, "analysis", "Analysis report persisted.")
    except Exception:
        return


def get_latest_report(connection_id: str, auth_subject: str) -> dict[str, Any]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT runs.report_json
                FROM analysis_runs AS runs
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE runs.monitored_database_id = %s
                  AND users.auth_subject = %s
                  AND runs.status = 'succeeded'
                ORDER BY runs.finished_at DESC
                LIMIT 1
                """,
                (connection_id, auth_subject),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No completed dashboard report found")
    return row[0]


def get_analysis_run(connection_id: str, run_id: str, auth_subject: str) -> dict[str, Any]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT runs.status, runs.trigger, runs.created_at, runs.started_at,
                       runs.finished_at, runs.report_json, runs.error_code, runs.error_message
                FROM analysis_runs AS runs
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE runs.id = %s
                  AND runs.monitored_database_id = %s
                  AND users.auth_subject = %s
                """,
                (run_id, connection_id, auth_subject),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return {
        "analysis_run_id": run_id,
        "status": row[0],
        "trigger": row[1],
        "created_at": row[2],
        "started_at": row[3],
        "finished_at": row[4],
        "report": row[5],
        "error_code": row[6],
        "error_message": row[7],
    }


def ensure_owned_database(connection_id: str, auth_subject: str) -> None:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM monitored_databases AS databases
                JOIN users ON users.id = databases.owner_user_id
                WHERE databases.id = %s
                  AND databases.deleted_at IS NULL
                  AND users.auth_subject = %s
                """,
                (connection_id, auth_subject),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Database not found")


def _set_running(run_id: str) -> None:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE analysis_runs
                SET status = 'running', started_at = now(), attempt_count = attempt_count + 1,
                    lease_expires_at = now() + interval '10 minutes'
                WHERE id = %s AND status = 'queued'
                """,
                (run_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Analysis run is not available")


def _mark_failed(run_id: str, message: str) -> None:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE analysis_runs
                SET status = 'failed', finished_at = now(), lease_expires_at = NULL,
                    error_code = 'analysis_failed', error_message = %s
                WHERE id = %s AND status <> 'succeeded'
                """,
                (message[:1000], run_id),
            )


def _persist_report(
    run_id: str,
    connection_id: str,
    report: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> None:
    statistics = _ok_data(report, "statistics")
    schema = _ok_data(report, "schema")
    health_checks = _ok_data(report, "health_checks")
    generated_at = report.get("generated_at") or datetime.now(UTC).isoformat()
    complete = statistics is not None and schema is not None

    with _app_connection() as connection:
        with connection.cursor() as cursor:
            schema_revision_id = None
            if schema is not None:
                schema_revision_id = _persist_schema(cursor, run_id, connection_id, schema, report, progress)
                _persist_table_summaries(cursor, connection_id, run_id, schema_revision_id, schema, progress)
            if statistics is not None:
                _persist_statistics(cursor, run_id, connection_id, generated_at, statistics, schema, progress)
            if health_checks is not None:
                _persist_health_checks(cursor, run_id, health_checks, progress)

            if complete:
                cursor.execute(
                    """
                    UPDATE monitored_databases
                    SET last_successful_run_id = %s, current_schema_revision_id = %s,
                        last_collected_at = %s
                    WHERE id = %s
                    """,
                    (run_id, schema_revision_id, generated_at, connection_id),
                )
            cursor.execute(
                """
                UPDATE analysis_runs
                SET status = %s, finished_at = now(), lease_expires_at = NULL,
                    report_json = %s, schema_revision_id = %s,
                    schema_fingerprint = %s, error_code = %s, error_message = %s
                WHERE id = %s
                """,
                (
                    "succeeded" if complete else "failed",
                    Json(report),
                    schema_revision_id,
                    _fingerprint(schema) if schema is not None else None,
                    None if complete else "collection_incomplete",
                    None if complete else "Statistics and schema collection must both succeed",
                    run_id,
                ),
            )
            if progress:
                progress("persistence", "Finalized analysis run status.")


def _persist_statistics(
    cursor: Any,
    run_id: str,
    connection_id: str,
    collected_at: str,
    statistics: dict[str, Any],
    schema: dict[str, Any] | None,
    progress: ProgressCallback | None = None,
) -> None:
    database = statistics["database_stats"]
    cursor.execute(
        """
        INSERT INTO database_stat_snapshots (
            run_id, collected_at, num_connections, database_size_mb, cache_hit_ratio
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            run_id,
            collected_at,
            database["num_connections"],
            database["database_size_mb"],
            database["cache_hit_ratio"],
        ),
    )
    cursor.execute(
        """
        UPDATE monitored_databases
        SET num_connections = %s, database_size_mb = %s, cache_hit_ratio = %s,
            last_collected_at = %s
        WHERE id = %s
        """,
        (
            database["num_connections"],
            database["database_size_mb"],
            database["cache_hit_ratio"],
            collected_at,
            connection_id,
        ),
    )

    table_metadata = {
        (table["schema_name"], table["table_name"]): table
        for table in (schema or {}).get("tables", [])
    }
    table_ids: dict[str, str] = {}
    table_stats = statistics.get("table_stats", [])
    for number, table_stat in enumerate(table_stats, start=1):
        table = table_metadata.get(("public", table_stat["table_name"]))
        if table is None:
            continue
        cursor.execute(
            """
            INSERT INTO database_tables (
                monitored_database_id, schema_name, table_name, table_type, estimated_rows,
                seq_scan, idx_scan, n_live_tup, n_dead_tup, stats_collected_at,
                schema_collected_at, last_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (monitored_database_id, schema_name, table_name) WHERE removed_at IS NULL
            DO UPDATE SET table_type = EXCLUDED.table_type,
                          estimated_rows = EXCLUDED.estimated_rows,
                          seq_scan = EXCLUDED.seq_scan,
                          idx_scan = EXCLUDED.idx_scan,
                          n_live_tup = EXCLUDED.n_live_tup,
                          n_dead_tup = EXCLUDED.n_dead_tup,
                          stats_collected_at = EXCLUDED.stats_collected_at,
                          schema_collected_at = EXCLUDED.schema_collected_at,
                          last_seen_at = now()
            RETURNING id
            """,
            (
                connection_id,
                table["schema_name"],
                table["table_name"],
                table["table_type"],
                table["estimated_rows"],
                table_stat["seq_scan"],
                table_stat["idx_scan"],
                table_stat["n_live_tup"],
                table_stat["n_dead_tup"],
                collected_at,
                collected_at,
            ),
        )
        if progress:
            progress("persistence", f"Saved table statistics {number}/{len(table_stats)}.")
        table_id = str(cursor.fetchone()[0])
        table_ids[table_stat["table_name"]] = table_id
        cursor.execute(
            """
            INSERT INTO table_stat_snapshots (
                run_id, database_table_id, collected_at, seq_scan, idx_scan, n_live_tup, n_dead_tup
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                table_id,
                collected_at,
                table_stat["seq_scan"],
                table_stat["idx_scan"],
                table_stat["n_live_tup"],
                table_stat["n_dead_tup"],
            ),
        )

    for query in statistics.get("query_stats", []):
        cursor.execute(
            """
            INSERT INTO query_stat_snapshots (
                run_id, query_text, calls, total_exec_time_ms, mean_exec_time_ms, rows_returned
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                query["query"][:16384],
                query["calls"],
                query["total_exec_time"],
                query["mean_exec_time"],
                query["rows_returned"],
            ),
        )
    for index in statistics.get("index_stats", []):
        cursor.execute(
            """
            INSERT INTO index_stat_snapshots (
                run_id, database_table_id, index_name, idx_scan, idx_tup_read, idx_tup_fetch
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                table_ids.get(index["table_name"]),
                index["index_name"],
                index["idx_scan"],
                index["idx_tup_read"],
                index["idx_tup_fetch"],
            ),
        )
    for lock in statistics.get("lock_stats", []):
        cursor.execute(
            """
            INSERT INTO lock_snapshots (run_id, pid, lock_type, relation_name, mode, granted)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (run_id, lock["pid"], lock["lock_type"], lock["relation"], lock["mode"], lock["granted"]),
        )


def _persist_schema(
    cursor: Any,
    run_id: str,
    connection_id: str,
    schema: dict[str, Any],
    report: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> str:
    fingerprint = _fingerprint(schema)
    visualization = _ok_data(report, "schema_visualization")
    mermaid = visualization if isinstance(visualization, str) else ""
    tables = schema.get("tables", [])
    for number, table in enumerate(tables, start=1):
        cursor.execute(
            """
            INSERT INTO database_tables (
                monitored_database_id, schema_name, table_name, table_type,
                estimated_rows, schema_collected_at, last_seen_at
            ) VALUES (%s, %s, %s, %s, %s, now(), now())
            ON CONFLICT (monitored_database_id, schema_name, table_name) WHERE removed_at IS NULL
            DO UPDATE SET table_type = EXCLUDED.table_type,
                          estimated_rows = EXCLUDED.estimated_rows,
                          schema_collected_at = EXCLUDED.schema_collected_at,
                          last_seen_at = now()
            """,
            (
                connection_id,
                table["schema_name"],
                table["table_name"],
                table["table_type"],
                table["estimated_rows"],
            ),
        )
        if progress:
            progress("persistence", f"Saved schema table {number}/{len(tables)}.")
    cursor.execute(
        """
        INSERT INTO schema_revisions (
            monitored_database_id, first_seen_run_id, fingerprint, schema_json, mermaid_erd
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (monitored_database_id, fingerprint)
        DO UPDATE SET mermaid_erd = EXCLUDED.mermaid_erd
        RETURNING id
        """,
        (connection_id, run_id, fingerprint, Json(schema), mermaid),
    )
    return str(cursor.fetchone()[0])


def _table_summary_input(table: dict[str, Any], schema: dict[str, Any]) -> TableSummaryInput:
    table_name = table["table_name"]
    return TableSummaryInput(
        table_name=table_name,
        table_columns=[
            f"{column['column_name']} ({column['data_type']})"
            for column in schema.get("columns", [])
            if column["table_name"] == table_name
        ],
        relationships=[
            f"{key['source_table']}.{key['source_column']} -> {key['target_table']}.{key['target_column']}"
            for key in schema.get("foreign_keys", [])
            if table_name in (key["source_table"], key["target_table"])
        ],
    )


def _persist_table_summaries(
    cursor: Any,
    connection_id: str,
    run_id: str,
    schema_revision_id: str,
    schema: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> None:
    tables = schema.get("tables", [])
    agent = TableBusinessSummaryAgent()
    for number, table in enumerate(tables, start=1):
        name = f"{table['schema_name']}.{table['table_name']}"
        cursor.execute(
            """
            SELECT id FROM database_tables
            WHERE monitored_database_id = %s AND schema_name = %s AND table_name = %s
              AND removed_at IS NULL
            """,
            (connection_id, table["schema_name"], table["table_name"]),
        )
        database_table_id = str(cursor.fetchone()[0])
        if progress:
            progress("summaries", f"Summarizing table {number}/{len(tables)}: {name}.")
        try:
            summary = agent.summarize(_table_summary_input(table, schema))
        except Exception as exc:
            cursor.execute(
                """
                UPDATE database_tables
                SET summary_status = 'failed'
                WHERE monitored_database_id = %s AND schema_name = %s AND table_name = %s
                """,
                (connection_id, table["schema_name"], table["table_name"]),
            )
            cursor.execute(
                """
                INSERT INTO table_summaries (
                    database_table_id, schema_revision_id, run_id, summary, status, error_message
                ) VALUES (%s, %s, %s, '', 'failed', %s)
                ON CONFLICT (database_table_id, schema_revision_id)
                DO UPDATE SET run_id = EXCLUDED.run_id, status = EXCLUDED.status,
                              error_message = EXCLUDED.error_message, created_at = now()
                """,
                (database_table_id, schema_revision_id, run_id, f"{type(exc).__name__}: {exc}"[:1000]),
            )
            if progress:
                progress("summaries", f"Table {number}/{len(tables)} failed: {type(exc).__name__}.")
            continue
        cursor.execute(
            """
            UPDATE database_tables
            SET business_summary = %s, summary_status = 'ready', summary_generated_at = now()
            WHERE monitored_database_id = %s AND schema_name = %s AND table_name = %s
            """,
            (summary, connection_id, table["schema_name"], table["table_name"]),
        )
        cursor.execute(
            """
            INSERT INTO table_summaries (
                database_table_id, schema_revision_id, run_id, summary, status, prompt_version
            ) VALUES (%s, %s, %s, %s, 'ready', 'v1')
            ON CONFLICT (database_table_id, schema_revision_id)
            DO UPDATE SET run_id = EXCLUDED.run_id, summary = EXCLUDED.summary,
                          status = EXCLUDED.status, error_message = NULL, created_at = now()
            """,
            (database_table_id, schema_revision_id, run_id, summary),
        )
        if progress:
            progress("summaries", f"Saved table summary {number}/{len(tables)}: {name}.")


def _persist_health_checks(
    cursor: Any,
    run_id: str,
    health_checks: list[dict[str, Any]],
    progress: ProgressCallback | None = None,
) -> None:
    for number, finding in enumerate(health_checks, start=1):
        cursor.execute(
            """
            INSERT INTO health_findings (
                run_id, check_name, severity, message, recommended_action
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                run_id,
                finding["check"],
                finding["severity"],
                finding["message"],
                finding.get("action"),
            ),
        )
        if progress:
            progress("persistence", f"Saved health finding {number}/{len(health_checks)}.")


def _ok_data(report: dict[str, Any], name: str) -> Any | None:
    section = report.get(name, {})
    return section.get("data") if section.get("status") == "ok" else None


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
