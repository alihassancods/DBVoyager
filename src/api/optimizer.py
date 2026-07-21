"""Owner-scoped query optimizer endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg2.extras import Json

from src.agent.business_intelligence.validator import SQLValidator
from src.agent.query_optimizer.models import OptimizationResult
from src.agent.query_optimizer.optimizer_agent import QueryOptimizerAgent
from src.db_engine.inspectors.explain_plan_inspector import ExplainPlanInspector
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.statistics.query_stats_inspector import QueryStatsInspector
from src.models.api.optimizer_request import CompareQueryRequest, OptimizeQueryRequest

from .analysis_repository import (
    ensure_owned_database,
    get_latest_slow_queries,
    get_slow_query,
    get_slow_query_detail,
)
from .auth import current_user
from .resource_cache import cache_resource, cached_value
from .store import connection_provider, get_connection


router = APIRouter(prefix="/connections/{connection_id}/optimizer", tags=["Query Optimizer"])


class FeedbackRequest(BaseModel):
    feedback: str = Field(pattern="^(useful|not_useful)$")
    note: str | None = Field(default=None, max_length=1_000)


def _owner_subject(user: dict[str, object]) -> str:
    return str(user["sub"])


def _agent(connection_id: str, owner: str) -> QueryOptimizerAgent:
    provider = connection_provider(connection_id, owner)
    return QueryOptimizerAgent(
        query_stats_inspector=QueryStatsInspector(provider),
        schema_inspector=SchemaInspector.from_connection_provider(provider),
        explain_plan_inspector=ExplainPlanInspector(provider),
    )


def _owned_agent(connection_id: str, user: dict[str, object]) -> QueryOptimizerAgent:
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)
    get_connection(connection_id, owner)
    return _agent(connection_id, owner)


@router.get("/slow-queries")
def slow_queries(
    connection_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, list[dict[str, Any]]]:
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)
    return {"data": get_latest_slow_queries(connection_id, owner, limit)}


@router.get("/queries/{query_id}")
def query_detail(
    connection_id: str,
    query_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)
    return get_slow_query_detail(connection_id, owner, query_id)


@router.post("/queries/{query_id}/plan")
def query_plan(
    connection_id: str,
    query_id: str,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    """Generate a plain, read-only PostgreSQL EXPLAIN for a stored query."""
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)
    get_connection(connection_id, owner)
    detail = get_slow_query_detail(connection_id, owner, query_id)
    validation = SQLValidator().validate(str(detail["query"]))
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=f"Stored query is unsafe: {validation.reason}")
    try:
        plan = ExplainPlanInspector(connection_provider(connection_id, owner)).get_plan(str(detail["query"]))
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "query_id": query_id,
        "costs": plan.costs.model_dump(),
        "raw_plan": plan.raw_plan,
    }


@router.post("/optimizations")
def optimize_query(
    connection_id: str,
    request: OptimizeQueryRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    owner = _owner_subject(user)
    agent = _owned_agent(connection_id, user)
    query = get_slow_query(connection_id, owner, request.query_id)
    validation = SQLValidator().validate(query)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=f"Stored query is unsafe: {validation.reason}")
    cached_result = cached_value(
        connection_id,
        cache_resource("optimization", query),
        lambda: agent.optimize_query(query).model_dump(),
        3600,
    )
    result = OptimizationResult.model_validate(cached_result)
    optimized_validation = SQLValidator().validate(result.optimized_query)
    if not optimized_validation.is_valid:
        raise HTTPException(status_code=422, detail=f"Optimizer returned unsafe SQL: {optimized_validation.reason}")
    from .analysis_repository import _app_connection
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO query_optimizations (
                    monitored_database_id, query_snapshot_id, original_query, optimized_query, explanation, index_recommendations
                ) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (connection_id, request.query_id, result.original_query, result.optimized_query,
                   result.explanation, Json(result.index_recommendations)))
            optimization_id = str(cursor.fetchone()[0])
    return {
        "optimization_id": optimization_id,
        "query_id": request.query_id,
        "original_query": result.original_query,
        "optimized_query": result.optimized_query,
        "explanation": result.explanation,
        "index_recommendations": result.index_recommendations,
    }


@router.post("/optimizations/compare")
def compare_queries(
    connection_id: str,
    request: CompareQueryRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, float | int]:
    for query in (request.original_query, request.optimized_query):
        validation = SQLValidator().validate(query)
        if not validation.is_valid:
            raise HTTPException(status_code=400, detail=validation.reason)
    try:
        comparison = _owned_agent(connection_id, user).compare_queries(
            request.original_query, request.optimized_query
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return comparison.model_dump()


@router.get("/optimizations/{optimization_id}")
def optimization(
    connection_id: str, optimization_id: str, user: dict[str, object] = Depends(current_user)
) -> dict[str, Any]:
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)
    from .analysis_repository import _app_connection
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, original_query, optimized_query, explanation, index_recommendations, feedback, feedback_note, created_at
                FROM query_optimizations WHERE id = %s AND monitored_database_id = %s
            """, (optimization_id, connection_id))
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Optimization not found")
    return {"optimization_id": str(row[0]), "original_query": row[1], "optimized_query": row[2],
            "explanation": row[3], "index_recommendations": row[4], "feedback": row[5],
            "feedback_note": row[6], "created_at": row[7]}


@router.post("/optimizations/{optimization_id}/feedback")
def optimization_feedback(
    connection_id: str, optimization_id: str, payload: FeedbackRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    owner = _owner_subject(user)
    ensure_owned_database(connection_id, owner)
    from .analysis_repository import _app_connection
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE query_optimizations SET feedback = %s, feedback_note = %s
                              WHERE id = %s AND monitored_database_id = %s""",
                           (payload.feedback, payload.note, optimization_id, connection_id))
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="Optimization not found")
    return {"optimization_id": optimization_id, "feedback": payload.feedback}
