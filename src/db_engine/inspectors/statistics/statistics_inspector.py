"""Main statistics orchestrator with parallel execution."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.db_engine.inspectors.statistics.database_stats_inspector import (
    DatabaseStatsInspector,
)
from src.db_engine.inspectors.statistics.index_stats_inspector import (
    IndexStatsInspector,
)
from src.db_engine.inspectors.statistics.lock_stats_inspector import (
    LockStatsInspector,
)
from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)
from src.db_engine.inspectors.statistics.table_stats_inspector import (
    TableStatsInspector,
)
from src.models.statistics.statistics_snapshot_model import (
    StatisticsSnapshot,
)

ConnectionProvider = Callable[[], Any]


class StatisticsInspector:
    """Collect a complete statistics snapshot concurrently."""

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:
        self._query_inspector = QueryStatsInspector(connection_provider)
        self._table_inspector = TableStatsInspector(connection_provider)
        self._index_inspector = IndexStatsInspector(connection_provider)
        self._lock_inspector = LockStatsInspector(connection_provider)
        self._database_inspector = DatabaseStatsInspector(connection_provider)
        self._logger = logging.getLogger(__name__)

    def get_snapshot(
        self, progress: Callable[[str, str], None] | None = None
    ) -> StatisticsSnapshot:
        """Collect database statistics concurrently across a thread pool."""
        try:
            if progress:
                progress("statistics", "Collecting database statistics in parallel.")

            with ThreadPoolExecutor(max_workers=5) as executor:
                f_query = executor.submit(self._query_inspector.get_query_stats)
                f_table = executor.submit(self._table_inspector.get_table_stats)
                f_index = executor.submit(self._index_inspector.get_index_stats)
                f_lock = executor.submit(self._lock_inspector.get_lock_stats)
                f_db = executor.submit(self._database_inspector.get_database_stats)

                query_stats = f_query.result()
                table_stats = f_table.result()
                index_stats = f_index.result()
                lock_stats = f_lock.result()
                database_stats_list = f_db.result()

            database_stats = (
                database_stats_list[0] if database_stats_list else None
            )

            if database_stats is None:
                raise ValueError("Database statistics not available.")

            if progress:
                progress("statistics", "Completed database statistics collection.")

            return StatisticsSnapshot(
                query_stats=query_stats,
                table_stats=table_stats,
                index_stats=index_stats,
                lock_stats=lock_stats,
                database_stats=database_stats,
            )
        except Exception as exc:
            self._logger.exception("Failed to collect statistics snapshot")
            raise RuntimeError("Statistics snapshot collection failed") from exc