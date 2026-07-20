from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.auth import current_user
from src.api.main import app
from src.api.store import _connection_owners, _connections, _credentials, _reports, register_connection


client = TestClient(app)


def test_cors_temporarily_accepts_any_frontend_origin() -> None:
    response = client.options("/auth/signup", headers={
        "Origin": "https://frontend.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example"


def _owned_connection() -> None:
    _connections.clear()
    _credentials.clear()
    _reports.clear()
    _connection_owners.clear()
    connection = MagicMock()
    connection.closed = 0
    register_connection("connection-1", "owner", connection, {"database": "demo"})


def test_statistics_refresh_returns_a_collection_job() -> None:
    _owned_connection()
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.create_analysis_run", return_value="run-1"
        ) as create_run, patch("src.api.dashboard.run_analysis_in_background"):
            response = client.post("/connections/connection-1/statistics/refresh")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {"run_id": "run-1", "resource": "statistics", "status": "queued"}
    assert create_run.call_args.args == ("connection-1", "manual", "statistics")


def test_table_statistics_is_collecting_before_the_first_snapshot() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.dashboard.get_latest_statistics", side_effect=HTTPException(status_code=404)), patch(
            "src.api.dashboard.get_latest_collection_report", side_effect=HTTPException(status_code=404)
        ), patch("src.api.dashboard.get_latest_report", side_effect=HTTPException(status_code=404)):
            response = client.get("/connections/connection-1/statistics/tables")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "collecting", "data": []}


def test_optimizer_reads_persisted_slow_queries() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    rows = [{"query_id": "query-1", "query": "SELECT 1", "calls": 2}]
    try:
        with patch("src.api.optimizer.ensure_owned_database"), patch(
            "src.api.optimizer.get_latest_slow_queries", return_value=rows
        ):
            response = client.get("/connections/connection-1/optimizer/slow-queries")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"data": rows}


def test_bi_investigation_is_connection_scoped() -> None:
    _owned_connection()
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    result = {
        "question": "How many orders?",
        "plan": MagicMock(model_dump=lambda: {"tables": ["orders"]}),
        "sql": "SELECT count(*) AS orders FROM orders LIMIT 10",
        "rows": [{"orders": 4}],
        "row_count": 1,
        "insight": MagicMock(model_dump=lambda: {"summary": "Four orders."}),
        "charts": [],
    }
    try:
        app_connection = MagicMock()
        app_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = ("report-1",)
        with patch("src.api.business_api.ensure_owned_database"), patch(
            "src.api.business_api._app_connection", app_connection
        ), patch("src.api.business_api.BusinessIntelligenceOrchestrator") as orchestrator:
            orchestrator.return_value.investigate.return_value = result
            response = client.post(
                "/connections/connection-1/bi/investigations",
                json={"question": "How many orders?"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["result"] == {"columns": ["orders"], "rows": [{"orders": 4}], "row_count": 1}


def test_bi_investigation_streams_progress_and_report() -> None:
    _owned_connection()
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    result = {
        "question": "How many orders?",
        "plan": MagicMock(model_dump=lambda: {"tables": ["orders"]}),
        "sql": "SELECT count(*) AS orders FROM orders LIMIT 10",
        "rows": [{"orders": 4}],
        "row_count": 1,
        "insight": MagicMock(model_dump=lambda: {"summary": "Four orders."}),
        "charts": [],
    }

    def investigate(question: str, progress: object) -> dict[str, object]:
        progress("stage", {"stage": "plan", "status": "running", "detail": "Planning"})  # type: ignore[operator]
        progress("insight_delta", {"text": "Four orders."})  # type: ignore[operator]
        return result

    try:
        app_connection = MagicMock()
        app_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = ("report-1",)
        with patch("src.api.business_api.ensure_owned_database"), patch(
            "src.api.business_api._app_connection", app_connection
        ), patch("src.api.business_api.BusinessIntelligenceOrchestrator") as orchestrator:
            orchestrator.return_value.investigate.side_effect = investigate
            with client.stream("POST", "/connections/connection-1/bi/investigations/stream", json={"question": "How many orders?"}) as response:
                body = "".join(response.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "event: stage" in body
    assert "event: insight_delta" in body
    assert "event: complete" in body
