from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.auth import current_user
from src.api.main import _interval_seconds, app
from src.api.store import _connection_owners, _connections, _credentials, _reports, get_connection, register_connection


client = TestClient(app)


def test_agent_interval_uses_env_and_rejects_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("DBVOYAGER_AGENT_INTERVAL_SECONDS", "1800")
    assert _interval_seconds("DBVOYAGER_AGENT_INTERVAL_SECONDS", 60) == 1800
    monkeypatch.setenv("DBVOYAGER_AGENT_INTERVAL_SECONDS", "invalid")
    assert _interval_seconds("DBVOYAGER_AGENT_INTERVAL_SECONDS", 60) == 60


def test_connection_cache_miss_reloads_encrypted_credentials() -> None:
    _connections.clear()
    _credentials.clear()
    _connection_owners.clear()
    connection = MagicMock()
    connection.closed = 0

    with patch("src.api.store.load_connection_credentials", return_value={"database": "demo"}) as load, patch(
        "src.api.store.psycopg2.connect", return_value=connection
    ):
        assert get_connection("connection-1", "owner") is connection

    load.assert_called_once_with("connection-1", "owner")


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
        ), patch("src.api.connections.create_collection_schedules"
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
        "brief_run_id": "run-1",
        "deep_analysis_run_id": "run-1",
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
        ), patch("src.api.dashboard.run_analysis_in_background"), patch(
            "src.api.dashboard.get_latest_report", return_value=report
        ), patch(
            "src.api.dashboard.get_latest_health_findings", return_value=report["health_checks"]["data"]
        ), patch(
            "src.api.dashboard.get_latest_statistics", return_value=report["statistics"]["data"]
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

    assert refreshed.status_code == 202
    assert refreshed.json() == {"run_id": "run-1", "resource": "dashboard", "status": "queued"}
    assert run_status.json() == run
    assert health.json()["data"] == report["health_checks"]["data"]
    assert queries.json()["data"] == report["statistics"]["data"]["query_stats"]
    assert diagram.json() == report["schema_visualization"]


def test_health_checks_exposes_a_failed_collection() -> None:
    _connections.clear()
    _credentials.clear()
    _connection_owners.clear()
    register_connection("connection-1", "owner", MagicMock(), {"database": "demo"})
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    failed_report = {"health_checks": {"status": "error", "error": "NameError: name '_row' is not defined"}}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.get_latest_health_findings", side_effect=HTTPException(status_code=404)
        ), patch("src.api.dashboard.get_latest_collection_report", return_value=failed_report), patch(
            "src.api.dashboard.has_active_analysis", return_value=False
        ):
            response = client.get("/connections/connection-1/health-checks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {"detail": "NameError: name '_row' is not defined"}


def test_health_checks_waits_for_an_active_refresh() -> None:
    _connections.clear()
    _credentials.clear()
    _connection_owners.clear()
    register_connection("connection-1", "owner", MagicMock(), {"database": "demo"})
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    failed_report = {"health_checks": {"status": "error", "error": "old failure"}}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.get_latest_health_findings", side_effect=HTTPException(status_code=404)
        ), patch("src.api.dashboard.get_latest_collection_report", return_value=failed_report), patch(
            "src.api.dashboard.has_active_analysis", return_value=True
        ):
            response = client.get("/connections/connection-1/health-checks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["status"] == "collecting"


def test_overview_is_collecting_before_the_first_report_exists() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch("src.api.dashboard.get_dashboard_summary", return_value=None), patch(
            "src.api.dashboard.get_latest_collection_report", side_effect=HTTPException(status_code=404)
        ), patch("src.api.dashboard.get_latest_report", side_effect=HTTPException(status_code=404)):
            response = client.get("/connections/connection-1/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {"collection_status": "collecting"}


def test_dashboard_refresh_stream_emits_progress_and_compact_completion() -> None:
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
        def collect(*_args: object) -> dict[str, object]:
            progress, section_ready = _args[4], _args[6]
            progress("statistics", "started")
            progress("statistics", "completed")
            section_ready("statistics", report["statistics"])
            return report

        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.create_analysis_run", return_value="run-1"
        ), patch("src.api.dashboard.collect_analysis", side_effect=collect), patch(
            "src.api.dashboard.publish_preview", return_value=True
        ):
            with client.stream("POST", "/connections/connection-1/dashboard/refresh/stream") as response:
                events = "".join(response.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: progress\ndata: {"stage": "statistics", "status": "started"}' in events
    assert 'event: section_ready\ndata: {"section": "statistics", "data": {"status": "ok", "data": {}}}' in events
    assert 'event: complete\ndata: {"analysis_run_id": "run-1", "status": "succeeded"}' in events
    assert "event: data_ready" not in events


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
