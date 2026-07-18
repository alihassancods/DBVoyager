from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.auth import current_user
from src.api.main import app
from src.api.store import _connection_owners, _connections, _credentials, _reports, register_connection


client = TestClient(app)


def test_connection_id_is_used_for_query() -> None:
    _connections.clear()
    _credentials.clear()
    _reports.clear()
    _connection_owners.clear()
    connection = MagicMock()
    connection.closed = 0
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.description = ("value",)
    cursor.fetchall.return_value = [{"value": 1}]

    app.dependency_overrides[current_user] = lambda: {"sub": "owner", "email": "owner@example.com"}
    try:
        with patch("src.api.connections.psycopg2.connect", return_value=connection), patch(
            "src.api.connections.save_connection", return_value="connection-1"
        ), patch("src.api.connections.create_analysis_run", return_value="run-1"), patch(
            "src.api.connections.run_analysis_in_background"
        ):
            response = client.post(
                "/connections",
                json={"host": "localhost", "database": "demo", "user": "user", "password": "secret"},
            )

        assert response.status_code == 201
        result = client.post(
            "/queries",
            json={"connection_id": response.json()["connection_id"], "query": "SELECT 1 AS value"},
        )
        app.dependency_overrides[current_user] = lambda: {"sub": "other"}
        denied = client.post(
            "/queries",
            json={"connection_id": response.json()["connection_id"], "query": "SELECT 1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.json() == {
        "connection_id": "connection-1",
        "analysis_run_id": "run-1",
        "analysis_status": "queued",
    }
    assert result.json() == {"rows": [{"value": 1}], "row_count": 1}
    assert denied.status_code == 404
    cursor.execute.assert_called_once_with("SELECT 1 AS value")
    connection.commit.assert_called_once()


def test_dashboard_refresh_persists_and_reads_the_latest_report() -> None:
    _connections.clear()
    _credentials.clear()
    _reports.clear()
    _connection_owners.clear()
    connection = MagicMock()
    connection.closed = 0
    report = {
        "statistics": {"status": "ok", "data": {"query_stats": [{"query": "slow", "calls": 2, "total_exec_time": 100.0, "mean_exec_time": 50.0}], "table_stats": [], "index_stats": [], "lock_stats": [], "database_stats": {}}},
        "health_checks": {"status": "ok", "data": [{"check": "locks", "severity": "critical", "message": "blocked"}]},
        "schema": {"status": "ok", "data": {"tables": []}},
        "schema_visualization": {"status": "ok", "data": "erDiagram"},
    }
    register_connection("connection-1", "owner", connection, {"database": "demo"})
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    run = {"analysis_run_id": "run-1", "status": "succeeded", "report": report}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.create_analysis_run", return_value="run-1"
        ), patch("src.api.dashboard.run_analysis", return_value=report), patch(
            "src.api.dashboard.get_latest_report", return_value=report
        ), patch(
            "src.api.dashboard.get_latest_collection_report", return_value=report
        ), patch(
            "src.api.dashboard.get_analysis_run", return_value=run
        ):
            refreshed = client.post("/connections/connection-1/dashboard/refresh")
            run_status = client.get("/connections/connection-1/analysis-runs/run-1")
            health = client.get("/connections/connection-1/health-checks?severity=critical")
            queries = client.get("/connections/connection-1/statistics/queries?sort=calls")
            diagram = client.get("/connections/connection-1/schema/diagram")
    finally:
        app.dependency_overrides.clear()

    assert refreshed.json() == report
    assert run_status.json() == run
    assert health.json()["data"] == report["health_checks"]["data"]
    assert queries.json()["data"] == report["statistics"]["data"]["query_stats"]
    assert diagram.json() == report["schema_visualization"]


def test_dashboard_refresh_stream_emits_progress_and_report() -> None:
    _connections.clear()
    _credentials.clear()
    _reports.clear()
    _connection_owners.clear()
    connection = MagicMock()
    connection.closed = 0
    report = {"statistics": {"status": "ok", "data": {}}, "health_checks": {"status": "ok", "data": []}}
    register_connection("connection-1", "owner", connection, {"database": "demo"})
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        def collect(
            _run_id: str,
            _connection_id: str,
            _database: str,
            _provider: object,
            progress: object,
        ) -> dict[str, object]:
            progress("statistics", "started")
            progress("statistics", "completed")
            return report

        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.create_analysis_run", return_value="run-1"
        ), patch("src.api.dashboard.run_analysis", side_effect=collect):
            with client.stream("POST", "/connections/connection-1/dashboard/refresh/stream") as response:
                events = "".join(response.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: progress\ndata: {"stage": "statistics", "status": "started"}' in events
    assert 'event: complete\ndata: {"statistics": {"status": "ok", "data": {}}' in events


def test_analysis_run_stream_emits_terminal_report() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    run = {"analysis_run_id": "run-1", "status": "succeeded", "report": {"ok": True}}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.get_analysis_run", return_value=run
        ):
            with client.stream("GET", "/connections/connection-1/analysis-runs/run-1/stream") as response:
                events = "".join(response.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: complete\ndata: {"analysis_run_id": "run-1", "status": "succeeded"' in events
