"""Safe aggregate execution for approved KPI definitions."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .models import KPIDefinition, KPISnapshot


def _identifier(value: str) -> str:
    if not value.replace("_", "").isalnum() or not value or value[0].isdigit():
        raise ValueError("Invalid approved identifier")
    return f'"{value}"'


class KPIAggregateExecutor:
    """Build and execute aggregate-only SQL from an approved KPI definition."""

    def __init__(self, connection_provider: Callable[[], Any], statement_timeout_ms: int = 10_000) -> None:
        self._connection_provider = connection_provider
        self._statement_timeout_ms = statement_timeout_ms

    def execute(self, definition: KPIDefinition, analysis_run_id: str | None = None) -> KPISnapshot:
        table = f"{_identifier(definition.schema_name)}.{_identifier(definition.table_name)}"
        aggregate = "COUNT(*)" if definition.aggregation == "count" else (
            f"{definition.aggregation.upper()}({_identifier(definition.measure_column or '')})"
        )
        select, group_by, order_by = [], [], []
        if definition.time_column:
            bucket = f"date_trunc('{definition.time_grain}', {_identifier(definition.time_column)})"
            select.append(f"{bucket} AS period")
            group_by.append(bucket)
            order_by.append("period")
        if definition.dimension_column:
            dimension = _identifier(definition.dimension_column)
            select.append(f"{dimension} AS dimension")
            group_by.append(dimension)
            order_by.append("value DESC")
        select.append(f"{aggregate} AS value")
        sql = f"SELECT {', '.join(select)} FROM {table}"
        if group_by:
            sql += f" GROUP BY {', '.join(group_by)}"
        if order_by:
            sql += f" ORDER BY {', '.join(order_by)}"
        sql += " LIMIT %s"

        started = time.monotonic()
        connection = self._connection_provider()
        try:
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = %s", (str(self._statement_timeout_ms),))
                cursor.execute(sql, (definition.max_points,))
                names = [column.name for column in cursor.description]
                points = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
            return KPISnapshot(
                kpi_definition_id=definition.id,
                monitored_database_id=definition.monitored_database_id,
                analysis_run_id=analysis_run_id,
                sql=sql,
                points=points,
                execution_ms=(time.monotonic() - started) * 1000,
            )
        finally:
            connection.close()
