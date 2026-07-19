from unittest.mock import patch

from src.api.connection_repository import _connection_metadata_from_row


def test_connection_metadata_exposes_only_safe_fleet_fields() -> None:
    row = (
        "connection-1", "Production", "active", "2026-07-20T10:00:00Z", 128.5, 4,
        "2026-07-19T10:00:00Z", 99.2, b"wrapped", b"ciphertext", b"nonce", b"tag",
    )
    with patch(
        "src.api.connection_repository._decode_credentials",
        return_value={"host": "db.example.test", "port": 5432, "database": "inventory", "user": "readonly", "password": "secret"},
    ):
        metadata = _connection_metadata_from_row(row)

    assert metadata == {
        "connection_id": "connection-1",
        "display_name": "Production",
        "status": "active",
        "last_analyzed_at": "2026-07-20T10:00:00Z",
        "database_size_mb": 128.5,
        "num_connections": 4,
        "archived_at": "2026-07-19T10:00:00Z",
        "cache_hit_ratio": 99.2,
        "host": "db.example.test",
        "port": 5432,
        "database": "inventory",
    }


def test_connection_metadata_keeps_legacy_connection_visible_without_credentials() -> None:
    row = ("connection-1", "Legacy", "connection_error", None, None, None, None, None, None, None, None, None)

    assert _connection_metadata_from_row(row)["host"] is None
