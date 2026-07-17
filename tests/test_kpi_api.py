from unittest.mock import patch

from fastapi.testclient import TestClient

from src.agent.kpi.models import KPIDefinition
from src.api.auth import current_user
from src.api.kpis import get_kpi_repository
from src.api.main import app


client = TestClient(app)


def test_kpi_candidates_and_chart_are_owner_scoped() -> None:
    definition = KPIDefinition(
        id="kpi-1", monitored_database_id="connection-1", schema_revision_id="schema-1",
        table_name="orders", measure_column="total", aggregation="sum", time_column="created_at",
        title="Monthly revenue", rationale="Order totals", confidence=1,
    )

    class Repository:
        def list_candidates(self, connection_id, status):
            assert (connection_id, status) == ("connection-1", "proposed")
            return [{"id": "candidate-1", "title": "Monthly revenue", "status": "proposed"}]

        def get_definition(self, definition_id, connection_id):
            return definition if (definition_id, connection_id) == ("kpi-1", "connection-1") else None

        def latest_snapshot(self, definition_id):
            assert definition_id == "kpi-1"
            return {
                "analysis_run_id": "run-1", "points": [{"period": "2026-07-01", "value": 42}],
                "execution_ms": 12.5, "generated_at": "2026-07-02T00:00:00Z", "row_count": 1,
            }

    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    app.dependency_overrides[get_kpi_repository] = lambda: Repository()
    try:
        with patch("src.api.kpis.ensure_owned_database") as owned:
            candidates = client.get("/connections/connection-1/kpis/candidates")
            chart = client.get("/connections/connection-1/kpis/definitions/kpi-1/chart")
    finally:
        app.dependency_overrides.clear()

    assert candidates.json()["data"][0]["id"] == "candidate-1"
    assert chart.json()["series"] == [{"name": "Monthly revenue", "points": [{"x": "2026-07-01", "y": 42}]}]
    assert owned.call_count == 2
