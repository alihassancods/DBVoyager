from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.auth import current_user
from src.api.main import app


client = TestClient(app)


def test_query_detail_is_owner_scoped() -> None:
    detail = {
        "query_id": "query-1",
        "query": "SELECT id FROM orders",
        "calls": 4,
        "total_exec_time": 120.0,
        "mean_exec_time": 30.0,
        "rows_returned": 2,
        "collected_at": "2026-01-01T00:00:00Z",
        "cache_hit_ratio": 99.2,
    }
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.optimizer.ensure_owned_database") as ownership, patch(
            "src.api.optimizer.get_slow_query_detail", return_value=detail
        ):
            response = client.get("/connections/connection-1/optimizer/queries/query-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == detail
    ownership.assert_called_once_with("connection-1", "owner")


def test_query_plan_validates_stored_sql_before_explain() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    plan = MagicMock()
    plan.costs.model_dump.return_value = {"startup_cost": 0.0, "total_cost": 12.3, "plan_rows": 2}
    plan.raw_plan = [{"Plan": {"Node Type": "Seq Scan", "Startup Cost": 0.0, "Total Cost": 12.3, "Plan Rows": 2}}]
    try:
        with patch("src.api.optimizer.ensure_owned_database"), patch(
            "src.api.optimizer.get_connection"
        ), patch("src.api.optimizer.connection_provider"), patch(
            "src.api.optimizer.get_slow_query_detail", return_value={"query": "SELECT id FROM orders"}
        ), patch("src.api.optimizer.ExplainPlanInspector.get_plan", return_value=plan) as explain:
            response = client.post("/connections/connection-1/optimizer/queries/query-1/plan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["costs"]["total_cost"] == 12.3
    explain.assert_called_once_with("SELECT id FROM orders")


def test_query_plan_rejects_unsafe_stored_sql() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.optimizer.ensure_owned_database"), patch(
            "src.api.optimizer.get_connection"
        ), patch(
            "src.api.optimizer.get_slow_query_detail", return_value={"query": "DELETE FROM orders"}
        ), patch("src.api.optimizer.ExplainPlanInspector.get_plan") as explain:
            response = client.post("/connections/connection-1/optimizer/queries/query-1/plan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "unsafe" in response.json()["detail"].lower()
    explain.assert_not_called()
