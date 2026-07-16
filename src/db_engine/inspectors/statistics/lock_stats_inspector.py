"""
Inspector for PostgreSQL lock statistics.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.statistics_queries import (
    GET_LOCK_STATS_QUERY,
)

from src.models.statistics.lock_stats_model import (
    LockStats,
)

ConnectionProvider = Callable[[], Any]


class LockStatsInspector:
    """
    Collect information about active locks.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:

        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_lock_stats(self) -> list[LockStats]:
        """
        Return active lock information.
        """

        connection = None

        try:

            connection = self._connection_provider()

            with connection.cursor(
                cursor_factory=RealDictCursor,
            ) as cursor:

                cursor.execute(
                    GET_LOCK_STATS_QUERY,
                )

                rows = cursor.fetchall()

            return [
                LockStats.model_validate(
                    self._as_mapping(row),
                )
                for row in rows
            ]

        except (
            psycopg2.Error,
            ValueError,
            TypeError,
        ):

            self._logger.exception(
                "Failed to collect lock statistics"
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