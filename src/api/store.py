"""In-memory state for the small local DBVoyager API."""

from collections.abc import Callable
from threading import Lock
from typing import Any

import psycopg2
from fastapi import HTTPException


_connections: dict[str, Any] = {}
_credentials: dict[str, dict[str, Any]] = {}
_reports: dict[str, dict[str, Any]] = {}
_lock = Lock()


def get_connection(connection_id: str) -> Any:
    with _lock:
        connection = _connections.get(connection_id)
    if connection is None or connection.closed:
        raise HTTPException(status_code=404, detail="Connection not found or closed")
    return connection


def connection_provider(connection_id: str) -> Callable[[], Any]:
    with _lock:
        credentials = _credentials.get(connection_id)
    if credentials is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return lambda: psycopg2.connect(**credentials, connect_timeout=10)


def get_report(connection_id: str) -> dict[str, Any]:
    with _lock:
        report = _reports.get(connection_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No dashboard report; refresh it first")
    return report
