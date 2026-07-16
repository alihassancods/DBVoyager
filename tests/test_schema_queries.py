"""Tests for PostgreSQL schema metadata queries."""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db_engine.queries.schema_queries import (
    GET_COLUMNS_QUERY,
    GET_FOREIGN_KEYS_QUERY,
    GET_INDEXES_QUERY,
    GET_PRIMARY_KEYS_QUERY,
    GET_TABLES_QUERY,
)


class SchemaQueryTests(unittest.TestCase):
    """Verify the query module exposes complete PostgreSQL query strings."""

    def test_queries_are_non_empty_sql_strings(self) -> None:
        for query in (
            GET_TABLES_QUERY,
            GET_COLUMNS_QUERY,
            GET_PRIMARY_KEYS_QUERY,
            GET_FOREIGN_KEYS_QUERY,
            GET_INDEXES_QUERY,
        ):
            self.assertIsInstance(query, str)
            self.assertIn("SELECT", query.upper())

    def test_queries_use_postgresql_catalogs(self) -> None:
        self.assertIn("information_schema.tables", GET_TABLES_QUERY)
        self.assertIn("information_schema.columns", GET_COLUMNS_QUERY)
        self.assertIn("information_schema.table_constraints", GET_PRIMARY_KEYS_QUERY)
        self.assertIn("information_schema.referential_constraints", GET_FOREIGN_KEYS_QUERY)
        self.assertIn("pg_indexes", GET_INDEXES_QUERY)
        self.assertIn("pg_catalog", GET_TABLES_QUERY)
        self.assertIn("pg_catalog", GET_INDEXES_QUERY)

    def test_queries_limit_visualization_to_application_schema(self) -> None:
        for query in (
            GET_TABLES_QUERY,
            GET_COLUMNS_QUERY,
            GET_PRIMARY_KEYS_QUERY,
            GET_FOREIGN_KEYS_QUERY,
            GET_INDEXES_QUERY,
        ):
            self.assertIn("= 'public'", query)


if __name__ == "__main__":
    unittest.main()
