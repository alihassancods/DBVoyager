"""Inspector for PostgreSQL column metadata."""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.schema_queries import GET_COLUMNS_QUERY
from src.models.schema.column_model import ColumnInfo

ConnectionProvider = Callable[[], Any]


class ColumnInspector:
    """Collect column metadata using an injected connection provider."""

    def __init__(self, connection_provider: ConnectionProvider) -> None:
        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_columns(self) -> list[ColumnInfo]:
        """Return metadata for all columns in user-visible tables."""
        connection = None
        try:
            connection = self._connection_provider()
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(GET_COLUMNS_QUERY)
                rows = cursor.fetchall()
            return [ColumnInfo.model_validate(self._as_mapping(row)) for row in rows]
        except (psycopg2.Error, ValueError, TypeError):
            self._logger.exception("Failed to inspect database columns")
            return []
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _as_mapping(row: Mapping[str, Any] | Any) -> dict[str, Any]:
        return dict(row)
