"""Tests for schema visualization."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.visualizers import SchemaVisualizer
from src.models.schema import (
    ColumnInfo,
    DatabaseSchema,
    ForeignKeyInfo,
    IndexInfo,
    PrimaryKeyInfo,
    RelationInfo,
    TableInfo,
)


class SchemaVisualizerTests(unittest.TestCase):
    """Verify schema metadata produces usable diagrams."""

    def test_render_mermaid_includes_entities_columns_and_relationships(self) -> None:
        schema = DatabaseSchema(
            tables=[
                TableInfo(table_name="customers", schema_name="public", table_type="BASE TABLE", estimated_rows=1),
                TableInfo(table_name="orders", schema_name="public", table_type="BASE TABLE", estimated_rows=2),
            ],
            columns=[
                ColumnInfo(table_name="orders", column_name="customer_id", data_type="bigint", is_nullable=False, column_default=None, ordinal_position=2),
                ColumnInfo(table_name="customers", column_name="id", data_type="bigint", is_nullable=False, column_default=None, ordinal_position=1),
                ColumnInfo(table_name="orders", column_name="id", data_type="bigint", is_nullable=False, column_default=None, ordinal_position=1),
            ],
            primary_keys=[
                PrimaryKeyInfo(table_name="customers", column_name="id"),
                PrimaryKeyInfo(table_name="orders", column_name="id"),
            ],
            foreign_keys=[ForeignKeyInfo(source_table="orders", source_column="customer_id", target_table="customers", target_column="id")],
            relations=[RelationInfo(parent_table="customers", parent_column="id", child_table="orders", child_column="customer_id")],
            indexes=[IndexInfo(table_name="orders", index_name="orders_pkey", index_definition="", indexed_columns=["id"], is_unique=True)],
        )

        diagram = SchemaVisualizer().render_mermaid(schema)

        self.assertEqual(
            diagram,
            "erDiagram\n"
            "    %% CUSTOMERS represents customers\n"
            "    CUSTOMERS {\n"
            "        BIGINT ID PK\n"
            "    }\n"
            "    %% ORDERS represents orders\n"
            "    ORDERS {\n"
            "        BIGINT ID PK\n"
            "        BIGINT CUSTOMER_ID FK\n"
            "    }\n"
            "    CUSTOMERS ||--o{ ORDERS : \"id to customer_id\"\n",
        )

    def test_render_mermaid_normalizes_non_mermaid_identifiers(self) -> None:
        schema = DatabaseSchema(
            tables=[TableInfo(table_name="order-items", schema_name="public", table_type="BASE TABLE", estimated_rows=None)],
            columns=[ColumnInfo(table_name="order-items", column_name="line item", data_type="character varying", is_nullable=True, column_default=None, ordinal_position=1)],
            primary_keys=[], foreign_keys=[], relations=[], indexes=[],
        )

        diagram = SchemaVisualizer().render_mermaid(schema)

        self.assertIn("ORDER_ITEMS", diagram)
        self.assertIn("CHARACTER_VARYING LINE_ITEM", diagram)

    def test_render_html_creates_access_style_table_cards_and_relationships(self) -> None:
        schema = DatabaseSchema(
            tables=[
                TableInfo(table_name="customers", schema_name="public", table_type="BASE TABLE", estimated_rows=1),
                TableInfo(table_name="orders", schema_name="public", table_type="BASE TABLE", estimated_rows=2),
            ],
            columns=[
                ColumnInfo(table_name="customers", column_name="id", data_type="bigint", is_nullable=False, column_default=None, ordinal_position=1),
                ColumnInfo(table_name="orders", column_name="customer_id", data_type="bigint", is_nullable=False, column_default=None, ordinal_position=1),
            ],
            primary_keys=[PrimaryKeyInfo(table_name="customers", column_name="id")],
            foreign_keys=[ForeignKeyInfo(source_table="orders", source_column="customer_id", target_table="customers", target_column="id")],
            relations=[RelationInfo(parent_table="customers", parent_column="id", child_table="orders", child_column="customer_id")],
            indexes=[],
        )

        html = SchemaVisualizer().render_html(schema)

        self.assertIn('class="table-card" data-table="customers"', html)
        self.assertIn('class="badge pk">PK</span>', html)
        self.assertIn('class="badge fk">FK</span>', html)
        self.assertIn('"parent": "customers"', html)
        self.assertIn("drawRelationships", html)


if __name__ == "__main__":
    unittest.main()
