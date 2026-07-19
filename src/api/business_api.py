"""Owner-scoped business intelligence investigations."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException #type: ignore
from pydantic import BaseModel, Field # type: ignore

from src.agent.business_intelligence.orchestrator import BusinessIntelligenceOrchestrator

from .analysis_repository import ensure_owned_database
from .auth import current_user
from .store import connection_provider, get_connection


router = APIRouter(prefix="/connections/{connection_id}/bi", tags=["Business Intelligence"])


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)


class InvestigationResult(BaseModel):
    question: str
    plan: dict[str, Any]
    generated_sql: str
    result: dict[str, Any]
    insight: dict[str, Any]
    charts: list[dict[str, Any]]


@router.post("/investigations", response_model=InvestigationResult)
def investigate_business_question(
    connection_id: str,
    request: InvestigationRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, Any]:
    owner = str(user["sub"])
    ensure_owned_database(connection_id, owner)
    get_connection(connection_id, owner)
    try:
        result = BusinessIntelligenceOrchestrator(
            connection_provider=connection_provider(connection_id, owner)
        ).investigate(question=request.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"BI investigation failed: {type(exc).__name__}") from exc
    return {
    "question": result["question"],
    "answer": result["insight"].summary,
    "evidence": result["insight"].evidence,
    "recommendations": result["insight"].recommendations,
    "charts": [chart.model_dump() for chart in result["charts"]],
}
