"""Since our model is hallucinating we need to make this one good. This will be maknig sure the model dont hallucinate gets
the accurate data and the correct schema to create the query and the results"""

"""
Schema Formatter

Converts a DatabaseSchema object into a clean text format
that can be injected into LLM prompts.

This helps the SQL generation agent understand the
real database structure and reduces hallucinations.
"""

from src.models.schema.schema_model import DatabaseSchema


class SchemaFormatter:
    """
    Format DatabaseSchema into prompt-friendly text.
    """

    @staticmethod
    def to_prompt(
        schema: DatabaseSchema,
    ) -> str:
        """
        Convert schema metadata into readable text.

        Example output:

        TABLE customers
        - id
        - email
        - name

        TABLE orders
        - id
        - customer_id

        RELATIONSHIPS

        orders.customer_id -> customers.id
        """

        lines: list[str] = []

        # =========================
        # TABLES + COLUMNS
        # =========================

        for table in sorted(
            schema.tables,
            key=lambda t: t.table_name,
        ):
            lines.append(
                f"TABLE {table.table_name}"
            )

            table_columns = [
                column
                for column in schema.columns
                if column.table_name == table.table_name
            ]

            table_columns.sort(
                key=lambda c: c.ordinal_position
            )

            for column in table_columns:
                lines.append(
                    f"- {column.column_name}"
                )

            lines.append("")

        # =========================
        # RELATIONSHIPS
        # =========================

        lines.append("RELATIONSHIPS")
        lines.append("")

        if schema.relations:

            for relation in schema.relations:
                lines.append(
                    f"{relation.child_table}."
                    f"{relation.child_column}"
                    f" -> "
                    f"{relation.parent_table}."
                    f"{relation.parent_column}"
                )

        else:
            lines.append(
                "No relationships found."
            )

        return "\n".join(lines)