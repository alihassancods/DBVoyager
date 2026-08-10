"""Service for assembling complete PostgreSQL schema metadata using concurrent execution."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.db_engine.inspectors.column_inspector import ColumnInspector
from src.db_engine.inspectors.index_inspector import IndexInspector
from src.db_engine.inspectors.key_inspector import KeyInspector
from src.db_engine.inspectors.relation_inspector import RelationInspector
from src.db_engine.inspectors.table_inspector import TableInspector
from src.models.schema.schema_model import DatabaseSchema


class SchemaInspector:
    """Coordinate metadata inspectors concurrently to produce a complete database schema."""

    def __init__(
        self,
        table_inspector: TableInspector,
        column_inspector: ColumnInspector,
        key_inspector: KeyInspector,
        relation_inspector: RelationInspector,
        index_inspector: IndexInspector,
    ) -> None:
        self._table_inspector = table_inspector
        self._column_inspector = column_inspector
        self._key_inspector = key_inspector
        self._relation_inspector = relation_inspector
        self._index_inspector = index_inspector
        self._logger = logging.getLogger(__name__)

    @classmethod
    def from_connection_provider(
        cls, connection_provider: Callable[[], Any]
    ) -> "SchemaInspector":
        """Build an inspector that obtains fresh connections per query for parallel execution."""
        return cls(
            table_inspector=TableInspector(connection_provider),
            column_inspector=ColumnInspector(connection_provider),
            key_inspector=KeyInspector(connection_provider),
            relation_inspector=RelationInspector(),
            index_inspector=IndexInspector(connection_provider),
        )

    def inspect(self, progress: Callable[[str, str], None] | None = None) -> DatabaseSchema:
        """Collect and assemble database schema metadata concurrently using a thread pool."""
        try:
            if progress:
                progress("schema", "Starting concurrent schema inspection.")

            # Run 5 database metadata queries in parallel
            with ThreadPoolExecutor(max_workers=5) as executor:
                f_tables = executor.submit(self._table_inspector.get_tables)
                f_columns = executor.submit(self._column_inspector.get_columns)
                f_pks = executor.submit(self._key_inspector.get_primary_keys)
                f_fks = executor.submit(self._key_inspector.get_foreign_keys)
                f_indexes = executor.submit(self._index_inspector.get_indexes)

                tables = f_tables.result()
                columns = f_columns.result()
                primary_keys = f_pks.result()
                foreign_keys = f_fks.result()
                indexes = f_indexes.result()

            # Assemble relations in-memory from foreign keys
            relations = self._relation_inspector.build_relations(foreign_keys)

            if progress:
                progress("schema", "Schema inspection complete.")

            return DatabaseSchema(
                tables=tables,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                relations=relations,
                indexes=indexes,
            )
        except Exception as exc:
            self._logger.exception("Failed to assemble database schema metadata")
            raise RuntimeError("Schema inspection failed") from exc