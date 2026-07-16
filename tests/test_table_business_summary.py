"""Unit tests for the table business summary agent."""

from types import SimpleNamespace

from src.agent import table_business_summary
from src.agent import TableBusinessSummaryAgent, TableSummaryInput


class FakeModel:
    def __init__(self) -> None:
        self.prompt = ""

    def invoke(self, prompt: str) -> SimpleNamespace:
        self.prompt = prompt
        return SimpleNamespace(content="Orders store customer purchases. They support fulfilment, with id, customer_id, and total as key columns.")


def test_table_business_summary_uses_table_metadata() -> None:
    model = FakeModel()
    agent = TableBusinessSummaryAgent(model)

    summary = agent.summarize(TableSummaryInput(
        table_name="orders",
        table_columns=["id", "customer_id", "total"],
        relationships=["orders.customer_id -> customers.id"],
    ))

    assert summary.startswith("Orders store customer purchases.")
    assert '"table_name": "orders"' in model.prompt
    assert "orders.customer_id -> customers.id" in model.prompt


def test_agent_builds_summary_input_from_schema_inspector(monkeypatch: object) -> None:
    schema = SimpleNamespace(
        tables=[SimpleNamespace(table_name="orders")],
        columns=[
            SimpleNamespace(table_name="orders", column_name="id", data_type="bigint"),
            SimpleNamespace(table_name="orders", column_name="customer_id", data_type="bigint"),
        ],
        foreign_keys=[
            SimpleNamespace(source_table="orders", source_column="customer_id", target_table="customers", target_column="id"),
        ],
    )
    monkeypatch.setattr(
        table_business_summary.SchemaInspector,
        "from_connection_provider",
        lambda _provider: SimpleNamespace(inspect=lambda: schema),
    )
    model = FakeModel()

    summary = TableBusinessSummaryAgent(model).summarize_database_table("orders", lambda: None)

    assert summary.startswith("Orders store customer purchases.")
    assert "id (bigint)" in model.prompt
    assert "orders.customer_id -> customers.id" in model.prompt
