"""Connection and ad-hoc query endpoints."""

from typing import Any

import psycopg2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from .auth import current_user
from .analysis_repository import create_analysis_run, run_analysis_in_background
from .connection_repository import connection_metadata, list_connections, load_connection_credentials, rename_connection, save_connection, set_archived
from .store import _connections, _connection_owners, _credentials, _lock, _reports, connection_provider, get_connection, register_connection
from src.agent.business_intelligence.validator import SQLValidator


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


class ConnectionUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


class ScopedQueryRequest(BaseModel):
    query: str = Field(min_length=1)


@router.get("/connections")
def connections(user: dict[str, object] = Depends(current_user)) -> dict[str, list[dict[str, Any]]]:
    return {"data": list_connections(str(user["sub"]))}


@router.get("/connections/{connection_id}")
def connection_details(connection_id: str, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    return connection_metadata(connection_id, str(user["sub"]))


@router.patch("/connections/{connection_id}")
def update_connection(connection_id: str, payload: ConnectionUpdateRequest, user: dict[str, object] = Depends(current_user)) -> dict[str, Any]:
    return rename_connection(connection_id, str(user["sub"]), payload.display_name)


@router.post("/connections/{connection_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_connection(connection_id: str, user: dict[str, object] = Depends(current_user)) -> None:
    set_archived(connection_id, str(user["sub"]), True)


@router.post("/connections/{connection_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_connection(connection_id: str, user: dict[str, object] = Depends(current_user)) -> None:
    set_archived(connection_id, str(user["sub"]), False)


@router.post("/connections/{connection_id}/reconnect")
def reconnect_connection(connection_id: str, user: dict[str, object] = Depends(current_user)) -> dict[str, str]:
    owner = str(user["sub"])
    credentials = load_connection_credentials(connection_id, owner)
    try:
        connection = psycopg2.connect(**credentials, connect_timeout=10)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail="Could not reconnect to database") from exc
    register_connection(connection_id, owner, connection, credentials)
    return {"connection_id": connection_id, "status": "connected"}


@router.post("/connections/{connection_id}/test")
def test_connection(
    connection_id: str, credentials: DatabaseCredentials, user: dict[str, object] = Depends(current_user)
) -> dict[str, str]:
    """Validate supplied credentials without persisting them."""
    connection_metadata(connection_id, str(user["sub"]))
    connection_data = credentials.model_dump(exclude={"display_name"})
    try:
        connection = psycopg2.connect(**connection_data, connect_timeout=10)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail="Could not connect to database") from exc
    connection.close()
    return {"status": "ok"}


@router.post("/connections/{connection_id}/queries")
def execute_connection_query(
    connection_id: str, request: ScopedQueryRequest, user: dict[str, object] = Depends(current_user)
) -> dict[str, object]:
    return execute_query(QueryRequest(connection_id=connection_id, query=request.query), user)


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
    validation = SQLValidator().validate(request.query)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail=validation.reason)
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
