import json

from src.agent.kpi.discovery import KPIDiscoveryAgent
from src.agent.kpi.executor import KPIAggregateExecutor
from src.agent.kpi.models import KPIDefinition
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
