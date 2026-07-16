"""Tests for schema metadata models."""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.schema import (
    ColumnInfo,
    DatabaseSchema,
    ForeignKeyInfo,
    IndexInfo,
    PrimaryKeyInfo,
    RelationInfo,
    TableInfo,
)


class SchemaModelTests(unittest.TestCase):
    """Verify schema models validate and serialize expected metadata."""

    def test_database_schema_accepts_complete_metadata(self) -> None:
        table = TableInfo(
            table_name="orders",
            schema_name="public",
            table_type="BASE TABLE",
            estimated_rows=42,
        )
        column = ColumnInfo(
            table_name="orders",
            column_name="id",
            data_type="bigint",
            is_nullable=False,
            column_default="nextval('orders_id_seq'::regclass)",
            ordinal_position=1,
        )
        primary_key = PrimaryKeyInfo(table_name="orders", column_name="id")
        foreign_key = ForeignKeyInfo(
            source_table="orders",
            source_column="customer_id",
            target_table="customers",
            target_column="id",
        )
        relation = RelationInfo(
            parent_table="customers",
            parent_column="id",
            child_table="orders",
            child_column="customer_id",
        )
        index = IndexInfo(
            table_name="orders",
            index_name="orders_customer_id_idx",
            index_definition="CREATE INDEX orders_customer_id_idx ON public.orders USING btree (customer_id)",
            indexed_columns=["customer_id"],
            is_unique=False,
        )

        schema = DatabaseSchema(
            tables=[table],
            columns=[column],
            primary_keys=[primary_key],
            foreign_keys=[foreign_key],
            relations=[relation],
            indexes=[index],
        )

        self.assertEqual(schema.tables[0].table_name, "orders")
        self.assertEqual(schema.columns[0].ordinal_position, 1)
        self.assertEqual(schema.foreign_keys[0].target_table, "customers")
        self.assertEqual(schema.indexes[0].indexed_columns, ["customer_id"])

    def test_table_allows_unknown_row_estimate(self) -> None:
        table = TableInfo(
            table_name="events",
            schema_name="public",
            table_type="BASE TABLE",
            estimated_rows=None,
        )

        self.assertIsNone(table.estimated_rows)


if __name__ == "__main__":
    unittest.main()
