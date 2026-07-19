"""Authenticated KPI proposal, approval, execution, and chart endpoints."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent.kpi import KPIAggregateExecutor, KPIDiscoveryAgent, KPIDiscoveryUnavailable, KPIRepository, generate_kpis

from .analysis_repository import ensure_owned_database
from .auth import current_user
from .resource_cache import cached_json, invalidate
from .store import connection_provider, get_connection


router = APIRouter(prefix="/connections/{connection_id}/kpis", tags=["kpis"])


class RefreshRequest(BaseModel):
    analysis_run_id: str | None = None


class KPIReviewRequest(BaseModel):
    approved_ids: list[str] = Field(default_factory=list, max_length=50)
    rejected_ids: list[str] = Field(default_factory=list, max_length=50)


def get_kpi_repository() -> KPIRepository:
    return KPIRepository()


def get_kpi_discovery_agent() -> KPIDiscoveryAgent:
    return KPIDiscoveryAgent()


def _owner_subject(user: dict[str, object]) -> str:
    return str(user["sub"])


def _ensure_owned(connection_id: str, user: dict[str, object]) -> None:
    ensure_owned_database(connection_id, _owner_subject(user))


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
def generate_dashboard_kpis(
    connection_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, str]:
    owner = _owner_subject(user)
    _ensure_owned(connection_id, user)
    get_connection(connection_id, owner)
    try:
        KPIDiscoveryAgent().ensure_available()
    except KPIDiscoveryUnavailable as exc:
        repository.set_generation_status(
            connection_id, "unavailable",
            error_message="KPI generation is temporarily unavailable. Please try again later.",
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    repository.set_generation_status(connection_id, "running")
    invalidate(connection_id, "kpis/dashboard")
    background_tasks.add_task(generate_kpis, connection_id, connection_provider(connection_id, owner))
    return {"status": "queued"}


def discover_candidates(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
    discovery_agent: KPIDiscoveryAgent = Depends(get_kpi_discovery_agent),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    context = repository.current_schema_context(connection_id)
    if context is None:
        raise HTTPException(status_code=409, detail="Run schema analysis before discovering KPIs")
    schema_revision_id, schema, summaries = context
    try:
        saved = repository.save_candidates(
            connection_id, schema_revision_id, discovery_agent.discover(schema, summaries)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"data": [{"id": candidate_id, **candidate.model_dump()} for candidate_id, candidate in saved]}


def _chart(definition: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    series: dict[str, list[dict[str, object]]] = defaultdict(list)
    for point in snapshot["points"]:
        name = str(point.get("dimension", definition.title))
        x = point.get("period", point.get("dimension", definition.title))
        series[name].append({"x": str(x), "y": point.get("value")})
    return {
        "kpi_id": definition.id,
        "title": definition.title,
        "unit": None,
        "grain": definition.time_grain if definition.time_column else None,
        "series": [{"name": name, "points": points} for name, points in series.items()],
        "source": {
            "analysis_run_id": snapshot["analysis_run_id"],
            "schema_revision_id": definition.schema_revision_id,
            "generated_at": snapshot["generated_at"],
            "execution_ms": snapshot["execution_ms"],
        },
    }


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def review_candidates_stream(
    connection_id: str,
    request: KPIReviewRequest,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> StreamingResponse:
    if not request.approved_ids and not request.rejected_ids:
        raise HTTPException(status_code=422, detail="Select at least one KPI proposal")
    if len(set(request.approved_ids + request.rejected_ids)) != len(request.approved_ids) + len(request.rejected_ids):
        raise HTTPException(status_code=422, detail="Each KPI proposal must have one decision")
    _ensure_owned(connection_id, user)
    get_connection(connection_id, _owner_subject(user))

    async def stream() -> Any:
        yield _sse("started", {"approved": len(request.approved_ids), "rejected": len(request.rejected_ids)})
        for candidate_id in request.rejected_ids:
            try:
                await asyncio.to_thread(repository.reject, candidate_id, connection_id)
                yield _sse("rejected", {"candidate_id": candidate_id})
            except ValueError as exc:
                yield _sse("candidate_error", {"candidate_id": candidate_id, "error": str(exc)})
        for candidate_id in request.approved_ids:
            yield _sse("kpi_started", {"candidate_id": candidate_id})
            try:
                definition = await asyncio.to_thread(repository.approve, candidate_id, connection_id)
                snapshot = await asyncio.to_thread(KPIAggregateExecutor(connection_provider(connection_id, _owner_subject(user))).execute, definition)
                await asyncio.to_thread(repository.save_snapshot, snapshot)
                yield _sse("kpi_ready", {"candidate_id": candidate_id, "definition": definition.model_dump(), "chart": _chart(definition, {
                    "analysis_run_id": snapshot.analysis_run_id, "points": snapshot.points,
                    "execution_ms": snapshot.execution_ms, "generated_at": None,
                })})
            except Exception as exc:
                yield _sse("candidate_error", {"candidate_id": candidate_id, "error": f"{type(exc).__name__}: {exc}"})
        yield _sse("complete", {})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def list_candidates(
    connection_id: str,
    status: Literal["proposed", "approved", "rejected"] | None = Query(default="proposed"),
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    return {"data": repository.list_candidates(connection_id, status)}


def approve_candidate(
    connection_id: str,
    candidate_id: str,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    get_connection(connection_id, _owner_subject(user))
    try:
        definition = repository.approve(candidate_id, connection_id)
        snapshot = KPIAggregateExecutor(connection_provider(connection_id, _owner_subject(user))).execute(definition)
        repository.save_snapshot(snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"KPI execution failed: {type(exc).__name__}") from exc
    invalidate(connection_id, "kpis/dashboard", f"kpis/chart:{definition.id}")
    return {"definition": definition.model_dump(), "chart": _chart(definition, {
        "analysis_run_id": snapshot.analysis_run_id,
        "points": snapshot.points,
        "execution_ms": snapshot.execution_ms,
        "generated_at": None,
    })}


def reject_candidate(
    connection_id: str,
    candidate_id: str,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> None:
    _ensure_owned(connection_id, user)
    try:
        repository.reject(candidate_id, connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/definitions")
def list_definitions(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    return {"data": [definition.model_dump() for definition in repository.list_definitions(connection_id)]}


@router.get("/dashboard")
def kpi_dashboard(
    connection_id: str,
    request: Request,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> Response:
    _ensure_owned(connection_id, user)
    snapshots = repository.latest_snapshots(connection_id)
    data = []
    for definition in repository.list_definitions(connection_id):
        snapshot = snapshots.get(definition.id)
        data.append({**definition.model_dump(), "chart": _chart(definition, snapshot) if snapshot else None})
    return cached_json(request, connection_id, "kpis/dashboard", {"data": data, "generation": repository.generation_status(connection_id)})


@router.post("/definitions/{definition_id}/refresh")
def refresh_definition(
    connection_id: str,
    definition_id: str,
    request: RefreshRequest | None = None,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    definition = repository.get_definition(definition_id, connection_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="KPI definition not found")
    get_connection(connection_id, _owner_subject(user))
    try:
        snapshot = KPIAggregateExecutor(connection_provider(connection_id, _owner_subject(user))).execute(
            definition, request.analysis_run_id if request else None
        )
        repository.save_snapshot(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"KPI execution failed: {type(exc).__name__}") from exc
    invalidate(connection_id, "kpis/dashboard", f"kpis/chart:{definition_id}")
    return _chart(definition, {
        "analysis_run_id": snapshot.analysis_run_id,
        "points": snapshot.points,
        "execution_ms": snapshot.execution_ms,
        "generated_at": None,
    })


@router.get("/definitions/{definition_id}/chart")
def latest_chart(
    connection_id: str,
    definition_id: str,
    request: Request,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> Response:
    _ensure_owned(connection_id, user)
    definition = repository.get_definition(definition_id, connection_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="KPI definition not found")
    snapshot = repository.latest_snapshot(definition_id, connection_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No KPI snapshot found")
    return cached_json(request, connection_id, f"kpis/chart:{definition_id}", _chart(definition, snapshot))
