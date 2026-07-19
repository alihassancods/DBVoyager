"""Owner-scoped business intelligence investigations."""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query #type: ignore
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field # type: ignore
from psycopg2.extras import Json

from src.agent.business_intelligence.orchestrator import BusinessIntelligenceOrchestrator

from .analysis_repository import _app_connection, ensure_owned_database
from .auth import current_user
from .store import connection_provider, get_connection


router = APIRouter(prefix="/connections/{connection_id}/bi", tags=["Business Intelligence"])
logger = logging.getLogger(__name__)


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)


class InvestigationResult(BaseModel):
    report_id: str
    question: str
    plan: dict[str, Any]
    generated_sql: str
    result: dict[str, Any]
    insight: dict[str, Any]
    charts: list[dict[str, Any]]


class ReportUpdate(BaseModel):
    is_pinned: bool


def _json(value: Any) -> Json:
    return Json(value, dumps=lambda data: json.dumps(data, default=str))


def _report_payload(report_id: str, question: str, plan: dict[str, Any], generated_sql: str, result: dict[str, Any], insight: dict[str, Any], charts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"report_id": report_id, "question": question, "plan": plan, "generated_sql": generated_sql, "result": result, "insight": insight, "charts": charts}


def _save_report(connection_id: str, result: dict[str, Any]) -> dict[str, Any]:
    plan = result["plan"].model_dump()
    rows = result["rows"]
    payload = {"columns": list(rows[0]) if rows else [], "rows": rows, "row_count": result["row_count"]}
    insight = result["insight"].model_dump()
    charts = [chart.model_dump() for chart in result["charts"]]
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""DELETE FROM bi_reports WHERE monitored_database_id = %s
                              AND is_pinned = false AND created_at < now() - interval '90 days'""", (connection_id,))
            cursor.execute("""INSERT INTO bi_reports (monitored_database_id, question, plan_json, generated_sql, result_json, insight_json, charts_json)
                              VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                           (connection_id, result["question"], _json(plan), result["sql"], _json(payload), _json(insight), _json(charts)))
            report_id = str(cursor.fetchone()[0])
    return _report_payload(report_id, result["question"], plan, result["sql"], payload, insight, charts)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


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
    return _save_report(connection_id, result)


@router.post("/investigations/stream")
async def stream_business_question(
    connection_id: str,
    request: InvestigationRequest,
    user: dict[str, object] = Depends(current_user),
) -> StreamingResponse:
    owner = str(user["sub"])
    ensure_owned_database(connection_id, owner)
    get_connection(connection_id, owner)

    async def stream() -> Any:
        loop = asyncio.get_running_loop()
        events: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        def emit(event: str, data: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(events.put_nowait, (event, data))

        def investigate() -> None:
            try:
                result = BusinessIntelligenceOrchestrator(
                    connection_provider=connection_provider(connection_id, owner)
                ).investigate(question=request.question, progress=emit)
                emit("complete", _save_report(connection_id, result))
            except ValueError as exc:
                emit("error", {"message": str(exc)})
            except Exception:
                logger.exception("BI investigation stream failed")
                emit("error", {"message": "BI investigation could not be completed."})

        task = asyncio.create_task(asyncio.to_thread(investigate))
        yield _sse("started", {"question": request.question})
        while True:
            event, data = await events.get()
            yield _sse(event, data)
            if event in {"complete", "error"}:
                break
        await task

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/reports")
def list_reports(connection_id: str, limit: int = Query(default=30, ge=1, le=100), user: dict[str, object] = Depends(current_user)) -> dict[str, list[dict[str, Any]]]:
    owner = str(user["sub"])
    ensure_owned_database(connection_id, owner)
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""DELETE FROM bi_reports WHERE monitored_database_id = %s
                              AND is_pinned = false AND created_at < now() - interval '90 days'""", (connection_id,))
            cursor.execute("""SELECT id, question, is_pinned, created_at FROM bi_reports
                              WHERE monitored_database_id = %s ORDER BY is_pinned DESC, created_at DESC LIMIT %s""", (connection_id, limit))
            rows = cursor.fetchall()
    return {"data": [{"report_id": str(row[0]), "question": row[1], "is_pinned": row[2], "created_at": row[3]} for row in rows]}


@router.get("/reports/{report_id}", response_model=InvestigationResult)
def report(connection_id: str, report_id: str, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    owner = str(user["sub"])
    ensure_owned_database(connection_id, owner)
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT question, plan_json, generated_sql, result_json, insight_json, charts_json
                              FROM bi_reports WHERE id = %s AND monitored_database_id = %s""", (report_id, connection_id))
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="BI report not found")
    return _report_payload(report_id, row[0], row[1], row[2], row[3], row[4], row[5])


@router.patch("/reports/{report_id}")
def update_report(connection_id: str, report_id: str, payload: ReportUpdate, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    owner = str(user["sub"])
    ensure_owned_database(connection_id, owner)
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE bi_reports SET is_pinned = %s, updated_at = now()
                              WHERE id = %s AND monitored_database_id = %s""", (payload.is_pinned, report_id, connection_id))
            if cursor.rowcount != 1:
                raise HTTPException(status_code=404, detail="BI report not found")
    return {"report_id": report_id, "is_pinned": payload.is_pinned}
