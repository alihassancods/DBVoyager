from src.api import analysis_repository


def test_table_summaries_are_saved_and_streamed(monkeypatch) -> None:
    class Agent:
        def summarize(self, table):
            return f"{table.table_name} stores application data. It supports reporting."

    class Cursor:
        def __init__(self) -> None:
            self.calls = []

        def execute(self, query, params) -> None:
            self.calls.append((query, params))

        def fetchone(self):
            return ("table-1", "pending")

    monkeypatch.setattr(analysis_repository, "TableBusinessSummaryAgent", Agent)
    cursor = Cursor()
    updates = []
    schema = {
        "tables": [{"schema_name": "public", "table_name": "orders"}],
        "columns": [{"table_name": "orders", "column_name": "id", "data_type": "uuid"}],
        "foreign_keys": [],
    }

    analysis_repository._persist_table_summaries(
        cursor, "connection-1", "run-1", "revision-1", schema, lambda *event: updates.append(event)
    )

    assert cursor.calls[-1][1][-1].startswith("orders stores application data.")
    assert updates[-1] == ("summaries", "Saved table summary 1/1: public.orders.")
