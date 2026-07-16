"""FastAPI endpoints for connecting to and querying PostgreSQL databases."""

from threading import Lock
from uuid import uuid4

import psycopg2
from fastapi import FastAPI, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field


app = FastAPI(title="DBVoyager API")


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


_connections: dict[str, object] = {}
_connections_lock = Lock()


@app.post("/connections", status_code=status.HTTP_201_CREATED)
def create_connection(credentials: DatabaseCredentials) -> dict[str, str]:
    try:
        connection = psycopg2.connect(**credentials.model_dump(), connect_timeout=10)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail=f"Could not connect: {exc}") from exc

    connection_id = str(uuid4())
    with _connections_lock:
        _connections[connection_id] = connection
    return {"connection_id": connection_id}


@app.post("/queries")
def execute_query(request: QueryRequest) -> dict[str, object]:
    with _connections_lock:
        connection = _connections.get(request.connection_id)
    if connection is None or connection.closed:
        raise HTTPException(status_code=404, detail="Connection not found or closed")

    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(request.query)
            rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
        connection.commit()
    except psycopg2.Error as exc:
        connection.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"rows": rows, "row_count": len(rows)}
