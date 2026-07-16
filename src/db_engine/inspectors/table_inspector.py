"""Inspector for PostgreSQL table metadata."""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.schema_queries import GET_TABLES_QUERY
from src.models.schema.table_model import TableInfo

ConnectionProvider = Callable[[], Any]


class TableInspector:
    """Collect table metadata using an injected connection provider."""

    def __init__(self, connection_provider: ConnectionProvider) -> None:
        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_tables(self) -> list[TableInfo]:
        """Return metadata for all user-visible tables in the database."""
        connection = None
        try:
            connection = self._connection_provider()
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(GET_TABLES_QUERY)
                rows = cursor.fetchall()
            return [TableInfo.model_validate(self._as_mapping(row)) for row in rows]
        except (psycopg2.Error, ValueError, TypeError):
            self._logger.exception("Failed to inspect database tables")
            return []
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _as_mapping(row: Mapping[str, Any] | Any) -> dict[str, Any]:
        return dict(row)
