"""Persistent, owner-scoped dashboard views for collected database analysis."""

import asyncio
import json
from datetime import datetime, timezone
from queue import Empty, Queue
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
from pydantic import BaseModel
from src.services.health.fix_service import HealthFixEngine

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
    has_active_analysis,
    list_analysis_runs,
    list_analysis_run_events,
    persist_collected_analysis,
    run_analysis,
    run_analysis_in_background,
)
from .auth import current_user
from .store import connection_provider, get_connection, get_database_name
from .resource_cache import cache_resource, cached_json, cached_value, invalidate
from .resource_cache import publish_preview, read_preview, warm_json
from .brief import collect_brief


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


class ProposeFixRequest(BaseModel):
    finding: dict[str, Any]


class ExecuteFixRequest(BaseModel):
    sql_query: str


@router.post("/health-checks/propose-fix")
def propose_fix(
    connection_id: str,
    payload: ProposeFixRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    """Step 1: AI generates the SQL query to show the user for approval."""
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)

    engine = HealthFixEngine()
    return cached_value(
        connection_id,
        cache_resource("fix", payload.finding),
        lambda: engine.generate_proposed_fix(payload.finding),
        3600,
    )


@router.post("/health-checks/apply-fix")
def apply_fix_and_refresh(
    connection_id: str,
    payload: ExecuteFixRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    """Step 2: Executed upon user confirmation -> Applies SQL fix & invalidates cache."""
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)

    # Execute SQL on database
    provider = connection_provider(connection_id, owner)
    HealthFixEngine.apply_fix_and_commit(provider, payload.sql_query)

    # Invalidate cached endpoints so UI updates cleanly
    invalidate(connection_id, "health-checks", "overview", "insights:10")

    return {
        "status": "success",
        "message": "Fix successfully applied.",
    }

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
    result = _start_collection_run(connection_id, "health_checks", background_tasks, user)
    invalidate(connection_id, "health-checks")
    return result


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


@router.get("/analysis/logs")
def analysis_logs(
    connection_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return {"data": list_analysis_runs(connection_id, _owner_subject(user), limit)}


@router.get("/analysis/logs/{run_id}")
def analysis_log_detail(
    connection_id: str,
    run_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return get_analysis_run(connection_id, run_id, _owner_subject(user))


@router.get("/analysis/logs/{run_id}/events")
def analysis_log_events(
    connection_id: str,
    run_id: str,
    offset: int = Query(default=0, ge=0),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return {"data": list_analysis_run_events(connection_id, run_id, _owner_subject(user), offset)}


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
        # Step 1: Run brief analysis first (fast, 3-4 queries, completes in < 2s)
        try:
            brief_data = await asyncio.to_thread(
                collect_brief, provider,
                lambda stage, msg: _record_progress(run_id, stage, msg),
            )
            brief_payload = {"status": "ok", "data": brief_data}
            yield _sse("section_ready", {"section": "brief", "data": brief_payload})
            _warm_brief_cache(connection_id, brief_data)
        except Exception as exc:
            yield _sse("section_ready", {"section": "brief", "data": {"status": "error", "error": f"{type(exc).__name__}: {exc}"}})

        # Step 2: Deep analysis with per-section streaming
        ready_sections: Queue[tuple[str, dict[str, Any]]] = Queue()
        task = asyncio.create_task(asyncio.to_thread(
            collect_analysis, run_id, connection_id, database_name, provider,
            lambda stage, state: _record_progress(run_id, stage, state), "dashboard",
            lambda section, data: ready_sections.put((section, data)),
        ))
        offset = 0
        while not task.done():
            events, offset = await asyncio.to_thread(get_analysis_progress, run_id, offset)
            for event in events:
                yield _sse("progress", {"stage": event["stage"], "status": event["message"]})
            while True:
                try:
                    section, data = ready_sections.get_nowait()
                except Empty:
                    break
                _warm_section_cache(connection_id, section, data)
                yield _sse("section_ready", {"section": section, "data": data})
            await asyncio.sleep(0.1)
        events, offset = await asyncio.to_thread(get_analysis_progress, run_id, offset)
        for event in events:
            yield _sse("progress", {"stage": event["stage"], "status": event["message"]})
        while True:
            try:
                section, data = ready_sections.get_nowait()
            except Empty:
                break
            _warm_section_cache(connection_id, section, data)
            yield _sse("section_ready", {"section": section, "data": data})
        try:
            report = task.result()
            if publish_preview(connection_id, run_id, "dashboard", report):
                _record_progress(run_id, "data_ready", "Collected data is ready for the dashboard.")
                yield _sse("complete", {"analysis_run_id": run_id, "status": "succeeded"})
            else:
                await asyncio.to_thread(persist_collected_analysis, run_id, connection_id, report, "dashboard")
                yield _sse("complete", {"analysis_run_id": run_id, "status": "succeeded"})
        except Exception as exc:
            yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


def _warm_brief_cache(connection_id: str, brief_data: dict) -> None:
    """Warm Redis cache from brief collection results so GET endpoints find data immediately."""
    try:
        insights = brief_data.get("insights", [])
        overview = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health_summary": {s: sum(1 for i in insights if i["severity"] == s) for s in ("critical", "warning", "info")},
            "database_stats": brief_data.get("database_stats", {}),
            "top_slow_queries": brief_data.get("queries", [])[:5],
            "table_count": len(brief_data.get("tables", [])),
            "insights": insights[:10],
            "query_telemetry_available": brief_data.get("query_telemetry_available", False),
        }
        warm_json(connection_id, "overview", overview)
    except Exception:
        pass


def _warm_section_cache(connection_id: str, section: str, data: dict) -> None:
    """Warm per-section Redis cache as each section arrives via SSE."""
    if data.get("status") != "ok" or not isinstance(data.get("data"), dict):
        return
    try:
        inner = data["data"]
        if section == "statistics":
            warm_json(connection_id, "statistics", data)
            if inner.get("query_stats"):
                warm_json(connection_id, "slow-queries:20", {"status": "ok", "data": inner["query_stats"][:20]})
        elif section == "schema":
            warm_json(connection_id, "schema", data)
        elif section == "health_checks":
            warm_json(connection_id, "health-checks", {"status": "ok", "data": inner})
    except Exception:
        pass


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
) -> Any:
    try:
        return _report(connection_id, user)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "collecting", "message": "Dashboard report is being generated."})


@router.get("/overview")
def overview(connection_id: str, request: Request, user: dict[str, object] = Depends(current_user)) -> Any:
    ensure_owned_database(connection_id, _owner_subject(user))

    def build() -> dict[str, Any]:
        summary = get_dashboard_summary(connection_id, _owner_subject(user))
        if summary:
            return summary[0]
        try:
            brief = get_latest_collection_report(connection_id, _owner_subject(user), "brief")["brief"]["data"]
            return {"generated_at": None, "health_summary": {severity: sum(item["severity"] == severity for item in brief["insights"]) for severity in ("critical", "warning", "info")}, "database_stats": brief["database_stats"], "top_slow_queries": brief["queries"], "table_count": len(brief["tables"]), "insights": brief["insights"], "query_telemetry_available": brief["query_telemetry_available"]}
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        report = _report(connection_id, user)
        health, statistics = _section(report, "health_checks"), _section(report, "statistics")
        findings = health.get("data", []) if health.get("status") == "ok" else []
        stats = statistics.get("data", {}) if statistics.get("status") == "ok" else {}
        health_score = HealthSummaryService.calculate_score(findings)
        return {"generated_at": report.get("generated_at"), "health_summary": {severity: sum(item.get("severity") == severity for item in findings) for severity in ("critical", "warning", "info")}, "database_stats": stats.get("database_stats", {}), "top_slow_queries": stats.get("query_stats", [])[:5], "table_count": len(_section(report, "schema").get("data", {}).get("tables", [])), "health_score": health_score, "top_findings": HealthSummaryService.top_findings(findings), "summary": cached_value(connection_id, cache_resource("execsummary", {"score": health_score, "findings": findings[:10]}), lambda: ExecutiveSummaryAgent().summarize(health_score, findings), 600)}

    try:
        return cached_json(request, connection_id, "overview", build)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"collection_status": "collecting"})


@router.get("/insights")
def insights(connection_id: str, request: Request, limit: int = Query(default=10, ge=1, le=50), user: dict[str, object] = Depends(current_user)) -> Response:
    ensure_owned_database(connection_id, _owner_subject(user))
    return cached_json(request, connection_id, f"insights:{limit}", lambda: {"data": get_latest_collection_report(connection_id, _owner_subject(user), "brief")["brief"]["data"]["insights"][:limit]})


@router.get("/health-checks")
def health_checks(
    connection_id: str,
    request: Request,
    severity: str | None = None,
    check: str | None = Query(default=None),
    user: dict[str, object] = Depends(current_user),
) -> Response:
    ensure_owned_database(connection_id, _owner_subject(user))
    resource = "health-checks" if severity is None and check is None else f"health-checks:{severity or 'all'}:{check or 'all'}"
    def build() -> dict[str, Any]:
        try:
            findings = get_latest_health_findings(connection_id, _owner_subject(user))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            section = _section(_collection_report(connection_id, user, "health_checks"), "health_checks")
            if section["status"] != "ok":
                if has_active_analysis(connection_id):
                    raise HTTPException(status_code=404)
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=section.get("error", "Health check collection failed."))
            findings = section["data"]
        return {"status": "ok", "data": [finding for finding in findings if (severity is None or finding["severity"] == severity) and (check is None or finding["check"] == check)]}
    try:
        return cached_json(request, connection_id, resource, build)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "collecting", "message": "Health check collection is in progress."})


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
            return {"status": "collecting", "message": "Statistics collection is in progress.", "data": {"query_stats": [], "table_stats": [], "index_stats": [], "lock_stats": [], "database_stats": {}}}


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
    ensure_owned_database(connection_id, _owner_subject(user))
    return cached_json(request, connection_id, f"slow-queries:{limit}", lambda: query_statistics(connection_id, "total_exec_time", limit, user))


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
            return {"status": "collecting", "message": "Schema collection is in progress.", "data": {"tables": [], "columns": [], "primary_keys": [], "foreign_keys": [], "indexes": [], "relations": []}}


@router.get("/schema")
def schema(
    connection_id: str,
    request: Request,
    user: dict[str, object] = Depends(current_user),
) -> Response:
    ensure_owned_database(connection_id, _owner_subject(user))
    return cached_json(request, connection_id, "schema", lambda: _schema_payload(connection_id, user))


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
        return {"status": "collecting", "message": "Schema diagram is being generated."}


@router.get("/schema/visualizer")
def schema_visualizer(
    connection_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, object] = Depends(current_user),
) -> Response:
    ensure_owned_database(connection_id, _owner_subject(user))

    def build() -> dict[str, Any]:
        schema_data = _schema_payload(connection_id, user)["data"]
        from .analysis_repository import _app_connection
        with _app_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT schema_name, table_name, business_summary FROM database_tables
                                  WHERE monitored_database_id = %s AND removed_at IS NULL AND summary_status = 'ready'""", (connection_id,))
                summaries = {(row[0], row[1]): row[2] for row in cursor.fetchall()}
        columns = schema_data.get("columns", [])
        primary_keys = {(key["table_name"], key["column_name"]) for key in schema_data.get("primary_keys", [])}
        foreign_keys, all_tables, indexes = schema_data.get("foreign_keys", []), schema_data.get("tables", []), schema_data.get("indexes", [])
        tables = all_tables[offset:offset + limit]
        table_names = {table["table_name"] for table in tables}
        relationships = [key for key in foreign_keys if key["source_table"] in table_names or key["target_table"] in table_names]
        return {"data": {"tables": [{"name": table["table_name"], "schema": table["schema_name"], "table_type": table["table_type"], "estimated_rows": table.get("estimated_rows"), "summary": summaries.get((table["schema_name"], table["table_name"])), "columns": [{**column, "primary_key": (table["table_name"], column["column_name"]) in primary_keys, "foreign_key": any(key["source_table"] == table["table_name"] and key["source_column"] == column["column_name"] for key in relationships)} for column in columns if column["table_name"] == table["table_name"]], "indexes": [index for index in indexes if index["table_name"] == table["table_name"]]} for table in tables], "relationships": relationships}, "next_offset": offset + limit if len(all_tables) > offset + limit else None}

    return cached_json(request, connection_id, f"schema/visualizer:{limit}:{offset}", build)


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
