"""Persist and retrieve analysis runs for monitored databases."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Any

import psycopg2
from fastapi import HTTPException, status
from psycopg2.extras import Json, execute_values

from src.agent import TableBusinessSummaryAgent, TableSummaryInput
from src.agent.business_intelligence.analysis_agent import AnalysisAgent
from src.agent.health.executive_summary_agent import ExecutiveSummaryAgent
from src.agent.kpi import generate_kpis
from src.agent.kpi.repository import KPIRepository
from src.models.business_intelligence.investigation_plan import InvestigationPlan
from src.models.business_intelligence.sql_result import SQLResult
from .brief import collect_brief
from .resource_cache import invalidate, publish_preview, warm_json
from v1 import build_report


ConnectionProvider = Callable[[], Any]
ProgressCallback = Callable[[str, str], None]
SectionCallback = Callable[[str, dict[str, Any]], None]
_progress_events: dict[str, list[dict[str, str]]] = {}
_progress_lock = Lock()


def _json(value: Any) -> Json:
    return Json(value, dumps=lambda data: json.dumps(data, default=str))


def get_analysis_progress(run_id: str, offset: int) -> tuple[list[dict[str, str]], int]:
    """Read durable progress first; the fallback only supports old, unmigrated installs."""
    try:
        with _app_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id, stage, message FROM analysis_run_events
                       WHERE analysis_run_id = %s AND id > %s ORDER BY id""",
                    (run_id, offset),
                )
                rows = cursor.fetchall()
        if rows:
            return ([{"stage": str(row[1]), "message": str(row[2])} for row in rows], int(rows[-1][0]))
        return [], offset
    except (HTTPException, psycopg2.Error):
        pass
    with _progress_lock:
        events = _progress_events.get(run_id, [])
        return events[offset:], len(events)


def _record_progress(run_id: str, stage: str, message: str) -> None:
    try:
        with _app_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO analysis_run_events (analysis_run_id, stage, message)
                       VALUES (%s, %s, %s)""",
                    (run_id, stage, message[:1_000]),
                )
        return
    except (HTTPException, psycopg2.Error):
        pass
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


def create_analysis_run(connection_id: str, trigger: str, collection_kind: str = "dashboard") -> str:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO analysis_runs (monitored_database_id, trigger, collection_kind)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (connection_id, trigger, collection_kind),
            )
            return str(cursor.fetchone()[0])


def create_collection_schedules(connection_id: str) -> None:
    """Install the default low-cost collection cadence once per connection."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO collection_schedules
                       (monitored_database_id, collection_kind, interval_seconds, next_scheduled_at)
                   VALUES (%s, %s, %s, now() + make_interval(secs => %s))
                   ON CONFLICT (monitored_database_id, collection_kind) DO NOTHING""",
                ((connection_id, "brief", 900, 900), (connection_id, "dashboard", 86_400, 86_400)),
            )


def claim_due_collection_runs(limit: int = 10) -> list[tuple[str, str, str]]:
    """Atomically turn due schedules into queued runs for one worker."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE analysis_runs
                SET status = 'queued', started_at = NULL, lease_expires_at = NULL
                WHERE trigger = 'scheduled' AND status = 'running'
                  AND lease_expires_at < now() AND attempt_count < 3
                RETURNING id, monitored_database_id, collection_kind
                """
            )
            recovered = [(str(row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()]
            cursor.execute(
                """
                UPDATE analysis_runs
                SET status = 'failed', finished_at = now(), lease_expires_at = NULL,
                    error_code = 'lease_expired', error_message = 'Worker lease expired after three attempts.'
                WHERE trigger = 'scheduled' AND status = 'running'
                  AND lease_expires_at < now() AND attempt_count >= 3
                """
            )
            cursor.execute(
                """
                WITH due AS (
                    SELECT monitored_database_id, collection_kind, interval_seconds
                    FROM collection_schedules
                    WHERE enabled AND next_scheduled_at <= now()
                    ORDER BY next_scheduled_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                ), advanced AS (
                    UPDATE collection_schedules schedule
                    SET next_scheduled_at = now() + make_interval(secs => due.interval_seconds)
                    FROM due
                    WHERE schedule.monitored_database_id = due.monitored_database_id
                      AND schedule.collection_kind = due.collection_kind
                    RETURNING due.monitored_database_id, due.collection_kind
                )
                INSERT INTO analysis_runs (monitored_database_id, trigger, collection_kind)
                SELECT monitored_database_id, 'scheduled', collection_kind FROM advanced
                RETURNING id, monitored_database_id, collection_kind
                """,
                (limit,),
            )
            return recovered + [(str(row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()]


def run_scheduled_collection(run_id: str, connection_id: str, collection_kind: str) -> None:
    """Execute one previously claimed schedule without relying on web-process memory."""
    from .connection_repository import load_worker_connection_credentials

    try:
        credentials = load_worker_connection_credentials(connection_id)
        run_analysis_in_background(
            run_id,
            connection_id,
            str(credentials["database"]),
            lambda: psycopg2.connect(**credentials, connect_timeout=10),
            collection_kind,
        )
    except Exception as exc:
        _record_progress(run_id, "error", f"{type(exc).__name__}: {exc}")
        _mark_failed(run_id, f"{type(exc).__name__}: {exc}")


def has_active_analysis(connection_id: str) -> bool:
    """Check if any analysis run is currently queued or running for this connection."""
    try:
        with _app_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM analysis_runs
                       WHERE monitored_database_id = %s AND status IN ('queued', 'running')
                       LIMIT 1""",
                    (connection_id,),
                )
                return cursor.fetchone() is not None
    except (HTTPException, psycopg2.Error):
        return False


def prune_database_history(connection_id: str) -> None:
    """Keep detailed operational data for 30 days after the daily deep run."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO database_stat_daily_rollups (
                    monitored_database_id, collected_on, avg_num_connections,
                    max_database_size_mb, avg_cache_hit_ratio
                )
                SELECT run.monitored_database_id, snapshot.collected_at::date,
                       avg(snapshot.num_connections), max(snapshot.database_size_mb),
                       avg(snapshot.cache_hit_ratio)
                FROM database_stat_snapshots snapshot
                JOIN analysis_runs run ON run.id = snapshot.run_id
                WHERE run.monitored_database_id = %s
                  AND snapshot.collected_at < now() - interval '30 days'
                GROUP BY run.monitored_database_id, snapshot.collected_at::date
                ON CONFLICT (monitored_database_id, collected_on) DO UPDATE SET
                    avg_num_connections = EXCLUDED.avg_num_connections,
                    max_database_size_mb = EXCLUDED.max_database_size_mb,
                    avg_cache_hit_ratio = EXCLUDED.avg_cache_hit_ratio
                """,
                (connection_id,),
            )
            cursor.execute(
                """DELETE FROM kpi_snapshots
                   WHERE monitored_database_id = %s AND created_at < now() - interval '30 days'""",
                (connection_id,),
            )
            cursor.execute(
                """DELETE FROM analysis_runs
                   WHERE monitored_database_id = %s
                     AND status IN ('succeeded', 'failed', 'cancelled')
                     AND finished_at < now() - interval '30 days'""",
                (connection_id,),
            )


def collect_analysis(
    run_id: str,
    connection_id: str,
    database_name: str,
    connection_provider: ConnectionProvider,
    progress: ProgressCallback | None = None,
    collection_kind: str = "dashboard",
    section_ready: SectionCallback | None = None,
) -> dict[str, Any]:
    """Collect a target-database report without app-database snapshot writes."""
    _set_running(run_id)
    started = time.monotonic()
    try:
        sections = {
            "dashboard": {"statistics", "schema", "health_checks"},
            "brief": set(),
            "statistics": {"statistics"},
            "slow_queries": {"statistics"},
            "schema": {"schema"},
            "health_checks": {"health_checks"},
            "table_summaries": {"schema"},
        }[collection_kind]
        if collection_kind == "brief":
            report = {"brief": {"status": "ok", "data": collect_brief(connection_provider, progress)}}
        else:
            report = build_report(database_name, connection_provider, progress, sections, section_ready)
        _record_collection_metric(run_id, "collection", int((time.monotonic() - started) * 1000), len(json.dumps(report, default=str)))
        return report
    except Exception as exc:
        _mark_failed(run_id, f"{type(exc).__name__}: {exc}")
        raise


def persist_collected_analysis(
    run_id: str, connection_id: str, report: dict[str, Any], collection_kind: str,
    progress: ProgressCallback | None = None,
) -> None:
    """Persist an already-collected report; called synchronously or by the Redis worker."""
    if progress:
        progress("persistence", "Saving analysis results.")
    if collection_kind == "brief":
        _persist_brief(run_id, connection_id, report)
    else:
        _persist_report(run_id, connection_id, report, progress, collection_kind)
    if progress:
        progress("persistence", "Analysis results saved.")


def run_post_persist_enrichment(
    connection_id: str,
    run_id: str,
    report: dict[str, Any],
    connection_provider: ConnectionProvider,
) -> None:
    """Run optional enrichment only after the durable snapshot has committed."""
    schema = _ok_data(report, "schema")
    try:
        generated = generate_kpis(
            connection_id, connection_provider,
            lambda stage, message: _record_progress(run_id, stage, message), run_id,
        )
        _record_progress(run_id, "kpis", f"KPI generation completed: {generated} metrics.")
    except Exception as exc:
        _record_progress(run_id, "kpis", f"KPI generation failed: {type(exc).__name__}.")
    try:
        _generate_agent_reports(connection_id, run_id, report)
        _record_progress(run_id, "agents", "VoyagerAI Developer and BI reports saved.")
    except Exception as exc:
        _record_progress(run_id, "agents", f"VoyagerAI reports skipped: {type(exc).__name__}.")
    if schema is not None:
        try:
            _generate_table_summaries(
                connection_id, run_id, schema,
                lambda stage, message: _record_progress(run_id, stage, message),
            )
        except Exception as exc:
            _record_progress(run_id, "summaries", f"Deferred summaries skipped: {type(exc).__name__}.")
    try:
        prune_database_history(connection_id)
    except Exception as exc:
        _record_progress(run_id, "retention", f"Retention deferred: {type(exc).__name__}.")


def _generate_agent_reports(connection_id: str, run_id: str, report: dict[str, Any]) -> None:
    """Reuse the existing BI analysis agent over already-persisted, bounded snapshots."""
    health = _ok_data(report, "health_checks") or []
    statistics = _ok_data(report, "statistics") or {}
    severity = "critical" if any(item.get("severity") == "critical" for item in health) else "warning" if any(item.get("severity") == "warning" for item in health) else "info"
    repository = KPIRepository()
    definitions = repository.list_definitions(connection_id)
    snapshots = repository.latest_snapshots(connection_id)
    reports = {
        "developer": ("Developer technical report", {"health_findings": health[:10], "slow_queries": statistics.get("query_stats", [])[:10], "database_stats": statistics.get("database_stats", {})}),
        "bi": ("BI KPI report", {"kpis": [{"title": item.title, "aggregation": item.aggregation, "points": snapshots.get(item.id, {}).get("points", [])[:12]} for item in definitions[:20]]}),
    }
    for kind, (title, payload) in reports.items():
        if kind == "developer":
            summary = ExecutiveSummaryAgent().summarize(100 if severity == "info" else 70 if severity == "warning" else 40, health)
            evidence, recommendations = [str(item.get("message", item.get("check", "Finding"))) for item in health[:10]], ["Review the linked health checks and slow-query snapshots before applying any change."]
        else:
            insight = AnalysisAgent().analyze(
                "Create a business recommendation-only report from these persisted KPI snapshots.",
                InvestigationPlan(question=title, tables=[], metrics=[], dimensions=[]),
                [SQLResult(sql="PERSISTED SNAPSHOT — DO NOT EXECUTE", rows=[payload])],
            )
            summary, evidence, recommendations = insight.summary, insight.evidence, insight.recommendations
        saved = _save_agent_report(connection_id, run_id, kind, title, severity, {"summary": summary[:2000], "evidence": evidence[:10], "recommendations": recommendations[:10]})
        from .notifications import AgentNotification, create_notification_for_connection
        create_notification_for_connection(AgentNotification(connection_id=connection_id, idempotency_key=f"voyagerai:{kind}:{run_id}", severity=severity, title=f"VoyagerAI · {kind.title()}", body=summary[:2000], metadata={"agent_kind": kind, "report_id": saved, "source_run_id": run_id}))


def _save_agent_report(connection_id: str, run_id: str, kind: str, title: str, severity: str, payload: dict[str, Any]) -> str:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO agent_reports (monitored_database_id, analysis_run_id, agent_kind, title, severity, report_json)
                              VALUES (%s, %s, %s, %s, %s, %s)
                              ON CONFLICT (monitored_database_id, analysis_run_id, agent_kind)
                              DO UPDATE SET title = EXCLUDED.title, severity = EXCLUDED.severity, report_json = EXCLUDED.report_json
                              RETURNING id""", (connection_id, run_id, kind, title, severity, _json(payload)))
            return str(cursor.fetchone()[0])


def run_analysis(
    run_id: str, connection_id: str, database_name: str, connection_provider: ConnectionProvider,
    progress: ProgressCallback | None = None, collection_kind: str = "dashboard",
) -> dict[str, Any]:
    """Compatibility path for callers that require collection and persistence together."""
    report = collect_analysis(run_id, connection_id, database_name, connection_provider, progress, collection_kind)
    try:
        persist_collected_analysis(run_id, connection_id, report, collection_kind, progress)
        return report
    except Exception as exc:
        _mark_failed(run_id, f"{type(exc).__name__}: {exc}")
        raise


def _record_collection_metric(run_id: str, stage: str, duration_ms: int, payload_bytes: int) -> None:
    try:
        with _app_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO collection_metrics (analysis_run_id, stage, duration_ms, payload_bytes)
                       VALUES (%s, %s, %s, %s)""",
                    (run_id, stage, duration_ms, payload_bytes),
                )
    except (HTTPException, psycopg2.Error):
        return


def run_analysis_in_background(
    run_id: str,
    connection_id: str,
    database_name: str,
    connection_provider: ConnectionProvider,
    collection_kind: str = "dashboard",
) -> None:
    try:
        _record_progress(run_id, "analysis", "Starting database analysis.")
        report = collect_analysis(
            run_id,
            connection_id,
            database_name,
            connection_provider,
            lambda stage, message: _record_progress(run_id, stage, message),
            collection_kind,
        )
        if publish_preview(connection_id, run_id, collection_kind, report):
            _record_progress(run_id, "data_ready", "Collected data is ready for the dashboard.")
            return
        persist_collected_analysis(run_id, connection_id, report, collection_kind, lambda stage, message: _record_progress(run_id, stage, message))
        if collection_kind == "dashboard":
            run_post_persist_enrichment(connection_id, run_id, report, connection_provider)
        _record_progress(run_id, "analysis", "Analysis report persisted.")
    except Exception as exc:
        _record_progress(run_id, "error", f"{type(exc).__name__}: {exc}")


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
                  AND runs.status = 'succeeded' AND runs.collection_kind = 'dashboard'
                ORDER BY runs.finished_at DESC
                LIMIT 1
                """,
                (connection_id, auth_subject),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No completed dashboard report found")
    return row[0]


def get_latest_collection_report(connection_id: str, auth_subject: str, collection_kind: str) -> dict[str, Any]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT runs.report_json FROM analysis_runs AS runs
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE runs.monitored_database_id = %s AND users.auth_subject = %s
                  AND runs.status = 'succeeded' AND runs.collection_kind = %s
                ORDER BY runs.finished_at DESC LIMIT 1
            """, (connection_id, auth_subject, collection_kind))
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No completed {collection_kind} report found")
    return row[0]


def get_latest_statistics(connection_id: str, auth_subject: str) -> dict[str, Any]:
    """Build the statistics response from compact persisted snapshot rows."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT snapshot.run_id, snapshot.collected_at, snapshot.num_connections,
                       snapshot.database_size_mb, snapshot.cache_hit_ratio
                FROM database_stat_snapshots snapshot
                JOIN analysis_runs run ON run.id = snapshot.run_id
                JOIN monitored_databases database ON database.id = run.monitored_database_id
                JOIN users ON users.id = database.owner_user_id
                WHERE run.monitored_database_id = %s AND users.auth_subject = %s
                ORDER BY snapshot.collected_at DESC LIMIT 1
                """,
                (connection_id, auth_subject),
            )
            snapshot = cursor.fetchone()
            if snapshot is None:
                raise HTTPException(status_code=404, detail="No completed statistics report found")
            run_id = snapshot[0]
            cursor.execute(
                """SELECT query_text, calls, total_exec_time_ms, mean_exec_time_ms, rows_returned
                   FROM query_stat_snapshots WHERE run_id = %s
                   ORDER BY total_exec_time_ms DESC LIMIT 100""",
                (run_id,),
            )
            queries = cursor.fetchall()
            cursor.execute(
                """SELECT database_table.table_name, snapshot.seq_scan, snapshot.idx_scan,
                          snapshot.n_live_tup, snapshot.n_dead_tup
                   FROM table_stat_snapshots snapshot
                   JOIN database_tables database_table ON database_table.id = snapshot.database_table_id
                   WHERE snapshot.run_id = %s ORDER BY snapshot.seq_scan DESC LIMIT 200""",
                (run_id,),
            )
            tables = cursor.fetchall()
            cursor.execute(
                """SELECT COALESCE(database_table.table_name, ''), snapshot.index_name, snapshot.idx_scan,
                          snapshot.idx_tup_read, snapshot.idx_tup_fetch
                   FROM index_stat_snapshots snapshot
                   LEFT JOIN database_tables database_table ON database_table.id = snapshot.database_table_id
                   WHERE snapshot.run_id = %s ORDER BY snapshot.idx_scan DESC LIMIT 200""",
                (run_id,),
            )
            indexes = cursor.fetchall()
            cursor.execute(
                """SELECT pid, lock_type, relation_name, mode, granted
                   FROM lock_snapshots WHERE run_id = %s ORDER BY granted, pid LIMIT 100""",
                (run_id,),
            )
            locks = cursor.fetchall()
    return {
        "database_stats": {
            "num_connections": snapshot[2], "database_size_mb": snapshot[3], "cache_hit_ratio": snapshot[4],
        },
        "query_stats": [
            {"query": row[0], "calls": row[1], "total_exec_time": row[2], "mean_exec_time": row[3], "rows_returned": row[4]}
            for row in queries
        ],
        "table_stats": [
            {"table_name": row[0], "seq_scan": row[1], "idx_scan": row[2], "n_live_tup": row[3], "n_dead_tup": row[4]}
            for row in tables
        ],
        "index_stats": [
            {"table_name": row[0], "index_name": row[1], "idx_scan": row[2], "idx_tup_read": row[3], "idx_tup_fetch": row[4]}
            for row in indexes
        ],
        "lock_stats": [
            {"pid": row[0], "lock_type": row[1], "relation": row[2], "mode": row[3], "granted": row[4]}
            for row in locks
        ],
    }


def get_latest_health_findings(connection_id: str, auth_subject: str) -> list[dict[str, Any]]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT finding.id, finding.check_name, finding.severity, finding.message,
                       finding.recommended_action, finding.details, finding.user_state, finding.user_note
                FROM health_findings finding
                JOIN analysis_runs run ON run.id = finding.run_id
                JOIN monitored_databases database ON database.id = run.monitored_database_id
                JOIN users ON users.id = database.owner_user_id
                WHERE finding.run_id = (
                    SELECT latest.id FROM analysis_runs latest
                    WHERE latest.monitored_database_id = %s AND latest.status = 'succeeded'
                    ORDER BY latest.finished_at DESC LIMIT 1
                ) AND users.auth_subject = %s
                ORDER BY CASE finding.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, finding.created_at
                """,
                (connection_id, auth_subject),
            )
            rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No completed health-check report found")
    return [
        {"id": str(row[0]), "check": row[1], "severity": row[2], "message": row[3], "action": row[4],
         "details": row[5], "user_state": row[6], "user_note": row[7]}
        for row in rows
    ]


def get_current_schema(connection_id: str, auth_subject: str) -> dict[str, Any]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT revision.schema_json
                   FROM monitored_databases database
                   JOIN users ON users.id = database.owner_user_id
                   JOIN schema_revisions revision ON revision.id = database.current_schema_revision_id
                   WHERE database.id = %s AND users.auth_subject = %s""",
                (connection_id, auth_subject),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No collected schema found")
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


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


def list_analysis_runs(connection_id: str, auth_subject: str, limit: int = 20) -> list[dict[str, Any]]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT runs.id, runs.status, runs.trigger, runs.collection_kind,
                       runs.created_at, runs.started_at, runs.finished_at,
                       runs.error_code, runs.error_message,
                       (SELECT count(*) FROM analysis_run_events WHERE analysis_run_id = runs.id) AS event_count
                FROM analysis_runs AS runs
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE runs.monitored_database_id = %s AND users.auth_subject = %s
                ORDER BY runs.created_at DESC
                LIMIT %s
                """,
                (connection_id, auth_subject, limit),
            )
            rows = cursor.fetchall()
    return [
        {
            "id": str(row[0]),
            "status": row[1],
            "trigger": row[2],
            "collection_kind": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "started_at": row[5].isoformat() if row[5] else None,
            "finished_at": row[6].isoformat() if row[6] else None,
            "error_code": row[7],
            "error_message": row[8],
            "event_count": row[9],
        }
        for row in rows
    ]


def list_analysis_run_events(connection_id: str, run_id: str, auth_subject: str, offset: int = 0) -> list[dict[str, Any]]:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT events.id, events.stage, events.message, events.created_at
                FROM analysis_run_events AS events
                JOIN analysis_runs AS runs ON runs.id = events.analysis_run_id
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE events.analysis_run_id = %s
                  AND runs.monitored_database_id = %s
                  AND users.auth_subject = %s
                  AND events.id > %s
                ORDER BY events.id
                """,
                (run_id, connection_id, auth_subject, offset),
            )
            rows = cursor.fetchall()
    return [
        {"id": row[0], "stage": row[1], "message": row[2], "created_at": row[3].isoformat() if row[3] else None}
        for row in rows
    ]


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


def get_latest_slow_queries(connection_id: str, auth_subject: str, limit: int) -> list[dict[str, Any]]:
    """Return persisted slow queries for one owned database."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT snapshots.id, snapshots.query_text, snapshots.calls,
                       snapshots.total_exec_time_ms, snapshots.mean_exec_time_ms,
                       snapshots.rows_returned, runs.finished_at
                FROM query_stat_snapshots AS snapshots
                JOIN analysis_runs AS runs ON runs.id = snapshots.run_id
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE runs.monitored_database_id = %s
                  AND users.auth_subject = %s
                  AND runs.status = 'succeeded'
                ORDER BY runs.finished_at DESC, snapshots.total_exec_time_ms DESC
                LIMIT %s
                """,
                (connection_id, auth_subject, limit),
            )
            rows = cursor.fetchall()
    return [
        {
            "query_id": str(row[0]), "query": row[1], "calls": row[2],
            "total_exec_time": row[3], "mean_exec_time": row[4],
            "rows_returned": row[5], "collected_at": row[6],
        }
        for row in rows
    ]


def get_slow_query(connection_id: str, auth_subject: str, query_id: str) -> str:
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT snapshots.query_text
                FROM query_stat_snapshots AS snapshots
                JOIN analysis_runs AS runs ON runs.id = snapshots.run_id
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE snapshots.id = %s AND runs.monitored_database_id = %s
                  AND users.auth_subject = %s
                """,
                (query_id, connection_id, auth_subject),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Slow query not found")
    return str(row[0])


def get_slow_query_detail(connection_id: str, auth_subject: str, query_id: str) -> dict[str, Any]:
    """Return one persisted slow-query snapshot, scoped to its owner."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT snapshots.id, snapshots.query_text, snapshots.calls,
                       snapshots.total_exec_time_ms, snapshots.mean_exec_time_ms,
                       snapshots.rows_returned, runs.finished_at, databases.cache_hit_ratio
                FROM query_stat_snapshots AS snapshots
                JOIN analysis_runs AS runs ON runs.id = snapshots.run_id
                JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE snapshots.id = %s
                  AND runs.monitored_database_id = %s
                  AND users.auth_subject = %s
                """,
                (query_id, connection_id, auth_subject),
            )
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Slow query not found")
    return {
        "query_id": str(row[0]),
        "query": row[1],
        "calls": row[2],
        "total_exec_time": row[3],
        "mean_exec_time": row[4],
        "rows_returned": row[5],
        "collected_at": row[6],
        "cache_hit_ratio": row[7],
    }


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


def _persist_brief(run_id: str, connection_id: str, report: dict[str, Any]) -> None:
    brief = report["brief"]["data"]
    database = brief["database_stats"]
    overview = {
        "generated_at": datetime.now(UTC).isoformat(),
        "health_summary": {severity: sum(item["severity"] == severity for item in brief["insights"])
                           for severity in ("critical", "warning", "info")},
        "database_stats": database,
        "top_slow_queries": brief["queries"][:5],
        "table_count": len(brief["tables"]),
        "insights": brief["insights"],
        "query_telemetry_available": brief["query_telemetry_available"],
    }
    etag = hashlib.sha256(json.dumps(overview, sort_keys=True, default=str).encode()).hexdigest()
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE monitored_databases SET num_connections = %s, database_size_mb = %s,
                              cache_hit_ratio = %s, last_collected_at = now(), last_successful_run_id = %s WHERE id = %s""",
                           (database.get("num_connections"), database.get("database_size_mb"), database.get("cache_hit_ratio"), run_id, connection_id))
            cursor.execute("""UPDATE analysis_runs SET status = 'succeeded', finished_at = now(), lease_expires_at = NULL,
                              report_json = %s WHERE id = %s""", (_json(report), run_id))
            cursor.execute(
                """INSERT INTO dashboard_summaries (monitored_database_id, analysis_run_id, overview_json, etag)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (monitored_database_id) DO UPDATE SET analysis_run_id = EXCLUDED.analysis_run_id,
                       overview_json = EXCLUDED.overview_json, etag = EXCLUDED.etag, updated_at = now()""",
                (connection_id, run_id, _json(overview), etag),
            )
            cursor.execute(
                """INSERT INTO dashboard_resources (
                       monitored_database_id, resource, analysis_run_id, etag, payload_json, generated_at
                   ) VALUES (%s, 'overview', %s, %s, %s, now())
                   ON CONFLICT (monitored_database_id, resource) DO UPDATE SET
                       analysis_run_id = EXCLUDED.analysis_run_id, etag = EXCLUDED.etag,
                       payload_json = EXCLUDED.payload_json, generated_at = EXCLUDED.generated_at,
                       version = dashboard_resources.version + 1, updated_at = now()""",
                (connection_id, run_id, etag, _json(overview)),
            )
    warm_json(connection_id, "overview", overview)


def get_dashboard_summary(connection_id: str, auth_subject: str) -> tuple[dict[str, Any], str] | None:
    try:
        with _app_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT resources.payload_json, resources.etag FROM dashboard_resources AS resources
                       JOIN monitored_databases AS databases ON databases.id = resources.monitored_database_id
                       JOIN users ON users.id = databases.owner_user_id
                       WHERE resources.monitored_database_id = %s AND resources.resource = 'overview'
                         AND users.auth_subject = %s
                         AND databases.deleted_at IS NULL""",
                    (connection_id, auth_subject),
                )
                row = cursor.fetchone()
    except psycopg2.errors.UndefinedTable:
        row = None
    if row is None:
        try:
            with _app_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT summaries.overview_json, summaries.etag FROM dashboard_summaries AS summaries
                           JOIN monitored_databases AS databases ON databases.id = summaries.monitored_database_id
                           JOIN users ON users.id = databases.owner_user_id
                           WHERE summaries.monitored_database_id = %s AND users.auth_subject = %s
                             AND databases.deleted_at IS NULL""",
                        (connection_id, auth_subject),
                    )
                    row = cursor.fetchone()
        except psycopg2.errors.UndefinedTable:
            return None
    return (row[0], str(row[1])) if row else None


def _persist_report(
    run_id: str,
    connection_id: str,
    report: dict[str, Any],
    progress: ProgressCallback | None = None,
    collection_kind: str = "dashboard",
) -> None:
    statistics = _ok_data(report, "statistics")
    schema = _ok_data(report, "schema")
    health_checks = _ok_data(report, "health_checks")
    generated_at = report.get("generated_at") or datetime.now(UTC).isoformat()
    complete = (
        statistics is not None and schema is not None
        if collection_kind in {"dashboard", "health_checks"}
        else (statistics is not None if collection_kind in {"statistics", "slow_queries"} else schema is not None)
    )

    with _app_connection() as connection:
        with connection.cursor() as cursor:
            schema_revision_id = None
            if schema is not None:
                schema_revision_id = _persist_schema(cursor, run_id, connection_id, schema, report, progress)
                if collection_kind == "table_summaries":
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
                    _json(report),
                    schema_revision_id,
                    _fingerprint(schema) if schema is not None else None,
                    None if complete else "collection_incomplete",
                    None if complete else "Statistics and schema collection must both succeed",
                    run_id,
                ),
            )
            if progress:
                progress("persistence", "Finalized analysis run status.")

    resources = ["overview"]
    if health_checks is not None:
        resources.extend(("health-checks", "insights"))
    if statistics is not None:
        resources.append("slow-queries")
    if schema is not None:
        resources.extend(("schema", "optimization", "bi"))
    invalidate(connection_id, *resources)


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
    table_rows: list[tuple[Any, ...]] = []
    for table_stat in statistics.get("table_stats", []):
        table = table_metadata.get(("public", table_stat["table_name"]))
        if table is None:
            continue
        table_rows.append((
            connection_id, table["schema_name"], table["table_name"], table["table_type"],
            table["estimated_rows"], table_stat["seq_scan"], table_stat["idx_scan"],
            table_stat["n_live_tup"], table_stat["n_dead_tup"], collected_at,
        ))

    table_ids: dict[str, str] = {}
    if table_rows:
        execute_values(cursor, """
            INSERT INTO database_tables (
                monitored_database_id, schema_name, table_name, table_type, estimated_rows,
                seq_scan, idx_scan, n_live_tup, n_dead_tup, stats_collected_at,
                schema_collected_at, last_seen_at
            ) VALUES %s
            ON CONFLICT (monitored_database_id, schema_name, table_name) WHERE removed_at IS NULL
            DO UPDATE SET table_type = EXCLUDED.table_type,
                          estimated_rows = EXCLUDED.estimated_rows,
                          seq_scan = EXCLUDED.seq_scan, idx_scan = EXCLUDED.idx_scan,
                          n_live_tup = EXCLUDED.n_live_tup, n_dead_tup = EXCLUDED.n_dead_tup,
                          stats_collected_at = EXCLUDED.stats_collected_at,
                          schema_collected_at = EXCLUDED.schema_collected_at, last_seen_at = now()
        """, table_rows, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())")
        cursor.execute(
            """SELECT id, table_name FROM database_tables
               WHERE monitored_database_id = %s AND schema_name = 'public' AND removed_at IS NULL""",
            (connection_id,),
        )
        table_ids = {str(row[1]): str(row[0]) for row in cursor.fetchall()}
        snapshot_rows = [
            (run_id, table_ids[row[2]], collected_at, row[5], row[6], row[7], row[8])
            for row in table_rows if row[2] in table_ids
        ]
        if snapshot_rows:
            execute_values(cursor, """INSERT INTO table_stat_snapshots (
                run_id, database_table_id, collected_at, seq_scan, idx_scan, n_live_tup, n_dead_tup
            ) VALUES %s""", snapshot_rows)
        if progress:
            progress("persistence", f"Saved {len(table_rows)} table statistics.")

    query_rows = [
        (run_id, query["query"][:1000], query["calls"], query["total_exec_time"], query["mean_exec_time"], query["rows_returned"])
        for query in statistics.get("query_stats", [])
    ]
    if query_rows:
        execute_values(cursor, """INSERT INTO query_stat_snapshots
            (run_id, query_text, calls, total_exec_time_ms, mean_exec_time_ms, rows_returned) VALUES %s""", query_rows)
    index_rows = [
        (run_id, table_ids.get(index["table_name"]), index["index_name"], index["idx_scan"], index["idx_tup_read"], index["idx_tup_fetch"])
        for index in statistics.get("index_stats", [])
    ]
    if index_rows:
        execute_values(cursor, """INSERT INTO index_stat_snapshots
            (run_id, database_table_id, index_name, idx_scan, idx_tup_read, idx_tup_fetch) VALUES %s""", index_rows)
    lock_rows = [
        (run_id, lock["pid"], lock["lock_type"], lock["relation"], lock["mode"], lock["granted"])
        for lock in statistics.get("lock_stats", [])
    ]
    if lock_rows:
        execute_values(cursor, """INSERT INTO lock_snapshots
            (run_id, pid, lock_type, relation_name, mode, granted) VALUES %s""", lock_rows)


def _generate_table_summaries(
    connection_id: str,
    run_id: str,
    schema: dict[str, Any],
    progress: ProgressCallback | None = None,
) -> None:
    """Run optional LLM enrichment after core collection has committed."""
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_schema_revision_id FROM monitored_databases WHERE id = %s",
                (connection_id,),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                return
            _persist_table_summaries(cursor, connection_id, run_id, str(row[0]), schema, progress)


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
    if tables:
        execute_values(cursor, """
            INSERT INTO database_tables (
                monitored_database_id, schema_name, table_name, table_type,
                estimated_rows, schema_collected_at, last_seen_at
            ) VALUES %s
            ON CONFLICT (monitored_database_id, schema_name, table_name) WHERE removed_at IS NULL
            DO UPDATE SET table_type = EXCLUDED.table_type,
                          estimated_rows = EXCLUDED.estimated_rows,
                          schema_collected_at = EXCLUDED.schema_collected_at, last_seen_at = now()
        """, [
            (connection_id, table["schema_name"], table["table_name"], table["table_type"], table["estimated_rows"])
            for table in tables
        ], template="(%s,%s,%s,%s,%s,now(),now())")
        if progress:
            progress("persistence", f"Saved {len(tables)} schema tables.")
    cursor.execute(
        """
        INSERT INTO schema_revisions (
            monitored_database_id, first_seen_run_id, fingerprint, schema_json, mermaid_erd
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (monitored_database_id, fingerprint)
        DO UPDATE SET mermaid_erd = EXCLUDED.mermaid_erd
        RETURNING id
        """,
        (connection_id, run_id, fingerprint, _json(schema), mermaid),
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
            SELECT id, summary_status FROM database_tables
            WHERE monitored_database_id = %s AND schema_name = %s AND table_name = %s
              AND removed_at IS NULL
            """,
            (connection_id, table["schema_name"], table["table_name"]),
        )
        database_table_id, summary_status = cursor.fetchone()
        if summary_status == "ready":
            if progress:
                progress("summaries", f"Skipped unchanged summary {number}/{len(tables)}: {name}.")
            continue
        database_table_id = str(database_table_id)
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
    if not health_checks:
        return
    execute_values(cursor, """
        INSERT INTO health_findings (
            run_id, check_name, severity, message, recommended_action
        ) VALUES %s
    """, [
        (run_id, finding["check"], finding["severity"], finding["message"], finding.get("action"))
        for finding in health_checks
    ])
    if progress:
        progress("persistence", f"Saved {len(health_checks)} health findings.")


def _ok_data(report: dict[str, Any], name: str) -> Any | None:
    section = report.get(name, {})
    return section.get("data") if section.get("status") == "ok" else None


def _fingerprint(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
