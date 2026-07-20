"""FastAPI router for the Standalone Manager AI Agent."""

from typing import Any, Dict
from fastapi import APIRouter, Body, Query
from src.agent.manager_agent_standalone import ManagerAgent

router = APIRouter(prefix="/agent/manager", tags=["Manager Agent"])


@router.post("/summary")
async def generate_manager_summary(
    payload: Dict[str, Any] = Body(...),
    db_name: str | None = Query(None),
):
    """Generates an executive health and business risk summary."""
    agent = ManagerAgent(db_name=db_name)
    health_score = payload.get("health_score", 100)
    findings = payload.get("findings", [])
    return agent.analyze_and_report(health_score=health_score, findings=findings)


@router.get("/notifications")
async def get_manager_notifications(db_name: str | None = Query(None)):
    """Fetches manager-focused executive alerts."""
    agent = ManagerAgent(db_name=db_name)
    return agent.fetch_notifications()