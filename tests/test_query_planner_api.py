from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.auth import current_user
from src.api.main import app


client = TestClient(app)


def test_query_planner_marks_read_only_sql_executable() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.query_generator.ensure_owned_database") as ownership, patch(
            "src.api.query_generator._schema_context", return_value={"tables": {"orders": ["id"]}}
        ), patch("src.api.query_generator.CustomQueryGenerator.generate_query", return_value={
            "success": True, "explanation": "Reads orders.", "query_type": "READ-ONLY", "sql": "SELECT id FROM orders"
        }):
            response = client.post("/connections/connection-1/query-planner/generate", json={"prompt": "show orders"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["executable"] is True
    ownership.assert_called_once_with("connection-1", "owner")


def test_query_planner_returns_write_sql_as_copy_only_draft() -> None:
    app.dependency_overrides[current_user] = lambda: {"sub": "owner"}
    try:
        with patch("src.api.query_generator.ensure_owned_database"), patch(
            "src.api.query_generator._schema_context", return_value={"tables": {"orders": ["id"]}}
        ), patch("src.api.query_generator.CustomQueryGenerator.generate_query", return_value={
            "success": True, "explanation": "Deletes orders.", "query_type": "MUTATING", "sql": "DELETE FROM orders"
        }):
            response = client.post("/connections/connection-1/query-planner/generate", json={"prompt": "delete orders"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["executable"] is False
    assert "Forbidden keyword" in response.json()["execution_block_reason"]
