"""Persistent, owner-scoped dashboard views for collected database analysis."""

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from .analysis_repository import (
    create_analysis_run,
    ensure_owned_database,
    get_analysis_progress,
    get_analysis_run,
    get_latest_report,
    run_analysis,
)
from .auth import current_user
from .store import connection_provider, get_connection, get_database_name


router = APIRouter(prefix="/connections/{connection_id}")


def _owner_subject(user: dict[str, object]) -> str:
    return str(user["sub"])


def _report(connection_id: str, user: dict[str, object]) -> dict[str, Any]:
    return get_latest_report(connection_id, _owner_subject(user))


def _section(report: dict[str, Any], name: str) -> dict[str, Any]:
    return report[name]


def _start_manual_run(connection_id: str, user: dict[str, object]) -> tuple[str, str]:
    owner_subject = _owner_subject(user)
    ensure_owned_database(connection_id, owner_subject)
    get_connection(connection_id, owner_subject)
    return create_analysis_run(connection_id, "manual"), get_database_name(connection_id)


@router.post("/dashboard/refresh")
def refresh_dashboard(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    run_id, database_name = _start_manual_run(connection_id, user)
    return run_analysis(run_id, connection_id, database_name, connection_provider(connection_id))


@router.get("/analysis-runs/{run_id}")
def analysis_run(
    connection_id: str,
    run_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return get_analysis_run(connection_id, run_id, _owner_subject(user))


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


@router.get("/health-checks")
def health_checks(
    connection_id: str,
    severity: str | None = None,
    check: str | None = Query(default=None),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    section = _section(_report(connection_id, user), "health_checks")
    if section["status"] != "ok":
        return section
    data = [
        finding for finding in section["data"]
        if (severity is None or finding["severity"] == severity)
        and (check is None or finding["check"] == check)
    ]
    return {"status": "ok", "data": data}


@router.get("/statistics")
def statistics(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _section(_report(connection_id, user), "statistics")


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
    return _section(_report(connection_id, user), "schema")


@router.get("/schema/diagram")
def schema_diagram(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    return _section(_report(connection_id, user), "schema_visualization")
