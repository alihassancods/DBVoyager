"""Connection and ad-hoc query endpoints."""

from typing import Any

import psycopg2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from .auth import current_user
from .analysis_repository import create_analysis_run, run_analysis_in_background
from .connection_repository import save_connection
from .store import _connections, _connection_owners, _credentials, _lock, _reports, connection_provider, get_connection, register_connection


router = APIRouter()


class DatabaseCredentials(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: str
    sslmode: str = "require"


class QueryRequest(BaseModel):
    connection_id: str
    query: str = Field(min_length=1)


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def create_connection(
    credentials: DatabaseCredentials,
    background_tasks: BackgroundTasks,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, str]:
    connection_data = credentials.model_dump(exclude={"display_name"})
    try:
        connection = psycopg2.connect(**connection_data, connect_timeout=10)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail=f"Could not connect: {exc}") from exc

    try:
        connection_id = save_connection(
            auth_subject=str(user["sub"]),
            email=str(user["email"]) if user.get("email") else None,
            display_name=credentials.display_name or credentials.database,
            credentials=connection_data,
        )
    except Exception:
        connection.close()
        raise
    register_connection(connection_id, str(user["sub"]), connection, connection_data)
    run_id = create_analysis_run(connection_id, "initial")
    background_tasks.add_task(
        run_analysis_in_background,
        run_id,
        connection_id,
        connection_data["database"],
        connection_provider(connection_id),
    )
    return {"connection_id": connection_id, "analysis_run_id": run_id, "analysis_status": "queued"}


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: str,
    user: dict[str, object] = Depends(current_user),
) -> None:
    with _lock:
        if _connection_owners.get(connection_id) != str(user["sub"]):
            raise HTTPException(status_code=404, detail="Connection not found")
        connection = _connections.pop(connection_id, None)
        _credentials.pop(connection_id, None)
        _reports.pop(connection_id, None)
        _connection_owners.pop(connection_id, None)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection.closed:
        connection.close()


@router.post("/queries")
def execute_query(
    request: QueryRequest,
    user: dict[str, object] = Depends(current_user),
) -> dict[str, object]:
    connection = get_connection(request.connection_id, str(user["sub"]))
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(request.query)
            rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
        connection.commit()
    except psycopg2.Error as exc:
        connection.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"rows": rows, "row_count": len(rows)}
