from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import _connections, app


client = TestClient(app)


def test_connection_id_is_used_for_query() -> None:
    _connections.clear()
    connection = MagicMock()
    connection.closed = 0
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.description = ("value",)
    cursor.fetchall.return_value = [{"value": 1}]

    with patch("src.api.main.psycopg2.connect", return_value=connection):
        response = client.post(
            "/connections",
            json={"host": "localhost", "database": "demo", "user": "user", "password": "secret"},
        )

    assert response.status_code == 201
    result = client.post(
        "/queries",
        json={"connection_id": response.json()["connection_id"], "query": "SELECT 1 AS value"},
    )
    assert result.json() == {"rows": [{"value": 1}], "row_count": 1}
    cursor.execute.assert_called_once_with("SELECT 1 AS value")
    connection.commit.assert_called_once()
