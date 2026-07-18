"""Connection and ad-hoc query endpoints."""

from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import psycopg2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field, field_validator, model_validator

from .auth import current_user
from .analysis_repository import create_analysis_run, create_collection_schedules, run_analysis_in_background
from .connection_repository import connection_metadata, list_connections, load_connection_credentials, rename_connection, save_connection, set_archived
from .store import _connections, _connection_owners, _credentials, _lock, _reports, connection_provider, get_connection, register_connection
from src.agent.business_intelligence.validator import SQLValidator


router = APIRouter()


class DatabaseCredentials(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    connection_url: str | None = Field(default=None, min_length=1, max_length=2_000)
    host: str | None = Field(default=None, min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, min_length=1)
    user: str | None = Field(default=None, min_length=1)
    password: str | None = None
    sslmode: str = "require"

    @field_validator("display_name", mode="before")
    @classmethod
    def blank_display_name_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def normalize_connection_url(self) -> "DatabaseCredentials":
        if self.connection_url:
            parsed = urlsplit(self.connection_url.strip())
            if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.username or parsed.password is None or not parsed.path.strip("/") or parsed.fragment:
                raise ValueError("Enter a complete postgresql://user:password@host:port/database URL")
            self.host = parsed.hostname
            self.port = parsed.port or 5432
            self.database = unquote(parsed.path.strip("/"))
            self.user = unquote(parsed.username)
            self.password = unquote(parsed.password)
            self.sslmode = parse_qs(parsed.query).get("sslmode", [self.sslmode])[0]
        self.port = self.port or 5432
        if not all((self.host, self.port, self.database, self.user, self.password)):
            raise ValueError("Provide a complete PostgreSQL connection URL")
        return self

    def connection_options(self) -> dict[str, object]:
        return self.model_dump(exclude={"display_name", "connection_url"}, exclude_none=True)


class QueryRequest(BaseModel):
    connection_id: str
    query: str = Field(min_length=1)


class ConnectionUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


class ScopedQueryRequest(BaseModel):
    query: str = Field(min_length=1)


def _test_credentials(credentials: DatabaseCredentials) -> None:
    try:
        connection = psycopg2.connect(**credentials.connection_options(), connect_timeout=10)
    except psycopg2.Error as exc:
        raise HTTPException(status_code=400, detail="Could not connect to database") from exc
    connection.close()


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
    _test_credentials(credentials)
    return {"status": "ok"}


@router.post("/connections/test")
def test_new_connection(
    credentials: DatabaseCredentials, user: dict[str, object] = Depends(current_user)
) -> dict[str, str]:
    """Validate new credentials before they are persisted."""
    _test_credentials(credentials)
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
    connection_data = credentials.connection_options()
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
    create_collection_schedules(connection_id)
    brief_run_id = create_analysis_run(connection_id, "initial", "brief")
    deep_run_id = create_analysis_run(connection_id, "initial")
    background_tasks.add_task(
        run_analysis_in_background,
        brief_run_id,
        connection_id,
        connection_data["database"],
        connection_provider(connection_id, str(user["sub"])),
        "brief",
    )
    background_tasks.add_task(
        run_analysis_in_background,
        deep_run_id,
        connection_id,
        connection_data["database"],
        connection_provider(connection_id, str(user["sub"])),
    )
    return {"connection_id": connection_id, "brief_run_id": brief_run_id, "deep_analysis_run_id": deep_run_id, "analysis_status": "queued"}


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
