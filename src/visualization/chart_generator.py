"""
Chart Generator

Converts SQL result rows into chart definitions.
"""

from __future__ import annotations

from typing import Any

from src.visualization.model import Chart


class ChartGenerator:
    """
    Generates charts from SQL results.
    """

    def generate(
        self,
        rows: list[dict[str, Any]],
    ) -> list[Chart]:

        if not rows:
            return []

        first_row = rows[0]

        columns = list(first_row.keys())

        if len(columns) < 2:
            return []

        x_column = columns[0]
        y_column = columns[1]

        return [
            Chart(
                chart_type="bar",
                title=f"{y_column} by {x_column}",
                x_axis=x_column,
                y_axis=y_column,
                data=rows,
            )
        ]