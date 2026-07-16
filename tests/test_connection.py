"""Tests for environment-based PostgreSQL connection setup."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.connection import get_connection


class ConnectionTests(unittest.TestCase):
    """Verify provider dashboard host URLs are compatible with psycopg2."""

    @patch("src.db_engine.connection.psycopg2.connect")
    @patch.dict(
        "os.environ",
        {
            "DB_HOST": "https://db.example.com",
            "DB_PORT": "5432",
            "DB_NAME": "hostel",
            "DB_USER": "reader",
            "DB_PASSWORD": "secret",
        },
        clear=True,
    )
    def test_get_connection_normalizes_url_host_and_uses_configured_database(self, connect: object) -> None:
        get_connection()

        connect.assert_called_once_with(
            host="db.example.com",
            port="5432",
            database="hostel",
            user="reader",
            password="secret",
            sslmode="require",
            connect_timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
