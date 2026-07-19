from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.auth import current_user
from src.api.main import app


client = TestClient(app)
SCHEMA = {"tables": [{"schema_name": "public", "table_name": "orders"}]}


def test_schema_metrics_are_owner_scoped() -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [
        {"total_size_bytes": 100, "table_size_bytes": 70, "index_size_bytes": 30},
        {"n_live_tup": 80, "n_dead_tup": 20, "seq_scan": 2, "idx_scan": 4},
    ]
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.dashboard.ensure_owned_database") as ownership, patch(
            "src.api.dashboard.get_current_schema", return_value=SCHEMA
        ), patch("src.api.dashboard.connection_provider", return_value=lambda: connection):
            response = client.get("/connections/connection-1/schema/tables/public/orders/metrics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["bloat_risk_ratio"] == 0.2
    ownership.assert_called_once_with("connection-1", "owner")


def test_schema_preview_quotes_the_allowlisted_table_and_limits_rows() -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{"id": 1, "name": "Ada"}]
    cursor.description = [SimpleNamespace(name="id"), SimpleNamespace(name="name")]
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.get_current_schema", return_value=SCHEMA
        ), patch("src.api.dashboard.connection_provider", return_value=lambda: connection):
            response = client.get("/connections/connection-1/schema/tables/public/orders/preview?limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"columns": ["id", "name"], "rows": [{"id": 1, "name": "Ada"}], "row_count": 1}
    assert "orders" in str(cursor.execute.call_args.args[0])


def test_schema_preview_rejects_unknown_tables() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.dashboard.ensure_owned_database"), patch(
            "src.api.dashboard.get_current_schema", return_value=SCHEMA
        ):
            response = client.get("/connections/connection-1/schema/tables/public/missing/preview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
