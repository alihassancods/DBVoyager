"""Main schema orchestrator with production thread management and fallback safety."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from src.db_engine.inspectors.column_inspector import ColumnInspector
from src.db_engine.inspectors.index_inspector import IndexInspector
from src.db_engine.inspectors.key_inspector import KeyInspector
from src.db_engine.inspectors.relation_inspector import RelationInspector
from src.db_engine.inspectors.table_inspector import TableInspector
from src.models.schema.schema_model import DatabaseSchema

ConnectionProvider = Callable[[], Any]


class SchemaInspector:
    """Collect full database schema metadata concurrently with strict timeout safety."""

    def __init__(
        self,
        connection_provider: ConnectionProvider,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._table_inspector = TableInspector(connection_provider)
        self._column_inspector = ColumnInspector(connection_provider)
        self._key_inspector = KeyInspector(connection_provider)
        self._index_inspector = IndexInspector(connection_provider)
        self._relation_inspector = RelationInspector()
        self._timeout = timeout_seconds
        self._logger = logging.getLogger(__name__)

    @classmethod
    def from_connection_provider(
        cls, connection_provider: ConnectionProvider, timeout_seconds: float = 10.0
    ) -> "SchemaInspector":
        return cls(connection_provider=connection_provider, timeout_seconds=timeout_seconds)

    def inspect(
        self, progress: Callable[[str, str], None] | None = None
    ) -> DatabaseSchema:
        """Inspect schema concurrently across parallel threads with safety bounds."""
        if progress:
            progress("schema", "Collecting schema metadata in parallel.")

        with ThreadPoolExecutor(max_workers=5) as executor:
            f_tables = executor.submit(
                self._safe_collect, "tables", self._table_inspector.get_tables
            )
            f_columns = executor.submit(
                self._safe_collect, "columns", self._column_inspector.get_columns
            )
            f_pks = executor.submit(
                self._safe_collect, "primary_keys", self._key_inspector.get_primary_keys
            )
            f_fks = executor.submit(
                self._safe_collect, "foreign_keys", self._key_inspector.get_foreign_keys
            )
            f_indexes = executor.submit(
                self._safe_collect, "indexes", self._index_inspector.get_indexes
            )

            try:
                tables = f_tables.result(timeout=self._timeout)
                columns = f_columns.result(timeout=self._timeout)
                primary_keys = f_pks.result(timeout=self._timeout)
                foreign_keys = f_fks.result(timeout=self._timeout)
                indexes = f_indexes.result(timeout=self._timeout)
            except TimeoutError:
                self._logger.error("Schema inspection timed out after %s seconds", self._timeout)
                raise RuntimeError(f"Schema inspection timed out after {self._timeout}s")

        # In-memory relation construction from extracted foreign keys
        try:
            relations = self._relation_inspector.build_relations(foreign_keys)
        except Exception:
            self._logger.exception("Failed to construct relations in-memory")
            relations = []

        if progress:
            progress("schema", "Completed schema metadata inspection.")

        return DatabaseSchema(
            tables=tables,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes,
            relations=relations,
        )

    def _safe_collect(self, name: str, fn: Callable[[], list[Any]]) -> list[Any]:
        """Wrap sub-inspectors to log errors and prevent full system failure."""
        try:
            return fn()
        except Exception:
            self._logger.exception("Failed to collect schema %s", name)
            return []