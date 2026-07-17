"""Authenticated KPI proposal, approval, execution, and chart endpoints."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.agent.kpi import KPIAggregateExecutor, KPIRepository

from .analysis_repository import ensure_owned_database
from .auth import current_user
from .store import connection_provider, get_connection


router = APIRouter(prefix="/connections/{connection_id}/kpis", tags=["kpis"])


class RefreshRequest(BaseModel):
    analysis_run_id: str | None = None


def get_kpi_repository() -> KPIRepository:
    return KPIRepository()


def _owner_subject(user: dict[str, object]) -> str:
    return str(user["sub"])


def _ensure_owned(connection_id: str, user: dict[str, object]) -> None:
    ensure_owned_database(connection_id, _owner_subject(user))


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


@router.get("/candidates")
def list_candidates(
    connection_id: str,
    status: Literal["proposed", "approved", "rejected"] | None = Query(default="proposed"),
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    return {"data": repository.list_candidates(connection_id, status)}


@router.post("/candidates/{candidate_id}/approve")
def approve_candidate(
    connection_id: str,
    candidate_id: str,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    if not repository.candidate_belongs_to(candidate_id, connection_id):
        raise HTTPException(status_code=404, detail="KPI candidate not found")
    get_connection(connection_id, _owner_subject(user))
    try:
        definition = repository.approve(candidate_id)
        snapshot = KPIAggregateExecutor(connection_provider(connection_id)).execute(definition)
        repository.save_snapshot(snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"KPI execution failed: {type(exc).__name__}") from exc
    return {"definition": definition.model_dump(), "chart": _chart(definition, {
        "analysis_run_id": snapshot.analysis_run_id,
        "points": snapshot.points,
        "execution_ms": snapshot.execution_ms,
        "generated_at": None,
    })}


@router.post("/candidates/{candidate_id}/reject", status_code=204)
def reject_candidate(
    connection_id: str,
    candidate_id: str,
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> None:
    _ensure_owned(connection_id, user)
    if not repository.candidate_belongs_to(candidate_id, connection_id):
        raise HTTPException(status_code=404, detail="KPI candidate not found")
    try:
        repository.reject(candidate_id)
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
        snapshot = KPIAggregateExecutor(connection_provider(connection_id)).execute(
            definition, request.analysis_run_id if request else None
        )
        repository.save_snapshot(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"KPI execution failed: {type(exc).__name__}") from exc
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
    user: dict[str, object] = Depends(current_user),
    repository: KPIRepository = Depends(get_kpi_repository),
) -> dict[str, object]:
    _ensure_owned(connection_id, user)
    definition = repository.get_definition(definition_id, connection_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="KPI definition not found")
    snapshot = repository.latest_snapshot(definition_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No KPI snapshot found")
    return _chart(definition, snapshot)
