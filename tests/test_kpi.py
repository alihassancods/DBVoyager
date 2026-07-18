import json
from unittest.mock import patch

import pytest

from src.agent.kpi.auto import generate_kpis
from src.agent.kpi.discovery import KPIDiscoveryAgent, KPIDiscoveryUnavailable
from src.agent.kpi.executor import KPIAggregateExecutor
from src.agent.kpi.models import KPICandidate, KPIDefinition, KPISnapshot
from src.models.schema.column_model import ColumnInfo
from src.models.schema.key_model import ForeignKeyInfo
from src.models.schema.schema_model import DatabaseSchema
from src.models.schema.table_model import TableInfo


def _schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=[TableInfo(schema_name="public", table_name="orders", table_type="BASE TABLE", estimated_rows=50_000_000)],
        columns=[
            ColumnInfo(table_name="orders", column_name="total", data_type="numeric", is_nullable=False, column_default=None, ordinal_position=1),
            ColumnInfo(table_name="orders", column_name="email", data_type="text", is_nullable=False, column_default=None, ordinal_position=2),
        ],
        primary_keys=[], foreign_keys=[], relations=[], indexes=[],
    )


def test_kpi_discovery_rejects_sensitive_columns() -> None:
    class LLM:
        def invoke(self, _prompt):
            return type("Response", (), {"content": "```json\n" + json.dumps([
                {"table_name": "orders", "measure_column": "total", "aggregation": "sum", "title": "Revenue", "rationale": "Order totals", "confidence": 0.9},
                {"table_name": "orders", "measure_column": "email", "aggregation": "count", "title": "Emails", "rationale": "Unsafe", "confidence": 0.9},
            ]) + "\n```"})()

    candidates = KPIDiscoveryAgent(LLM()).discover(_schema(), {})

    assert [candidate.title for candidate in candidates] == ["Revenue"]


def test_kpi_discovery_accepts_null_time_grain() -> None:
    class LLM:
        def invoke(self, _prompt):
            return type("Response", (), {"content": json.dumps([
                {"table_name": "orders", "measure_column": "total", "aggregation": "sum", "time_grain": None,
                 "title": "Revenue", "rationale": "Order totals", "confidence": 0.9},
            ])})()

    assert KPIDiscoveryAgent(LLM()).discover(_schema(), {})[0].time_grain == "month"


def test_kpi_discovery_accepts_wrapped_alias_response() -> None:
    class LLM:
        def invoke(self, _prompt):
            return type("Response", (), {"content": "```json\n" + json.dumps({"candidates": [
                {"table": "orders", "metric": "total", "aggregation": "average", "time_grain": "monthly",
                 "name": "Average order", "description": "Order totals", "confidence": 0.9},
                {"table": "orders", "aggregation": "not-a-real-aggregate"},
            ]}) + "\n```"})()

    candidate = KPIDiscoveryAgent(LLM()).discover(_schema(), {})[0]

    assert (candidate.aggregation, candidate.time_grain, candidate.title) == ("avg", "month", "Average order")


def test_kpi_discovery_reports_unavailable_llm() -> None:
    class LLM:
        def invoke(self, _prompt):
            raise ValueError("DEEPSEEK_API_KEY is required")

    with pytest.raises(KPIDiscoveryUnavailable):
        KPIDiscoveryAgent(LLM()).discover(_schema(), {})


def test_kpi_executor_runs_bounded_aggregate() -> None:
    class Cursor:
        description = [type("Column", (), {"name": "value"})()]

        def __init__(self) -> None:
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None) -> None:
            self.calls.append((query, params))

        def fetchall(self):
            return [(42,)]

    class Connection:
        def __init__(self) -> None:
            self.cursor_value = Cursor()

        def set_session(self, **_kwargs) -> None:
            return None

        def cursor(self):
            return self.cursor_value

        def close(self) -> None:
            return None

    connection = Connection()
    definition = KPIDefinition(
        id="kpi-1", monitored_database_id="db-1", schema_revision_id="schema-1",
        table_name="orders", measure_column="total", aggregation="sum", title="Revenue",
        rationale="Order totals", confidence=1,
    )

    snapshot = KPIAggregateExecutor(lambda: connection).execute(definition)

    assert snapshot.points == [{"value": 42}]
    assert "SUM(\"total\")" in snapshot.sql
    assert connection.cursor_value.calls[-1][1] == (500,)


def test_auto_kpis_discovers_and_calculates_without_review() -> None:
    candidate = KPICandidate(
        table_name="orders", measure_column="total", aggregation="sum", title="Revenue",
        rationale="Order totals", confidence=1,
    )
    definition = KPIDefinition(
        id="kpi-1", monitored_database_id="db-1", schema_revision_id="schema-1", **candidate.model_dump()
    )

    class Repository:
        def set_generation_status(self, *args, **kwargs):
            pass

        def current_schema_metadata(self, connection_id):
            assert connection_id == "db-1"
            return "schema-1", {}

        def save_candidates(self, connection_id, schema_revision_id, candidates):
            assert (connection_id, schema_revision_id, candidates) == ("db-1", "schema-1", [candidate])
            return [("candidate-1", candidate)]

        def approve(self, candidate_id, connection_id):
            assert (candidate_id, connection_id) == ("candidate-1", "db-1")
            return definition

        def save_snapshot(self, snapshot):
            assert snapshot.kpi_definition_id == "kpi-1"

        def list_definitions(self, connection_id):
            assert connection_id == "db-1"
            return [definition]

    class Discovery:
        def discover(self, schema, summaries):
            assert schema == _schema()
            assert summaries == {}
            return [candidate]

    class Executor:
        def __init__(self, _provider):
            pass

        def execute(self, received):
            assert received == definition
            return KPISnapshot(
                kpi_definition_id="kpi-1", monitored_database_id="db-1", sql="SELECT 1", points=[], execution_ms=1
            )

    with patch("src.agent.kpi.auto.KPIRepository", return_value=Repository()), \
         patch("src.agent.kpi.auto.SchemaInspector.from_connection_provider", return_value=type("Inspector", (), {"inspect": lambda _self: _schema()})()), \
         patch("src.agent.kpi.auto.KPIDiscoveryAgent", return_value=Discovery()), \
         patch("src.agent.kpi.auto.KPIAggregateExecutor", Executor):
        assert generate_kpis("db-1", lambda: object()) == 1


def test_auto_kpis_marks_discovery_service_unavailable() -> None:
    statuses = []

    class Repository:
        def set_generation_status(self, *args, **kwargs):
            statuses.append((args, kwargs))

        def current_schema_metadata(self, _connection_id):
            return "schema-1", {}

    class Discovery:
        def discover(self, _schema, _summaries):
            raise KPIDiscoveryUnavailable("offline")

    with patch("src.agent.kpi.auto.KPIRepository", return_value=Repository()), \
         patch("src.agent.kpi.auto.SchemaInspector.from_connection_provider", return_value=type("Inspector", (), {"inspect": lambda _self: _schema()})()), \
         patch("src.agent.kpi.auto.KPIDiscoveryAgent", return_value=Discovery()):
        with pytest.raises(KPIDiscoveryUnavailable):
            generate_kpis("db-1", lambda: object())

    assert statuses[-1][0][1] == "unavailable"
