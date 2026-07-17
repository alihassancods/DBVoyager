"""LLM-backed KPI candidate discovery from metadata only."""

import json
import re
from typing import Any

from src.agent.config import create_deepseek_llm
from src.models.schema.schema_model import DatabaseSchema

from .models import KPICandidate


_SENSITIVE = re.compile(r"password|token|secret|email|phone|address|national|ssn", re.I)


class KPIDiscoveryAgent:
    """Propose chartable KPIs without seeing customer rows."""

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm or create_deepseek_llm()

    def discover(self, schema: DatabaseSchema, summaries: dict[tuple[str, str], str]) -> list[KPICandidate]:
        allowed_columns = {
            (table.schema_name, column.table_name, column.column_name)
            for table in schema.tables
            for column in schema.columns
            if table.table_name == column.table_name and not _SENSITIVE.search(column.column_name)
        }
        context = {
            "tables": [
                {
                    "schema": table.schema_name,
                    "table": table.table_name,
                    "estimated_rows": table.estimated_rows,
                    "summary": summaries.get((table.schema_name, table.table_name)),
                    "columns": [
                        {"name": column.column_name, "type": column.data_type}
                        for column in schema.columns
                        if column.table_name == table.table_name and not _SENSITIVE.search(column.column_name)
                    ],
                }
                for table in schema.tables
            ],
            "relationships": [key.model_dump() for key in schema.foreign_keys],
        }
        prompt = (
            "Propose chartable business KPIs from database metadata only. Never use sensitive columns. "
            "Return JSON array only. Each item must contain schema_name, table_name, measure_column "
            "(null only for count), aggregation (sum/count/avg/min/max), time_column, dimension_column, "
            "time_grain (day/week/month/quarter/year), title, rationale, confidence (0..1).\n\n"
            + json.dumps(context, default=str)
        )
        response = self._llm.invoke(prompt)
        try:
            content = str(response.content).strip()
            match = re.search(r"\[.*\]", content, re.S)
            candidates = [KPICandidate.model_validate(item) for item in json.loads(match.group(0) if match else content)]
        except Exception as exc:
            raise ValueError("KPI discovery returned invalid JSON") from exc
        return [candidate for candidate in candidates if self._is_allowed(candidate, allowed_columns)]

    @staticmethod
    def _is_allowed(candidate: KPICandidate, allowed_columns: set[tuple[str, str, str]]) -> bool:
        columns = (candidate.measure_column, candidate.time_column, candidate.dimension_column)
        return all(
            column is None or (candidate.schema_name, candidate.table_name, column) in allowed_columns
            for column in columns
        )
