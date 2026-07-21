"""Small frontend-facing settings and audit endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import Json

from .analysis_repository import _app_connection, ensure_owned_database
from .auth import current_user


router = APIRouter(prefix="/connections/{connection_id}", tags=["management"])


def _owner(user: dict[str, object]) -> str:
    return str(user["sub"])


@router.get("/audit-events")
def audit_events(
    connection_id: str, limit: int = Query(default=20, ge=1, le=100),
    user: dict[str, object] = Depends(current_user),
) -> dict[str, list[dict[str, Any]]]:
    ensure_owned_database(connection_id, _owner(user))
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT id, event_type, metadata, created_at FROM audit_events
                              WHERE monitored_database_id = %s ORDER BY created_at DESC LIMIT %s""",
                           (connection_id, limit))
            rows = cursor.fetchall()
    return {"data": [{"event_id": str(row[0]), "event_type": row[1], "metadata": row[2], "created_at": row[3]} for row in rows]}


@router.get("/settings")
def settings(connection_id: str, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    ensure_owned_database(connection_id, _owner(user))
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT settings FROM database_settings WHERE monitored_database_id = %s", (connection_id,))
            row = cursor.fetchone()
    return {"data": row[0] if row else {}}


@router.patch("/settings")
def update_settings(
    connection_id: str, payload: dict[str, Any], user: dict[str, object] = Depends(current_user)
) -> dict[str, Any]:
    ensure_owned_database(connection_id, _owner(user))
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO database_settings (monitored_database_id, settings)
                              VALUES (%s, %s) ON CONFLICT (monitored_database_id)
                              DO UPDATE SET settings = EXCLUDED.settings, updated_at = now()""",
                           (connection_id, Json(payload)))
    return {"data": payload}


@router.get("/agent-reports/{report_id}")
def agent_report(connection_id: str, report_id: str, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    ensure_owned_database(connection_id, _owner(user))
    with _app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT id, agent_kind, title, severity, report_json, created_at
                              FROM agent_reports WHERE id = %s AND monitored_database_id = %s""", (report_id, connection_id))
            row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent report not found")
    return {"report_id": str(row[0]), "agent_kind": row[1], "title": row[2], "severity": row[3], "report": row[4], "created_at": row[5]}
