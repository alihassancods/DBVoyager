"""Connection and ad-hoc query endpoints."""

from typing import Any
from uuid import uuid4

import psycopg2
from fastapi import APIRouter, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from .store import _connections, _credentials, _lock, _reports, get_connection


router = APIRouter()


class DatabaseCredentials(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: str
    sslmode: str = "prefer"


class QueryRequest(BaseModel):
    connection_id: str
    query: str = Field(min_length=1)


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def create_connection(credentials: DatabaseCredentials) -> dict[str, str]:
    connection_data = credentials.model_dump()
    try:
        connection = psycopg2.connect(**connection_data, connect_timeout=10)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail=f"Could not connect: {exc}") from exc

    connection_id = str(uuid4())
    with _lock:
        _connections[connection_id] = connection
        _credentials[connection_id] = connection_data
    return {"connection_id": connection_id}


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: str) -> None:
    with _lock:
        connection = _connections.pop(connection_id, None)
        _credentials.pop(connection_id, None)
        _reports.pop(connection_id, None)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not connection.closed:
        connection.close()


@router.post("/queries")
def execute_query(request: QueryRequest) -> dict[str, object]:
    connection = get_connection(request.connection_id)
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(request.query)
            rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
        connection.commit()
    except psycopg2.Error as exc:
        connection.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"rows": rows, "row_count": len(rows)}
