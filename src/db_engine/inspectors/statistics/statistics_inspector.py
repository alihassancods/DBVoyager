"""Main statistics orchestrator with production thread management and fallback safety."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
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
    """Collect a complete statistics snapshot concurrently with thread timeouts and error isolation."""

    def __init__(
        self,
        connection_provider: ConnectionProvider,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._query_inspector = QueryStatsInspector(connection_provider)
        self._table_inspector = TableStatsInspector(connection_provider)
        self._index_inspector = IndexStatsInspector(connection_provider)
        self._lock_inspector = LockStatsInspector(connection_provider)
        self._database_inspector = DatabaseStatsInspector(connection_provider)
        self._timeout = timeout_seconds
        self._logger = logging.getLogger(__name__)

    def get_snapshot(
        self, progress: Callable[[str, str], None] | None = None
    ) -> StatisticsSnapshot:
        """Collect database statistics concurrently across a thread pool with strict safety bounds."""
        if progress:
            progress("statistics", "Collecting database statistics in parallel.")

        with ThreadPoolExecutor(max_workers=5) as executor:
            f_query = executor.submit(self._safe_collect, "query_stats", self._query_inspector.get_query_stats)
            f_table = executor.submit(self._safe_collect, "table_stats", self._table_inspector.get_table_stats)
            f_index = executor.submit(self._safe_collect, "index_stats", self._index_inspector.get_index_stats)
            f_lock = executor.submit(self._safe_collect, "lock_stats", self._lock_inspector.get_lock_stats)
            f_db = executor.submit(self._safe_collect, "db_stats", self._database_inspector.get_database_stats)

            try:
                query_stats = f_query.result(timeout=self._timeout)
                table_stats = f_table.result(timeout=self._timeout)
                index_stats = f_index.result(timeout=self._timeout)
                lock_stats = f_lock.result(timeout=self._timeout)
                database_stats_list = f_db.result(timeout=self._timeout)
            except TimeoutError:
                self._logger.error("Statistics collection timed out after %s seconds", self._timeout)
                raise RuntimeError(f"Database statistics inspection timed out after {self._timeout}s")

        database_stats = database_stats_list[0] if database_stats_list else None

        if database_stats is None:
            self._logger.warning("Database statistics object was empty; generating fallback default.")
            # Fallback if DB stats query returned empty due to permissions
            from src.models.statistics.database_stats_model import DatabaseStats
            database_stats = DatabaseStats(
                db_name="unknown",
                total_size="0 MB",
                active_connections=0,
                idle_connections=0,
                total_connections=0,
            )

        if progress:
            progress("statistics", "Completed database statistics collection.")

        return StatisticsSnapshot(
            query_stats=query_stats,
            table_stats=table_stats,
            index_stats=index_stats,
            lock_stats=lock_stats,
            database_stats=database_stats,
        )

    def _safe_collect(self, name: str, fn: Callable[[], list[Any]]) -> list[Any]:
        """Wrap individual sub-inspectors to log errors and prevent full system failure on minor issues."""
        try:
            return fn()
        except Exception:
            self._logger.exception("Failed to collect %s", name)
            return []