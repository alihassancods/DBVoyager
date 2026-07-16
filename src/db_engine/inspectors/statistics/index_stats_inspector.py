"""
Inspector for PostgreSQL index statistics.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.statistics_queries import (
    GET_INDEX_STATS_QUERY,
)

from src.models.statistics.index_stats_model import (
    IndexStats,
)

ConnectionProvider = Callable[[], Any]


class IndexStatsInspector:
    """
    Collect index usage statistics.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:

        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_index_stats(self) -> list[IndexStats]:
        """
        Return statistics for all indexes.
        """

        connection = None

        try:

            connection = self._connection_provider()

            with connection.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    GET_INDEX_STATS_QUERY
                )

                rows = cursor.fetchall()

            return [
                IndexStats.model_validate(
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
                "Failed to collect index statistics"
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