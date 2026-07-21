from decimal import Decimal

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


def test_persisted_json_serializes_postgres_decimal() -> None:
    assert analysis_repository._json({"size": Decimal("1.25")}).dumps({"size": Decimal("1.25")}) == '{"size": "1.25"}'


def test_schema_persistence_batches_table_upserts(monkeypatch) -> None:
    batches = []

    class Cursor:
        def execute(self, _query, _params=None) -> None:
            return None

        def fetchone(self):
            return ("revision-1",)

    monkeypatch.setattr(analysis_repository, "execute_values", lambda _cursor, _query, rows, **_kwargs: batches.append(rows))
    progress = []
    revision = analysis_repository._persist_schema(
        Cursor(), "run-1", "database-1",
        {"tables": [
            {"schema_name": "public", "table_name": "orders", "table_type": "BASE TABLE", "estimated_rows": 1},
            {"schema_name": "public", "table_name": "items", "table_type": "BASE TABLE", "estimated_rows": 2},
        ]},
        {"schema_visualization": {"status": "ok", "data": "erDiagram"}},
        lambda *event: progress.append(event),
    )

    assert revision == "revision-1"
    assert len(batches) == 1 and len(batches[0]) == 2
    assert progress == [("persistence", "Saved 2 schema tables.")]


def test_health_findings_are_saved_in_one_batch(monkeypatch) -> None:
    batches = []
    monkeypatch.setattr(analysis_repository, "execute_values", lambda _cursor, _query, rows: batches.append(rows))

    analysis_repository._persist_health_checks(object(), "run-1", [
        {"check": "locks", "severity": "critical", "message": "Blocked", "action": "Inspect."},
        {"check": "cache", "severity": "warning", "message": "Low ratio"},
    ])

    assert batches == [[
        ("run-1", "locks", "critical", "Blocked", "Inspect."),
        ("run-1", "cache", "warning", "Low ratio", None),
    ]]


def test_health_collection_fails_when_health_checks_fail(monkeypatch) -> None:
    class Cursor:
        def __init__(self) -> None:
            self.calls = []

        def execute(self, query, params=None) -> None:
            self.calls.append((query, params))

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def cursor(self):
            class CursorContext:
                def __enter__(_self):
                    return self.cursor_instance

                def __exit__(_self, *_args) -> None:
                    return None

            return CursorContext()

    connection = Connection()
    monkeypatch.setattr(analysis_repository, "_app_connection", lambda: connection)
    monkeypatch.setattr(analysis_repository, "_persist_schema", lambda *_args: "schema-1")
    monkeypatch.setattr(analysis_repository, "_persist_statistics", lambda *_args: None)
    monkeypatch.setattr(analysis_repository, "invalidate", lambda *_args: None)

    analysis_repository._persist_report("run-1", "connection-1", {
        "statistics": {"status": "ok", "data": {}},
        "schema": {"status": "ok", "data": {}},
        "health_checks": {"status": "error", "error": "broken"},
    }, collection_kind="health_checks")

    assert connection.cursor_instance.calls[-1][1][0] == "failed"
    assert connection.cursor_instance.calls[-1][1][-3] == "collection_incomplete"


def test_table_stat_batch_matches_its_insert_template(monkeypatch) -> None:
    batches = []

    class Cursor:
        def execute(self, _query, _params=None) -> None:
            return None

        def fetchall(self):
            return [("table-id", "orders")]

    monkeypatch.setattr(analysis_repository, "execute_values", lambda _cursor, _query, rows, **kwargs: batches.append((rows, kwargs)))
    analysis_repository._persist_statistics(Cursor(), "run-1", "database-1", "2026-01-01T00:00:00Z", {
        "database_stats": {"num_connections": 1, "database_size_mb": 1, "cache_hit_ratio": 99},
        "table_stats": [{"table_name": "orders", "seq_scan": 1, "idx_scan": 2, "n_live_tup": 3, "n_dead_tup": 4}],
        "query_stats": [], "index_stats": [], "lock_stats": [],
    }, {"tables": [{"schema_name": "public", "table_name": "orders", "table_type": "BASE TABLE", "estimated_rows": 3}]})

    assert batches[0][1]["template"].count("%s") == len(batches[0][0][0])
