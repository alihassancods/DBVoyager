"""
Main statistics orchestrator.
"""

from collections.abc import Callable
from typing import Any

from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)

from src.db_engine.inspectors.statistics.table_stats_inspector import (
    TableStatsInspector,
)

from src.db_engine.inspectors.statistics.index_stats_inspector import (
    IndexStatsInspector,
)

from src.db_engine.inspectors.statistics.lock_stats_inspector import (
    LockStatsInspector,
)

from src.db_engine.inspectors.statistics.database_stats_inspector import (
    DatabaseStatsInspector,
)

from src.models.statistics.statistics_snapshot_model import (
    StatisticsSnapshot,
)

ConnectionProvider = Callable[[], Any]


class StatisticsInspector:
    """
    Collect a complete statistics snapshot.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:

        self._query_inspector = QueryStatsInspector(
            connection_provider
        )

        self._table_inspector = TableStatsInspector(
            connection_provider
        )

        self._index_inspector = IndexStatsInspector(
            connection_provider
        )

        self._lock_inspector = LockStatsInspector(
            connection_provider
        )

        self._database_inspector = DatabaseStatsInspector(
            connection_provider
        )

    def get_snapshot(self, progress: Callable[[str, str], None] | None = None) -> StatisticsSnapshot:

        def collect(name: str, callback: Callable[[], list[Any]]) -> list[Any]:
            if progress:
                progress("statistics", f"Collecting {name}.")
            result = callback()
            if progress:
                progress("statistics", f"Collected {len(result)} {name}.")
            return result

        query_stats = collect("query statistics", self._query_inspector.get_query_stats)
        table_stats = collect("table statistics", self._table_inspector.get_table_stats)
        index_stats = collect("index statistics", self._index_inspector.get_index_stats)
        lock_stats = collect("lock statistics", self._lock_inspector.get_lock_stats)
        database_stats_list = collect("database statistics", self._database_inspector.get_database_stats)

        database_stats = (
            database_stats_list[0]
            if database_stats_list
            else None
        )

        if database_stats is None:
            raise ValueError(
                "Database statistics not available."
            )

        return StatisticsSnapshot(
            query_stats=query_stats,
            table_stats=table_stats,
            index_stats=index_stats,
            lock_stats=lock_stats,
            database_stats=database_stats,
        )
