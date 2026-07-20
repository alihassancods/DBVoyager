"""Persistent, owner-scoped dashboard views for collected database analysis."""

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, StreamingResponse

from src.services.health.health_summary import (
    HealthSummaryService,
)

from src.agent.health.executive_summary_agent import ExecutiveSummaryAgent

from .analysis_repository import (
    _record_progress,
    create_analysis_run,
    ensure_owned_database,
    get_analysis_progress,
    get_analysis_run,
    get_dashboard_summary,
    get_current_schema,
    get_latest_health_findings,
    get_latest_collection_report,
    get_latest_report,
    get_latest_statistics,
    collect_analysis,
    persist_collected_analysis,
    run_analysis,
    run_analysis_in_background,
)
from .auth import current_user
from .store import connection_provider, get_connection, get_database_name
from .resource_cache import cached_json, invalidate
from .resource_cache import publish_preview, read_preview


router = APIRouter(prefix="/connections/{connection_id}")
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class FindingStateRequest(BaseModel):
    user_state: Literal["open", "acknowledged", "muted"]
    user_note: str | None = Field(default=None, max_length=1_000)


def _owner_subject(user: dict[str, object]) -> str:
    return str(user["sub"])


def _report(connection_id: str, user: dict[str, object]) -> dict[str, Any]:
    return get_latest_report(connection_id, _owner_subject(user))


def _collection_report(connection_id: str, user: dict[str, object], collection_kind: str) -> dict[str, Any]:
    try:
        return get_latest_collection_report(connection_id, _owner_subject(user), collection_kind)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return _report(connection_id, user)


def _section(report: dict[str, Any], name: str) -> dict[str, Any]:
    return report[name]


def _start_manual_run(connection_id: str, user: dict[str, object]) -> tuple[str, str]:
    owner_subject = _owner_subject(user)
    ensure_owned_database(connection_id, owner_subject)
    get_connection(connection_id, owner_subject)
    return create_analysis_run(connection_id, "manual"), get_database_name(connection_id, owner_subject)


def _start_collection_run(
    connection_id: str,
    resource: Literal["brief", "statistics", "slow_queries", "schema", "health_checks", "table_summaries"],
    background_tasks: BackgroundTasks,
    user: dict[str, object],
) -> dict[str, str]:
    owner_subject = _owner_subject(user)
    ensure_owned_database(connection_id, owner_subject)
    get_connection(connection_id, owner_subject)
    run_id = create_analysis_run(connection_id, "manual", resource)
    background_tasks.add_task(
        run_analysis_in_background,
        run_id,
        connection_id,
        get_database_name(connection_id, owner_subject),
        connection_provider(connection_id, owner_subject),
        resource,
    )
    return {"run_id": run_id, "resource": resource, "status": "queued"}


@router.post("/dashboard/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_dashboard(
    connection_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    run_id, database_name = _start_manual_run(connection_id, user)
    background_tasks.add_task(
        run_analysis_in_background, run_id, connection_id, database_name,
        connection_provider(connection_id, str(user["sub"])), "dashboard",
    )
    return {"run_id": run_id, "resource": "dashboard", "status": "queued"}


@router.post("/brief/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_brief(connection_id: str, background_tasks: BackgroundTasks, user: dict[str, object] = Depends(current_user)) -> dict[str, str]:
    return _start_collection_run(connection_id, "brief", background_tasks, user)


@router.post("/statistics/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_statistics(
    connection_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    return _start_collection_run(connection_id, "statistics", background_tasks, user)


@router.post("/slow-queries/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_slow_queries(
    connection_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    return _start_collection_run(connection_id, "slow_queries", background_tasks, user)


@router.post("/schema/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_schema(
    connection_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    return _start_collection_run(connection_id, "schema", background_tasks, user)


@router.post("/health-checks/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_health_checks(
    connection_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    return _start_collection_run(connection_id, "health_checks", background_tasks, user)


@router.post("/table-summaries/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_table_summaries(
    connection_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    return _start_collection_run(connection_id, "table_summaries", background_tasks, user)


@router.get("/analysis-runs/{run_id}")
def analysis_run(
    connection_id: str,
    run_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return get_analysis_run(connection_id, run_id, _owner_subject(user))


@router.get("/collection-runs/{run_id}")
def collection_run(
    connection_id: str,
    run_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return analysis_run(connection_id, run_id, user)


@router.get("/analysis-runs/{run_id}/stream")
async def analysis_run_stream(
    connection_id: str,
    run_id: str,
    user: dict[str, object] = Depends(current_user),
) -> StreamingResponse:
    owner_subject = _owner_subject(user)
    ensure_owned_database(connection_id, owner_subject)

    async def stream() -> Any:
        offset = 0
        while True:
            events, offset = get_analysis_progress(run_id, offset)
            for event in events:
                if event["stage"] == "data_ready" and read_preview(connection_id, run_id) is not None:
                    yield _sse("data_ready", {"analysis_run_id": run_id, "preview": f"/connections/{connection_id}/collection-runs/{run_id}/preview"})
                    return
                yield _sse("progress", event)
            run = await asyncio.to_thread(get_analysis_run, connection_id, run_id, owner_subject)
            if run["status"] in {"succeeded", "failed", "cancelled"}:
                event_data = {key: value for key, value in run.items() if key != "report"}
                yield _sse("complete" if run["status"] == "succeeded" else "error", event_data)
                return
            if not events:
                yield _sse("progress", {"stage": "analysis", "message": f"Analysis is {run['status']}."})
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/collection-runs/{run_id}/stream")
async def collection_run_stream(
    connection_id: str,
    run_id: str,
    user: dict[str, object] = Depends(current_user),
) -> StreamingResponse:
    return await analysis_run_stream(connection_id, run_id, user)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/dashboard/refresh/stream")
async def refresh_dashboard_stream(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> StreamingResponse:
    run_id, database_name = _start_manual_run(connection_id, user)
    provider = connection_provider(connection_id, str(user["sub"]))

    async def stream() -> Any:
        task = asyncio.create_task(asyncio.to_thread(
            collect_analysis, run_id, connection_id, database_name, provider,
            lambda stage, state: _record_progress(run_id, stage, state),
        ))
        offset = 0
        while not task.done():
            events, offset = await asyncio.to_thread(get_analysis_progress, run_id, offset)
            for event in events:
                yield _sse("progress", {"stage": event["stage"], "status": event["message"]})
            await asyncio.sleep(0.1)
        events, offset = await asyncio.to_thread(get_analysis_progress, run_id, offset)
        for event in events:
            yield _sse("progress", {"stage": event["stage"], "status": event["message"]})
        try:
            report = task.result()
            if publish_preview(connection_id, run_id, "dashboard", report):
                _record_progress(run_id, "data_ready", "Collected data is ready for the dashboard.")
                yield _sse("data_ready", {"analysis_run_id": run_id, "preview": f"/connections/{connection_id}/collection-runs/{run_id}/preview"})
            else:
                await asyncio.to_thread(persist_collected_analysis, run_id, connection_id, report, "dashboard")
                yield _sse("complete", {"analysis_run_id": run_id, "status": "succeeded"})
        except Exception as exc:
            yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/collection-runs/{run_id}/preview")
def collection_preview(connection_id: str, run_id: str, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    ensure_owned_database(connection_id, _owner_subject(user))
    report = read_preview(connection_id, run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Live collection preview is unavailable")
    return {"analysis_run_id": run_id, "report": report}


@router.get("/dashboard")
def dashboard(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _report(connection_id, user)


@router.get("/overview")
def overview(connection_id: str, request: Request, user: dict[str, object] = Depends(current_user)) -> Any:
    summary = get_dashboard_summary(connection_id, _owner_subject(user))
    if summary:
        payload, _ = summary
        return cached_json(request, connection_id, "overview", payload)
        
    try:
        brief = get_latest_collection_report(connection_id, _owner_subject(user), "brief")["brief"]["data"]
        return {
            "generated_at": None,
            "health_summary": {severity: sum(item["severity"] == severity for item in brief["insights"]) for severity in ("critical", "warning", "info")},
            "database_stats": brief["database_stats"],
            "top_slow_queries": brief["queries"],
            "table_count": len(brief["tables"]),
            "insights": brief["insights"],
            "query_telemetry_available": brief["query_telemetry_available"]
        }
    except HTTPException as exc:
        if exc.status_code != 404:
            raise

    try:
        report = _report(connection_id, user)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"collection_status": "collecting"})

    health = _section(report, "health_checks")
    statistics = _section(report, "statistics")
    findings = health.get("data", []) if health.get("status") == "ok" else []
    stats = statistics.get("data", {}) if statistics.get("status") == "ok" else {}

    # Calculate score & top findings
    health_score = HealthSummaryService.calculate_score(findings)
    top_findings = HealthSummaryService.top_findings(findings)

    # Generate AI Executive Summary using your ExecutiveSummaryAgent
    summary_agent = ExecutiveSummaryAgent()
    executive_summary = summary_agent.summarize(
        health_score=health_score,
        findings=findings,
    )

    return {
        "generated_at": report.get("generated_at"),
        "health_summary": {
            severity: sum(item.get("severity") == severity for item in findings)
            for severity in ("critical", "warning", "info")
        },
        "database_stats": stats.get("database_stats", {}),
        "top_slow_queries": stats.get("query_stats", [])[:5],
        "table_count": len(_section(report, "schema").get("data", {}).get("tables", [])),
        "health_score": health_score,
        "top_findings": top_findings,
        "summary": executive_summary,  # <--- Integrated AI Executive Summary
    }


@router.get("/insights")
def insights(connection_id: str, request: Request, limit: int = Query(default=10, ge=1, le=50), user: dict[str, object] = Depends(current_user)) -> Response:
    report = get_latest_collection_report(connection_id, _owner_subject(user), "brief")
    return cached_json(request, connection_id, f"insights:{limit}", {"data": report["brief"]["data"]["insights"][:limit]})


@router.get("/health-checks")
def health_checks(
    connection_id: str,
    request: Request,
    severity: str | None = None,
    check: str | None = Query(default=None),
    user: dict[str, object] = Depends(current_user),
) -> Response:
    try:
        findings = get_latest_health_findings(connection_id, _owner_subject(user))
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        try:
            section = _section(_collection_report(connection_id, user, "health_checks"), "health_checks")
        except HTTPException as missing:
            if missing.status_code != 404:
                raise
            return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "collecting", "data": []})
        if section["status"] != "ok":
            return section
        findings = section["data"]
    data = [
        finding for finding in findings
        if (severity is None or finding["severity"] == severity)
        and (check is None or finding["check"] == check)
    ]
    resource = "health-checks" if severity is None and check is None else f"health-checks:{severity or 'all'}:{check or 'all'}"
    return cached_json(request, connection_id, resource, {"status": "ok", "data": data})


@router.patch("/health-checks/{finding_id}")
def update_health_finding(
    connection_id: str,
    finding_id: str,
    payload: FindingStateRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)
    from .analysis_repository import _app_connection
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE health_findings AS findings SET user_state = %s, user_note = %s, state_updated_at = now()
                FROM analysis_runs AS runs JOIN monitored_databases AS databases ON databases.id = runs.monitored_database_id
                JOIN users ON users.id = databases.owner_user_id
                WHERE findings.id = %s AND findings.run_id = runs.id AND databases.id = %s AND users.auth_subject = %s
            """, (payload.user_state, payload.user_note, finding_id, connection_id, owner))
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="Health finding not found")
    invalidate(connection_id, "health-checks", "overview", "insights:10")
    return {"finding_id": finding_id, "user_state": payload.user_state}


@router.get("/statistics")
def statistics(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    try:
        return {"status": "ok", "data": get_latest_statistics(connection_id, _owner_subject(user))}
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        try:
            return _section(_collection_report(connection_id, user, "statistics"), "statistics")
        except HTTPException as missing:
            if missing.status_code != 404:
                raise
            return {"status": "collecting", "data": {"query_stats": [], "table_stats": [], "index_stats": [], "lock_stats": [], "database_stats": {}}}


def _statistics_group(connection_id: str, name: str, user: dict[str, object]) -> dict[str, Any]:
    section = statistics(connection_id, user)
    return {"status": section["status"], "data": section["data"][name]}


def _page(section: dict[str, Any], limit: int, offset: int) -> dict[str, Any]:
    if section["status"] != "ok":
        return section
    data = section["data"]
    return {"status": "ok", "data": data[offset:offset + limit], "next_offset": offset + limit if len(data) > offset + limit else None}


@router.get("/statistics/queries")
def query_statistics(
    connection_id: str,
    sort: Literal["calls", "total_exec_time", "mean_exec_time"] = "total_exec_time",
    limit: int = Query(default=20, ge=1, le=100),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    section = _statistics_group(connection_id, "query_stats", user)
    if section["status"] == "ok":
        section["data"] = sorted(section["data"], key=lambda query: query[sort], reverse=True)[:limit]
    return section


@router.get("/slow-queries")
def slow_queries(
    connection_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict[str, object] = Depends(current_user),
) -> Response:
    return cached_json(request, connection_id, f"slow-queries:{limit}", query_statistics(connection_id, "total_exec_time", limit, user))


@router.get("/statistics/tables")
def table_statistics(
    connection_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _page(_statistics_group(connection_id, "table_stats", user), limit, offset)


@router.get("/statistics/indexes")
def index_statistics(
    connection_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _page(_statistics_group(connection_id, "index_stats", user), limit, offset)


@router.get("/statistics/locks")
def lock_statistics(
    connection_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _page(_statistics_group(connection_id, "lock_stats", user), limit, offset)


def _schema_payload(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    try:
        return {"status": "ok", "data": get_current_schema(connection_id, _owner_subject(user))}
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        try:
            return _section(_collection_report(connection_id, user, "schema"), "schema")
        except HTTPException as missing:
            if missing.status_code != 404:
                raise
            return {"status": "collecting", "data": {"tables": [], "columns": [], "primary_keys": [], "foreign_keys": [], "indexes": [], "relations": []}}


@router.get("/schema")
def schema(
    connection_id: str,
    request: Request,
    user: dict[str, object] = Depends(current_user),
) -> Response:
    return cached_json(request, connection_id, "schema", _schema_payload(connection_id, user))


@router.get("/schema/diagram")
def schema_diagram(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    try:
        return _section(_collection_report(connection_id, user, "schema"), "schema_visualization")
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return {"status": "collecting", "data": ""}


@router.get("/schema/visualizer")
def schema_visualizer(
    connection_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, object] = Depends(current_user),
) -> Response:
    schema_data = _schema_payload(connection_id, user)["data"]
    summaries: dict[tuple[str, str], str] = {}
    from .analysis_repository import _app_connection
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT schema_name, table_name, business_summary FROM database_tables
                              WHERE monitored_database_id = %s AND removed_at IS NULL AND summary_status = 'ready'""", (connection_id,))
            summaries = {(row[0], row[1]): row[2] for row in cursor.fetchall()}
    columns = schema_data.get("columns", [])
    primary_keys = {(key["table_name"], key["column_name"]) for key in schema_data.get("primary_keys", [])}
    foreign_keys = schema_data.get("foreign_keys", [])
    all_tables = schema_data.get("tables", [])
    tables = all_tables[offset:offset + limit]
    table_names = {table["table_name"] for table in tables}
    relationships = [key for key in foreign_keys if key["source_table"] in table_names or key["target_table"] in table_names]
    indexes = schema_data.get("indexes", [])
    return cached_json(request, connection_id, f"schema/visualizer:{limit}:{offset}", {"data": {"tables": [{"name": table["table_name"], "schema": table["schema_name"], "table_type": table["table_type"], "estimated_rows": table.get("estimated_rows"), "summary": summaries.get((table["schema_name"], table["table_name"])), "columns": [{**column, "primary_key": (table["table_name"], column["column_name"]) in primary_keys, "foreign_key": any(key["source_table"] == table["table_name"] and key["source_column"] == column["column_name"] for key in relationships)} for column in columns if column["table_name"] == table["table_name"]], "indexes": [index for index in indexes if index["table_name"] == table["table_name"]]} for table in tables], "relationships": relationships}, "next_offset": offset + limit if len(all_tables) > offset + limit else None})


def _owned_schema_table(connection_id: str, owner: str, schema_name: str, table_name: str) -> None:
    ensure_owned_database(connection_id, owner)
    schema = get_current_schema(connection_id, owner)
    if not any(table["schema_name"] == schema_name and table["table_name"] == table_name for table in schema["tables"]):
        raise HTTPException(status_code=404, detail="Table not found")


@router.get("/schema/tables/{schema_name}/{table_name}/metrics")
def schema_table_metrics(
    connection_id: str,
    schema_name: str,
    table_name: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    owner = _owner_subject(user)
    _owned_schema_table(connection_id, owner, schema_name, table_name)
    connection = connection_provider(connection_id, owner)()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                WITH relation AS (SELECT to_regclass(format('%%I.%%I', %s, %s)) AS oid)
                SELECT pg_total_relation_size(oid) AS total_size_bytes,
                       pg_relation_size(oid) AS table_size_bytes,
                       pg_indexes_size(oid) AS index_size_bytes
                FROM relation
                """,
                (schema_name, table_name),
            )
            sizes = dict(cursor.fetchone() or {})
            cursor.execute(
                """SELECT n_live_tup, n_dead_tup, seq_scan, idx_scan
                   FROM pg_stat_user_tables WHERE schemaname = %s AND relname = %s""",
                (schema_name, table_name),
            )
            stats = dict(cursor.fetchone() or {})
    finally:
        connection.close()
    live, dead = int(stats.get("n_live_tup") or 0), int(stats.get("n_dead_tup") or 0)
    return {**sizes, **stats, "bloat_risk_ratio": dead / (live + dead) if live + dead else None}


@router.get("/schema/tables/{schema_name}/{table_name}/preview")
def schema_table_preview(
    connection_id: str,
    schema_name: str,
    table_name: str,
    limit: int = Query(default=50, ge=1, le=100),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    owner = _owner_subject(user)
    _owned_schema_table(connection_id, owner, schema_name, table_name)
    connection = connection_provider(connection_id, owner)()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql.SQL("SELECT * FROM {}.{} LIMIT {}").format(
                sql.Identifier(schema_name), sql.Identifier(table_name), sql.Literal(limit)
            ))
            rows = [dict(row) for row in cursor.fetchall()]
            columns = [column.name for column in cursor.description or []]
    finally:
        connection.close()
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
