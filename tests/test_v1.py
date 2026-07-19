import v1


def test_build_report_collects_statistics_and_schema_on_separate_connections(monkeypatch) -> None:
    connections = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query):
            return None

    class Connection:
        def __init__(self) -> None:
            self.closed = False

        def set_session(self, **_kwargs) -> None:
            return None

        def cursor(self):
            return Cursor()

        def close(self) -> None:
            self.closed = True

    class Snapshot:
        def model_dump(self, **_kwargs):
            return {"database_stats": {"num_connections": 1}}

    class Schema:
        def model_dump(self, **_kwargs):
            return {"tables": []}

    class StatisticsInspector:
        def __init__(self, _provider) -> None:
            return None

        def get_snapshot(self, _progress=None):
            return Snapshot()

    class SchemaInspector:
        @classmethod
        def from_connection_provider(cls, _provider):
            return cls()

        def inspect(self, _progress=None):
            return Schema()

    class Visualizer:
        def render_mermaid(self, _schema):
            return "erDiagram"

    def provider():
        connection = Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(v1, "StatisticsInspector", StatisticsInspector)
    monkeypatch.setattr(v1, "SchemaInspector", SchemaInspector)
    monkeypatch.setattr(v1, "SchemaVisualizer", Visualizer)

    report = v1.build_report("demo", provider, sections={"statistics", "schema"})

    assert report["statistics"]["status"] == "ok"
    assert report["schema"]["status"] == "ok"
    assert len(connections) == 2
    assert all(connection.closed for connection in connections)
