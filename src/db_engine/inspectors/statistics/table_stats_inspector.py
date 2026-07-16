"""
Inspector for PostgreSQL table statistics.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any
import psycopg2
from psycopg2.extras import RealDictCursor
from src.db_engine.queries.statistics_queries import (
    GET_TABLE_STATS_QUERY,
)
from src.models.statistics.table_stats_model import (
    TableStats,
)

ConnectionProvider = Callable[[], Any]

class TableStatsInspector:
    """
    Collect statistics for user tables.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:

        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_table_stats(self) -> list[TableStats]:
        """
        Return statistics for all user tables.
        """

        connection = None

        try:

            connection = self._connection_provider()

            with connection.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    GET_TABLE_STATS_QUERY
                )

                rows = cursor.fetchall()

            return [
                TableStats.model_validate(
                    self._as_mapping(row)
                )
                for row in rows
            ]

        except (
            psycopg2.Error,
            ValueError,
            TypeError,
        ):

            self._logger.exception(
                "Failed to collect table statistics"
            )

            return []

        finally:

            if connection is not None:
                connection.close()

    @staticmethod
    def _as_mapping(
        row: Mapping[str, Any] | Any,
    ) -> dict[str, Any]:

        return dict(row)