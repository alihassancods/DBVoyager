from unittest.mock import patch
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.agent.kpi.models import KPIDefinition
from src.api.auth import current_user
from src.api.kpis import _generate_and_invalidate, get_kpi_repository
from src.api.main import app
from src.models.schema.column_model import ColumnInfo
from src.models.schema.schema_model import DatabaseSchema
from src.models.schema.table_model import TableInfo


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
                "execution_ms": 12.5, "generated_at": datetime(2026, 7, 2, tzinfo=UTC), "row_count": 1,
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
    assert response.json()["data"][0]["chart"]["source"]["generated_at"] == "2026-07-02T00:00:00+00:00"


def test_custom_kpi_create_validates_schema_and_uses_owner_scope() -> None:
    schema = DatabaseSchema(
        tables=[TableInfo(schema_name="public", table_name="orders", table_type="BASE TABLE", estimated_rows=1)],
        columns=[ColumnInfo(table_name="orders", column_name="total", data_type="numeric", is_nullable=False, column_default=None, ordinal_position=1)],
        primary_keys=[], foreign_keys=[], relations=[], indexes=[],
    )
    created = KPIDefinition(
        id="custom-1", monitored_database_id="connection-1", schema_revision_id="schema-1",
        table_name="orders", measure_column="total", aggregation="sum", title="Revenue",
        rationale="Order totals", confidence=1,
    )

    class Repository:
        def current_schema_context(self, connection_id):
            assert connection_id == "connection-1"
            return "schema-1", schema, {}

        def create_definition(self, connection_id, revision_id, candidate):
            assert (connection_id, revision_id, candidate.title) == ("connection-1", "schema-1", "Revenue")
            return created

    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    app.dependency_overrides[get_kpi_repository] = lambda: Repository()
    try:
        with patch("src.api.kpis.ensure_owned_database") as owned:
            response = client.post("/connections/connection-1/kpis/definitions", json={
                "table_name": "orders", "measure_column": "total", "aggregation": "sum",
                "title": "Revenue", "rationale": "Order totals", "confidence": 1,
            })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == "custom-1"
    owned.assert_called_once_with("connection-1", "owner")


def test_kpi_generation_status_has_idle_default() -> None:
    class Repository:
        def generation_status(self, connection_id):
            assert connection_id == "connection-1"
            return None

    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    app.dependency_overrides[get_kpi_repository] = lambda: Repository()
    try:
        with patch("src.api.kpis.ensure_owned_database"):
            response = client.get("/connections/connection-1/kpis/generation")
    finally:
        app.dependency_overrides.clear()

    assert response.json()["status"] == "idle"


def test_generation_invalidates_dashboard_after_background_work() -> None:
    provider = object()

    with patch("src.api.kpis.generate_kpis") as generate, patch("src.api.kpis.invalidate") as invalidate:
        _generate_and_invalidate("connection-1", provider)

    generate.assert_called_once_with("connection-1", provider)
    invalidate.assert_called_once_with("connection-1", "kpis/dashboard")
