"""Tests for schema metadata inspectors."""

import unittest
from collections.abc import Callable
from pathlib import Path
import sys
from typing import Any
from unittest.mock import Mock

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.inspectors.column_inspector import ColumnInspector
from src.db_engine.inspectors.index_inspector import IndexInspector
from src.db_engine.inspectors.key_inspector import KeyInspector
from src.db_engine.inspectors.relation_inspector import RelationInspector
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.table_inspector import TableInspector
from src.models.schema import (
    ColumnInfo,
    ForeignKeyInfo,
    IndexInfo,
    PrimaryKeyInfo,
    RelationInfo,
    TableInfo,
)


class FakeCursor:
    """Minimal context-managed cursor returning predefined mapping rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.executed_query: str | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: str) -> None:
        self.executed_query = query

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConnection:
    """Minimal connection implementation for inspector tests."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_instance = FakeCursor(rows)
        self.closed = False

    def cursor(self, **_: Any) -> FakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


def provider_for(rows: list[dict[str, Any]]) -> tuple[Callable[[], FakeConnection], FakeConnection]:
    """Create a provider and expose its connection for assertions."""
    connection = FakeConnection(rows)
    return lambda: connection, connection


class InspectorTests(unittest.TestCase):
    """Verify inspectors map database rows to typed metadata."""

    def test_table_inspector_maps_rows_and_closes_connection(self) -> None:
        provider, connection = provider_for([
            {
                "table_name": "orders",
                "schema_name": "public",
                "table_type": "BASE TABLE",
                "estimated_rows": 12,
            }
        ])

        tables = TableInspector(provider).get_tables()

        self.assertEqual(tables, [TableInfo(table_name="orders", schema_name="public", table_type="BASE TABLE", estimated_rows=12)])
        self.assertTrue(connection.closed)
        self.assertIsNotNone(connection.cursor_instance.executed_query)

    def test_column_inspector_maps_rows(self) -> None:
        provider, _ = provider_for([
            {
                "table_name": "orders",
                "column_name": "id",
                "data_type": "bigint",
                "is_nullable": False,
                "column_default": None,
                "ordinal_position": 1,
            }
        ])

        columns = ColumnInspector(provider).get_columns()

        self.assertEqual(columns[0].column_name, "id")
        self.assertFalse(columns[0].is_nullable)

    def test_key_inspector_maps_primary_and_foreign_keys(self) -> None:
        primary_provider, _ = provider_for([{"table_name": "orders", "column_name": "id"}])
        foreign_provider, _ = provider_for([
            {
                "source_table": "orders",
                "source_column": "customer_id",
                "target_table": "customers",
                "target_column": "id",
            }
        ])

        self.assertEqual(
            KeyInspector(primary_provider).get_primary_keys(),
            [PrimaryKeyInfo(table_name="orders", column_name="id")],
        )
        self.assertEqual(
            KeyInspector(foreign_provider).get_foreign_keys(),
            [
                ForeignKeyInfo(
                    source_table="orders",
                    source_column="customer_id",
                    target_table="customers",
                    target_column="id",
                )
            ],
        )

    def test_relation_inspector_builds_parent_to_child_relation(self) -> None:
        relations = RelationInspector().build_relations([
            ForeignKeyInfo(
                source_table="orders",
                source_column="customer_id",
                target_table="customers",
                target_column="id",
            )
        ])

        self.assertEqual(
            relations,
            [
                RelationInfo(
                    parent_table="customers",
                    parent_column="id",
                    child_table="orders",
                    child_column="customer_id",
                )
            ],
        )

    def test_index_inspector_parses_unique_expression_index(self) -> None:
        provider, _ = provider_for([
            {
                "table_name": "users",
                "index_name": "users_email_lower_idx",
                "index_definition": "CREATE UNIQUE INDEX users_email_lower_idx ON public.users USING btree (lower(email), tenant_id)",
            }
        ])

        indexes = IndexInspector(provider).get_indexes()

        self.assertEqual(
            indexes,
            [
                IndexInfo(
                    table_name="users",
                    index_name="users_email_lower_idx",
                    index_definition="CREATE UNIQUE INDEX users_email_lower_idx ON public.users USING btree (lower(email), tenant_id)",
                    indexed_columns=["lower(email)", "tenant_id"],
                    is_unique=True,
                )
            ],
        )

    def test_index_inspector_handles_malformed_definition(self) -> None:
        inspector = IndexInspector(lambda: FakeConnection([]))

        with self.assertLogs("src.db_engine.inspectors.index_inspector", level="WARNING"):
            self.assertEqual(inspector._extract_indexed_columns("not valid SQL"), [])

    def test_database_failure_returns_empty_result(self) -> None:
        def failing_provider() -> Any:
            raise psycopg2.OperationalError("database unavailable")

        with self.assertLogs("src.db_engine.inspectors.table_inspector", level="ERROR"):
            self.assertEqual(TableInspector(failing_provider).get_tables(), [])
        with self.assertLogs("src.db_engine.inspectors.column_inspector", level="ERROR"):
            self.assertEqual(ColumnInspector(failing_provider).get_columns(), [])
        with self.assertLogs("src.db_engine.inspectors.key_inspector", level="ERROR"):
            self.assertEqual(KeyInspector(failing_provider).get_primary_keys(), [])
        with self.assertLogs("src.db_engine.inspectors.index_inspector", level="ERROR"):
            self.assertEqual(IndexInspector(failing_provider).get_indexes(), [])

    def test_schema_inspector_assembles_all_results(self) -> None:
        foreign_key = ForeignKeyInfo(
            source_table="orders",
            source_column="customer_id",
            target_table="customers",
            target_column="id",
        )
        table_inspector = Mock(get_tables=Mock(return_value=[]))
        column_inspector = Mock(get_columns=Mock(return_value=[]))
        key_inspector = Mock(
            get_primary_keys=Mock(return_value=[]),
            get_foreign_keys=Mock(return_value=[foreign_key]),
        )
        relation_inspector = RelationInspector()
        index_inspector = Mock(get_indexes=Mock(return_value=[]))

        schema = SchemaInspector(
            table_inspector=table_inspector,
            column_inspector=column_inspector,
            key_inspector=key_inspector,
            relation_inspector=relation_inspector,
            index_inspector=index_inspector,
        ).inspect()

        self.assertEqual(schema.foreign_keys, [foreign_key])
        self.assertEqual(schema.relations[0].child_table, "orders")
        table_inspector.get_tables.assert_called_once_with()
        column_inspector.get_columns.assert_called_once_with()
        key_inspector.get_primary_keys.assert_called_once_with()
        key_inspector.get_foreign_keys.assert_called_once_with()
        index_inspector.get_indexes.assert_called_once_with()

    def test_schema_inspector_factory_creates_all_metadata_inspectors(self) -> None:
        inspector = SchemaInspector.from_connection_provider(lambda: FakeConnection([]))

        self.assertIsInstance(inspector._table_inspector, TableInspector)
        self.assertIsInstance(inspector._column_inspector, ColumnInspector)
        self.assertIsInstance(inspector._key_inspector, KeyInspector)
        self.assertIsInstance(inspector._relation_inspector, RelationInspector)
        self.assertIsInstance(inspector._index_inspector, IndexInspector)


if __name__ == "__main__":
    unittest.main()
