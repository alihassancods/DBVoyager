"""Connection cache backed by encrypted application-database credentials."""

from collections.abc import Callable
from threading import Lock
from typing import Any

import psycopg2
from fastapi import HTTPException

from .connection_repository import load_connection_credentials


_connections: dict[str, Any] = {}
_credentials: dict[str, dict[str, Any]] = {}
_reports: dict[str, dict[str, Any]] = {}
_connection_owners: dict[str, str] = {}
_lock = Lock()


def register_connection(connection_id: str, owner_subject: str, connection: Any, credentials: dict[str, Any]) -> None:
    with _lock:
        _connections[connection_id] = connection
        _credentials[connection_id] = credentials
        _connection_owners[connection_id] = owner_subject


def get_connection(connection_id: str, owner_subject: str | None = None) -> Any:
    with _lock:
        connection = _connections.get(connection_id)
        owner = _connection_owners.get(connection_id)
    if connection is not None and owner_subject is not None and owner != owner_subject:
        raise HTTPException(status_code=404, detail="Connection not found or closed")
    if connection is None or connection.closed:
        if owner_subject is None:
            raise HTTPException(status_code=404, detail="Connection not found or closed")
        credentials = load_connection_credentials(connection_id, owner_subject)
        try:
            connection = psycopg2.connect(**credentials, connect_timeout=10)
        except psycopg2.Error as exc:
            raise HTTPException(status_code=400, detail="Could not reconnect to database") from exc
        register_connection(connection_id, owner_subject, connection, credentials)
    return connection


def connection_provider(connection_id: str, owner_subject: str | None = None) -> Callable[[], Any]:
    with _lock:
        credentials = _credentials.get(connection_id)
    if credentials is None:
        if owner_subject is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        credentials = load_connection_credentials(connection_id, owner_subject)
        with _lock:
            _credentials[connection_id] = credentials
    return lambda: psycopg2.connect(**credentials, connect_timeout=10)


def get_database_name(connection_id: str, owner_subject: str | None = None) -> str:
    with _lock:
        credentials = _credentials.get(connection_id)
    if credentials is None:
        if owner_subject is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        credentials = load_connection_credentials(connection_id, owner_subject)
        with _lock:
            _credentials[connection_id] = credentials
    return str(credentials["database"])


def get_report(connection_id: str) -> dict[str, Any]:
    with _lock:
        report = _reports.get(connection_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No dashboard report; refresh it first")
    return report
