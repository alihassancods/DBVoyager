"""So this one is to fetch the details of the query stats from the database and return it in a structured format."""

"""
Inspector for PostgreSQL query statistics.
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

ConnectionProvider = Callable[[], Any] # just give it the connection no matter which database it is, it will return the connection object for that database.

class QueryStatsInspector:
    """
    Collect query statistics from pg_stat_statements.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:

        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__) # to print the logs in the console, we need to create a logger object and pass the name of the module to it.

    def get_query_stats(self) -> list[QueryStats]:
        """
        Return statistics for executed queries.
        """

        connection = None

        try:

            connection = self._connection_provider()

            with connection.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    GET_QUERY_STATS_QUERY
                )

                rows = cursor.fetchall()

            return [
                QueryStats.model_validate(
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
                "Failed to collect query statistics"
            )

            return []

        finally:

            if connection is not None:
                connection.close()

    @staticmethod
    def _as_mapping(
        row: Mapping[str, Any] | Any, # to make the row in the dictionary format which the pydantic object can understand and validate
    ) -> dict[str, Any]:

        return dict(row)