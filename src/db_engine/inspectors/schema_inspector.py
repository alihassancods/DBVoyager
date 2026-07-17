"""Service for assembling complete PostgreSQL schema metadata."""

import logging
from collections.abc import Callable
from typing import Any

from src.db_engine.inspectors.column_inspector import ColumnInspector
from src.db_engine.inspectors.index_inspector import IndexInspector
from src.db_engine.inspectors.key_inspector import KeyInspector
from src.db_engine.inspectors.relation_inspector import RelationInspector
from src.db_engine.inspectors.table_inspector import TableInspector
from src.models.schema.schema_model import DatabaseSchema


class SchemaInspector:
    """Coordinate metadata inspectors to produce a complete database schema."""

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
        """Build an inspector that obtains a fresh connection per metadata query."""
        return cls(
            table_inspector=TableInspector(connection_provider),
            column_inspector=ColumnInspector(connection_provider),
            key_inspector=KeyInspector(connection_provider),
            relation_inspector=RelationInspector(),
            index_inspector=IndexInspector(connection_provider),
        )

    def inspect(self, progress: Callable[[str, str], None] | None = None) -> DatabaseSchema:
        """Collect and assemble all supported database schema metadata."""
        try:
            def collect(name: str, callback: Callable[[], Any]) -> Any:
                if progress:
                    progress("schema", f"Collecting {name}.")
                result = callback()
                if progress:
                    progress("schema", f"Collected {len(result)} {name}.")
                return result

            tables = collect("table metadata", self._table_inspector.get_tables)
            columns = collect("column metadata", self._column_inspector.get_columns)
            primary_keys = collect("primary keys", self._key_inspector.get_primary_keys)
            foreign_keys = collect("foreign keys", self._key_inspector.get_foreign_keys)
            relations = self._relation_inspector.build_relations(foreign_keys)
            if progress:
                progress("schema", "Building table relationships.")
            indexes = collect("indexes", self._index_inspector.get_indexes)
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
