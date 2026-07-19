# src/agent/business_intelligence/schema_validator.py

from __future__ import annotations

from typing import Set

try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # pragma: no cover - optional dependency
    sqlglot = None
    exp = None

from src.models.schema.schema_model import DatabaseSchema


class SchemaValidator:

    def validate(
        self,
        sql: str,
        schema: DatabaseSchema,
    ) -> tuple[bool, str | None]:

        if sqlglot is None or exp is None:
            return False, "SQL validation is unavailable: sqlglot is not installed"

        try:
            parsed = sqlglot.parse_one(sql)

        except Exception as exc:
            return False, f"Invalid SQL syntax: {exc}"

        valid_tables: Set[str] = {
            table.table_name.lower()
            for table in schema.tables
        }

        valid_columns: dict[str, Set[str]] = {}

        for column in schema.columns:

            table_name = column.table_name.lower()

            valid_columns.setdefault(
                table_name,
                set(),
            ).add(
                column.column_name.lower()
            )

        # -------------------------
        # CTEs
        # -------------------------

        ctes: Set[str] = set()

        with_clause = parsed.find(exp.With)

        if with_clause:

            for cte in with_clause.expressions:
                ctes.add(
                    cte.alias.lower()
                )

        # -------------------------
        # Tables
        # -------------------------

        aliases: dict[str, str] = {}

        for table in parsed.find_all(exp.Table):

            table_name = table.name.lower()

            if table_name not in valid_tables and table_name not in ctes:

                return (
                    False,
                    f"Unknown table: {table_name}",
                )

            if table.alias:

                aliases[
                    table.alias.lower()
                ] = table_name

        # -------------------------
        # Columns
        # -------------------------

        for column in parsed.find_all(exp.Column):

            column_name = column.name.lower()

            table_alias = (
                column.table.lower()
                if column.table
                else None
            )

            if table_alias:

                actual_table = aliases.get(
                    table_alias,
                    table_alias,
                )

                if actual_table in valid_columns:

                    if (
                        column_name
                        not in valid_columns[
                            actual_table
                        ]
                    ):
                        return (
                            False,
                            f"Column '{column_name}' "
                            f"does not exist in table "
                            f"'{actual_table}'",
                        )

        return True, None