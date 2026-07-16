"""Generate concise business descriptions for inspected database tables."""

import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from src.db_engine.inspectors.schema_inspector import SchemaInspector

from .config import create_deepseek_llm


class TableSummaryInput(BaseModel):
    table_name: str = Field(min_length=1)
    table_columns: list[str]
    relationships: list[str] = Field(default_factory=list)


class TableBusinessSummaryAgent:
    """A LangChain-compatible agent that summarizes one database table."""

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm or create_deepseek_llm()

    def summarize(self, table: TableSummaryInput) -> str:
        """Return exactly two business-focused sentences for ``table``."""
        prompt = (
            "Write exactly two plain-text business sentences about this PostgreSQL table. "
            "Explain what data it stores and why it exists, then name its most important columns. "
            "Do not invent facts, use headings, or add bullet points.\n\n"
            f"Table metadata:\n{json.dumps(table.model_dump(), indent=2)}"
        )
        response = self._llm.invoke(prompt)
        sentences = re.split(r"(?<=[.!?])\s+", str(response.content).strip())
        if len(sentences) < 2:
            raise ValueError("LLM response did not contain two sentences")
        # ponytail: sentence boundary heuristic; use structured output if abbreviated prose becomes common.
        return " ".join(sentences[:2])

    def summarize_database_table(
        self, table_name: str, connection_provider: Callable[[], Any]
    ) -> str:
        """Inspect one connected database table and return its business summary."""
        schema = SchemaInspector.from_connection_provider(connection_provider).inspect()
        if not any(table.table_name == table_name for table in schema.tables):
            raise ValueError(f"Table not found: {table_name}")
        table = TableSummaryInput(
            table_name=table_name,
            table_columns=[
                f"{column.column_name} ({column.data_type})"
                for column in schema.columns
                if column.table_name == table_name
            ],
            relationships=[
                f"{key.source_table}.{key.source_column} -> {key.target_table}.{key.target_column}"
                for key in schema.foreign_keys
                if table_name in (key.source_table, key.target_table)
            ],
        )
        return self.summarize(table)

    async def summarize_database_table_async(
        self, table_name: str, connection_provider: Callable[[], Any]
    ) -> str:
        """Async wrapper for FastAPI endpoints."""
        import asyncio

        return await asyncio.to_thread(
            self.summarize_database_table, table_name, connection_provider
        )
