"""
Inspector for PostgreSQL database statistics.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.statistics_queries import (
    GET_DATABASE_STATS_QUERY,
)

from src.models.statistics.database_stats_model import (
    DatabaseStats,
)

ConnectionProvider = Callable[[], Any]


class DatabaseStatsInspector:
    """
    Collect overall database statistics.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:

        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_database_stats(
        self,
    ) -> list[DatabaseStats]:

        connection = None

        try:

            connection = (
                self._connection_provider()
            )

            with connection.cursor(
                cursor_factory=RealDictCursor,
            ) as cursor:

                cursor.execute(
                    GET_DATABASE_STATS_QUERY
                )

                rows = cursor.fetchall()

            return [
                DatabaseStats.model_validate(
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
                "Failed to collect database statistics"
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