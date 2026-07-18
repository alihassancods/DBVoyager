"""Persistent, owner-scoped dashboard views for collected database analysis."""

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from .analysis_repository import (
    create_analysis_run,
    ensure_owned_database,
    get_analysis_progress,
    get_analysis_run,
    get_latest_collection_report,
    get_latest_report,
    run_analysis,
    run_analysis_in_background,
)
from .auth import current_user
from .store import connection_provider, get_connection, get_database_name


router = APIRouter(prefix="/connections/{connection_id}")


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
    return create_analysis_run(connection_id, "manual"), get_database_name(connection_id)


def _start_collection_run(
    connection_id: str,
    resource: Literal["statistics", "slow_queries", "schema", "health_checks", "table_summaries"],
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
        get_database_name(connection_id),
        connection_provider(connection_id),
        resource,
    )
    return {"run_id": run_id, "resource": resource, "status": "queued"}


@router.post("/dashboard/refresh")
def refresh_dashboard(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    run_id, database_name = _start_manual_run(connection_id, user)
    return run_analysis(run_id, connection_id, database_name, connection_provider(connection_id))


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
                yield _sse("progress", event)
            run = await asyncio.to_thread(get_analysis_run, connection_id, run_id, owner_subject)
            if run["status"] in {"succeeded", "failed", "cancelled"}:
                yield _sse("complete" if run["status"] == "succeeded" else "error", run)
                return
            if not events:
                yield _sse("progress", {"stage": "analysis", "message": f"Analysis is {run['status']}."})
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")


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
    provider = connection_provider(connection_id)
    loop = asyncio.get_running_loop()
    updates: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    def progress(stage: str, state: str) -> None:
        loop.call_soon_threadsafe(updates.put_nowait, {"stage": stage, "status": state})

    async def stream() -> Any:
        task = asyncio.create_task(
            asyncio.to_thread(run_analysis, run_id, connection_id, database_name, provider, progress)
        )
        while not task.done() or not updates.empty():
            try:
                yield _sse("progress", await asyncio.wait_for(updates.get(), timeout=0.1))
            except TimeoutError:
                continue
        try:
            yield _sse("complete", task.result())
        except Exception as exc:
            yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/dashboard")
def dashboard(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _report(connection_id, user)


@router.get("/overview")
def overview(connection_id: str, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    report = _report(connection_id, user)
    health = _section(report, "health_checks")
    statistics = _section(report, "statistics")
    findings = health.get("data", []) if health.get("status") == "ok" else []
    stats = statistics.get("data", {}) if statistics.get("status") == "ok" else {}
    return {
        "generated_at": report.get("generated_at"),
        "health_summary": {severity: sum(item.get("severity") == severity for item in findings)
                           for severity in ("critical", "warning", "info")},
        "database_stats": stats.get("database_stats", {}),
        "top_slow_queries": stats.get("query_stats", [])[:5],
        "table_count": len(_section(report, "schema").get("data", {}).get("tables", [])),
    }


@router.get("/health-checks")
def health_checks(
    connection_id: str,
    severity: str | None = None,
    check: str | None = Query(default=None),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    section = _section(_collection_report(connection_id, user, "health_checks"), "health_checks")
    if section["status"] != "ok":
        return section
    data = [
        finding for finding in section["data"]
        if (severity is None or finding["severity"] == severity)
        and (check is None or finding["check"] == check)
    ]
    return {"status": "ok", "data": data}


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
    return {"finding_id": finding_id, "user_state": payload.user_state}


@router.get("/statistics")
def statistics(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _section(_collection_report(connection_id, user, "statistics"), "statistics")


def _statistics_group(connection_id: str, name: str, user: dict[str, object]) -> dict[str, Any]:
    section = statistics(connection_id, user)
    return section if section["status"] != "ok" else {"status": "ok", "data": section["data"][name]}


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
    limit: int = Query(default=20, ge=1, le=100),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return query_statistics(connection_id, "total_exec_time", limit, user)


@router.get("/statistics/tables")
def table_statistics(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _statistics_group(connection_id, "table_stats", user)


@router.get("/statistics/indexes")
def index_statistics(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _statistics_group(connection_id, "index_stats", user)


@router.get("/statistics/locks")
def lock_statistics(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _statistics_group(connection_id, "lock_stats", user)


@router.get("/schema")
def schema(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _section(_collection_report(connection_id, user, "schema"), "schema")


@router.get("/schema/diagram")
def schema_diagram(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _section(_collection_report(connection_id, user, "schema"), "schema_visualization")
