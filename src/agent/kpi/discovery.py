"""LLM-backed KPI candidate discovery from metadata only."""

import json
import re
from collections.abc import Mapping
from typing import Any

from src.agent.config import create_deepseek_llm
from src.models.schema.schema_model import DatabaseSchema

from .models import KPICandidate


_SENSITIVE = re.compile(r"password|token|secret|email|phone|address|national|ssn", re.I)


class KPIDiscoveryUnavailable(RuntimeError):
    """The optional KPI discovery service cannot accept a new request."""


class KPIDiscoveryAgent:
    """Propose chartable KPIs without seeing customer rows."""

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    def ensure_available(self) -> None:
        try:
            self._llm = self._llm or create_deepseek_llm()
        except Exception as exc:
            raise KPIDiscoveryUnavailable("KPI discovery is temporarily unavailable.") from exc

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
        self.ensure_available()
        try:
            response = self._llm.invoke(prompt)
        except Exception as exc:
            raise KPIDiscoveryUnavailable("KPI discovery is temporarily unavailable.") from exc
        try:
            content = str(response.content).strip()
            candidates = [candidate for item in self._response_items(content) if (candidate := self._candidate(item))]
            candidates = [candidate for candidate in candidates if self._is_allowed(candidate, allowed_columns)]
            if candidates:
                return candidates
        except Exception as exc:
            raise ValueError("KPI discovery returned invalid JSON") from exc
        raise ValueError("KPI discovery returned no safe candidates")

    @staticmethod
    def _response_items(content: str) -> list[object]:
        """Accept JSON arrays, fenced JSON, and common object wrappers from the model."""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
        decoded: object | None = None
        for start in (index for index, char in enumerate(cleaned) if char in "[{"):
            try:
                decoded, _ = json.JSONDecoder().raw_decode(cleaned[start:])
                break
            except json.JSONDecodeError:
                continue
        if isinstance(decoded, Mapping):
            decoded = next((decoded[key] for key in ("candidates", "kpis", "data", "items", "results") if isinstance(decoded.get(key), list)), decoded)
        return decoded if isinstance(decoded, list) else []

    @staticmethod
    def _candidate(item: object) -> KPICandidate | None:
        if not isinstance(item, Mapping):
            return None
        aliases = {
            "schema": "schema_name", "table": "table_name", "metric": "measure_column",
            "value_column": "measure_column", "date_column": "time_column",
            "group_by": "dimension_column", "name": "title", "description": "rationale",
        }
        data = {aliases.get(str(key), str(key)): value for key, value in item.items()}
        try:
            return KPICandidate.model_validate(data)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_allowed(candidate: KPICandidate, allowed_columns: set[tuple[str, str, str]]) -> bool:
        columns = (candidate.measure_column, candidate.time_column, candidate.dimension_column)
        return all(
            column is None or (candidate.schema_name, candidate.table_name, column) in allowed_columns
            for column in columns
        )
