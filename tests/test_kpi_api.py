from unittest.mock import patch

from fastapi.testclient import TestClient

from src.agent.kpi.models import KPIDefinition
from src.api.auth import current_user
from src.api.kpis import get_kpi_repository
from src.api.main import app


client = TestClient(app)


def test_kpi_chart_is_owner_scoped() -> None:
    definition = KPIDefinition(
        id="kpi-1", monitored_database_id="connection-1", schema_revision_id="schema-1",
        table_name="orders", measure_column="total", aggregation="sum", time_column="created_at",
        title="Monthly revenue", rationale="Order totals", confidence=1,
    )

    class Repository:
        def get_definition(self, definition_id, connection_id):
            return definition if (definition_id, connection_id) == ("kpi-1", "connection-1") else None

        def latest_snapshot(self, definition_id, monitored_database_id=None):
            assert (definition_id, monitored_database_id) == ("kpi-1", "connection-1")
            return {
                "analysis_run_id": "run-1", "points": [{"period": "2026-07-01", "value": 42}],
                "execution_ms": 12.5, "generated_at": "2026-07-02T00:00:00Z", "row_count": 1,
            }

    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    app.dependency_overrides[get_kpi_repository] = lambda: Repository()
    try:
        with patch("src.api.kpis.ensure_owned_database") as owned:
            chart = client.get("/connections/connection-1/kpis/definitions/kpi-1/chart")
    finally:
        app.dependency_overrides.clear()

    assert chart.json()["series"] == [{"name": "Monthly revenue", "points": [{"x": "2026-07-01", "y": 42}]}]
    owned.assert_called_once_with("connection-1", "owner")


def test_kpi_dashboard_fetches_database_snapshots_in_one_call() -> None:
    definition = KPIDefinition(
        id="kpi-1", monitored_database_id="connection-1", schema_revision_id="schema-1",
        table_name="orders", measure_column="total", aggregation="sum", time_column="created_at",
        title="Monthly revenue", rationale="Order totals", confidence=1,
    )

    class Repository:
        def list_definitions(self, connection_id):
            assert connection_id == "connection-1"
            return [definition]

        def latest_snapshots(self, connection_id):
            assert connection_id == "connection-1"
            return {"kpi-1": {
                "analysis_run_id": "run-1", "points": [{"period": "2026-07-01", "value": 42}],
                "execution_ms": 12.5, "generated_at": "2026-07-02T00:00:00Z", "row_count": 1,
            }}

        def generation_status(self, connection_id):
            assert connection_id == "connection-1"
            return {"status": "succeeded"}

    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    app.dependency_overrides[get_kpi_repository] = lambda: Repository()
    try:
        with patch("src.api.kpis.ensure_owned_database"):
            response = client.get("/connections/connection-1/kpis/dashboard")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"][0]["chart"]["kpi_id"] == "kpi-1"
