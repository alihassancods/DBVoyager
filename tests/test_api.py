from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import _connections, app
from src.api.store import _credentials, _reports


client = TestClient(app)


def test_connection_id_is_used_for_query() -> None:
    _connections.clear()
    _credentials.clear()
    _reports.clear()
    connection = MagicMock()
    connection.closed = 0
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.description = ("value",)
    cursor.fetchall.return_value = [{"value": 1}]

    with patch("src.api.connections.psycopg2.connect", return_value=connection):
        response = client.post(
            "/connections",
            json={"host": "localhost", "database": "demo", "user": "user", "password": "secret"},
        )

    assert response.status_code == 201
    result = client.post(
        "/queries",
        json={"connection_id": response.json()["connection_id"], "query": "SELECT 1 AS value"},
    )
    assert result.json() == {"rows": [{"value": 1}], "row_count": 1}
    cursor.execute.assert_called_once_with("SELECT 1 AS value")
    connection.commit.assert_called_once()


def test_dashboard_routes_read_the_cached_refresh_report() -> None:
    _connections.clear()
    _credentials.clear()
    _reports.clear()
    connection = MagicMock()
    connection.closed = 0
    report = {
        "statistics": {"status": "ok", "data": {"query_stats": [{"query": "slow", "calls": 2, "total_exec_time": 100.0, "mean_exec_time": 50.0}], "table_stats": [], "index_stats": [], "lock_stats": [], "database_stats": {}}},
        "health_checks": {"status": "ok", "data": [{"check": "locks", "severity": "critical", "message": "blocked"}]},
        "schema": {"status": "ok", "data": {"tables": []}},
        "schema_visualization": {"status": "ok", "data": "erDiagram"},
    }
    with patch("src.api.connections.psycopg2.connect", return_value=connection):
        created = client.post("/connections", json={"host": "localhost", "database": "demo", "user": "user", "password": "secret"})
    connection_id = created.json()["connection_id"]

    with patch("src.api.dashboard.build_report", return_value=report) as build:
        refreshed = client.post(f"/connections/{connection_id}/dashboard/refresh")

    assert refreshed.json() == report
    assert build.call_count == 1
    assert client.get(f"/connections/{connection_id}/health-checks?severity=critical").json()["data"] == report["health_checks"]["data"]
    assert client.get(f"/connections/{connection_id}/statistics/queries?sort=calls").json()["data"] == report["statistics"]["data"]["query_stats"]
    assert client.get(f"/connections/{connection_id}/schema/diagram").json() == report["schema_visualization"]


def test_dashboard_refresh_stream_emits_progress_and_report() -> None:
    _connections.clear()
    _credentials.clear()
    _reports.clear()
    connection = MagicMock()
    connection.closed = 0
    report = {"statistics": {"status": "ok", "data": {}}, "health_checks": {"status": "ok", "data": []}}
    with patch("src.api.connections.psycopg2.connect", return_value=connection):
        created = client.post("/connections", json={"host": "localhost", "database": "demo", "user": "user", "password": "secret"})

    def collect(_database: str, _provider: object, progress: object) -> dict[str, object]:
        progress("statistics", "started")
        progress("statistics", "completed")
        return report

    with patch("src.api.dashboard.build_report", side_effect=collect):
        with client.stream("POST", f"/connections/{created.json()['connection_id']}/dashboard/refresh/stream") as response:
            events = "".join(response.iter_text())

    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: progress\ndata: {"stage": "statistics", "status": "started"}' in events
    assert 'event: complete\ndata: {"statistics": {"status": "ok", "data": {}}' in events
