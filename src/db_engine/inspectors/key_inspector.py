"""Inspector for PostgreSQL key metadata."""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.schema_queries import (
    GET_FOREIGN_KEYS_QUERY,
    GET_PRIMARY_KEYS_QUERY,
)
from src.models.schema.key_model import ForeignKeyInfo, PrimaryKeyInfo

ConnectionProvider = Callable[[], Any]


class KeyInspector:
    """Collect primary- and foreign-key metadata."""

    def __init__(self, connection_provider: ConnectionProvider) -> None:
        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_primary_keys(self) -> list[PrimaryKeyInfo]:
        """Return primary-key columns, or an empty list when none exist."""
        rows = self._fetch_rows(GET_PRIMARY_KEYS_QUERY, "primary keys")
        return self._validate_rows(rows, PrimaryKeyInfo, "primary-key")

    def get_foreign_keys(self) -> list[ForeignKeyInfo]:
        """Return foreign-key references, or an empty list when none exist."""
        rows = self._fetch_rows(GET_FOREIGN_KEYS_QUERY, "foreign keys")
        return self._validate_rows(rows, ForeignKeyInfo, "foreign-key")

    def _fetch_rows(self, query: str, metadata_name: str) -> list[Mapping[str, Any]]:
        connection = None
        try:
            connection = self._connection_provider()
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
        except psycopg2.Error:
            self._logger.exception("Failed to inspect database %s", metadata_name)
            return []
        finally:
            if connection is not None:
                connection.close()

    def _validate_rows(self, rows: list[Mapping[str, Any]], model: type[Any], metadata_name: str) -> list[Any]:
        try:
            return [model.model_validate(dict(row)) for row in rows]
        except (ValueError, TypeError):
            self._logger.exception("Invalid %s metadata returned by the database", metadata_name)
            return []
