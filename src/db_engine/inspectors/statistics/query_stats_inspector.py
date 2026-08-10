"""So this one is to fetch the details of the query stats from the database and return it in a structured format."""

"""
Inspector for PostgreSQL query statistics.
"""
"""
Inspector for PostgreSQL query statistics with pre-flight extension checking.
"""

"""
Update this one so that if the pg_statement extension is not installed, it will return an empty list instead of throwing an error.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db_engine.queries.statistics_queries import (
    GET_QUERY_STATS_QUERY,
)
from src.models.statistics.query_stats_model import (
    QueryStats,
)

ConnectionProvider = Callable[[], Any]

# Query to verify if pg_stat_statements is installed and accessible
CHECK_EXTENSION_QUERY = "SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements';"


class QueryStatsInspector:
    """
    Collect query statistics from pg_stat_statements safely.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:
        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_query_stats(self) -> list[QueryStats]:
        """
        Return statistics for executed queries if pg_stat_statements is available.
        """
        connection = None

        try:
            connection = self._connection_provider()

            # 1. Pre-flight check: Verify extension existence
            with connection.cursor() as cursor:
                cursor.execute(CHECK_EXTENSION_QUERY)
                if not cursor.fetchone():
                    self._logger.info(
                        "pg_stat_statements extension is not installed. Skipping query statistics."
                    )
                    return []

            # 2. Fetch query statistics
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(GET_QUERY_STATS_QUERY)
                rows = cursor.fetchall()

            return [
                QueryStats.model_validate(self._as_mapping(row))
                for row in rows
            ]

        except (
            psycopg2.Error,
            ValueError,
            TypeError,
        ):
            self._logger.exception("Failed to collect query statistics")
            return []

        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _as_mapping(
        row: Mapping[str, Any] | Any,
    ) -> dict[str, Any]:
        return dict(row)