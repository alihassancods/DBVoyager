"""Cached dashboard views over the report produced by ``v1``."""

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from v1 import build_report

from .store import _credentials, _lock, _reports, connection_provider, get_connection, get_report


router = APIRouter(prefix="/connections/{connection_id}")


def _section(report: dict[str, Any], name: str) -> dict[str, Any]:
    return report[name]


@router.post("/dashboard/refresh")
def refresh_dashboard(connection_id: str) -> dict[str, Any]:
    get_connection(connection_id)
    with _lock:
        database_name = _credentials[connection_id]["database"]
    report = build_report(database_name, connection_provider(connection_id))
    with _lock:
        _reports[connection_id] = report
    return report


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/dashboard/refresh/stream")
async def refresh_dashboard_stream(connection_id: str) -> StreamingResponse:
    get_connection(connection_id)
    with _lock:
        database_name = _credentials[connection_id]["database"]
    provider = connection_provider(connection_id)
    loop = asyncio.get_running_loop()
    updates: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    def progress(stage: str, status: str) -> None:
        loop.call_soon_threadsafe(updates.put_nowait, {"stage": stage, "status": status})

    async def stream() -> Any:
        task = asyncio.create_task(asyncio.to_thread(build_report, database_name, provider, progress))
        while not task.done() or not updates.empty():
            try:
                yield _sse("progress", await asyncio.wait_for(updates.get(), timeout=0.1))
            except TimeoutError:
                continue
        try:
            report = task.result()
        except Exception as exc:
            yield _sse("error", {"error": f"{type(exc).__name__}: {exc}"})
            return
        with _lock:
            _reports[connection_id] = report
        yield _sse("complete", report)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/dashboard")
def dashboard(connection_id: str) -> dict[str, Any]:
    return get_report(connection_id)


@router.get("/health-checks")
def health_checks(
    connection_id: str,
    severity: str | None = None,
    check: str | None = Query(default=None),
) -> dict[str, Any]:
    section = _section(get_report(connection_id), "health_checks")
    if section["status"] != "ok":
        return section
    data = [
        finding for finding in section["data"]
        if (severity is None or finding["severity"] == severity)
        and (check is None or finding["check"] == check)
    ]
    return {"status": "ok", "data": data}


@router.get("/statistics")
def statistics(connection_id: str) -> dict[str, Any]:
    return _section(get_report(connection_id), "statistics")


def _statistics_group(connection_id: str, name: str) -> dict[str, Any]:
    section = statistics(connection_id)
    return section if section["status"] != "ok" else {"status": "ok", "data": section["data"][name]}


@router.get("/statistics/queries")
def query_statistics(
    connection_id: str,
    sort: Literal["calls", "total_exec_time", "mean_exec_time"] = "total_exec_time",
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    section = _statistics_group(connection_id, "query_stats")
    if section["status"] == "ok":
        section["data"] = sorted(section["data"], key=lambda query: query[sort], reverse=True)[:limit]
    return section


@router.get("/statistics/tables")
def table_statistics(connection_id: str) -> dict[str, Any]:
    return _statistics_group(connection_id, "table_stats")


@router.get("/statistics/indexes")
def index_statistics(connection_id: str) -> dict[str, Any]:
    return _statistics_group(connection_id, "index_stats")


@router.get("/statistics/locks")
def lock_statistics(connection_id: str) -> dict[str, Any]:
    return _statistics_group(connection_id, "lock_stats")


@router.get("/schema")
def schema(connection_id: str) -> dict[str, Any]:
    return _section(get_report(connection_id), "schema")


@router.get("/schema/diagram")
def schema_diagram(connection_id: str) -> dict[str, Any]:
    return _section(get_report(connection_id), "schema_visualization")
