"""
Visualization domain models.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field #type: ignore


ChartType = Literal[
    "bar",
    "line",
    "pie",
    "scatter",
]


class Chart(BaseModel):
    """
    Frontend chart definition.

    Returned by the Business Intelligence workflow and
    rendered by the frontend dashboard.
    """

    chart_type: ChartType

    title: str = Field(
        min_length=1,
        description="Human readable chart title",
    )

    x_axis: str = Field(
        min_length=1,
        description="Column used on x axis",
    )

    y_axis: str = Field(
        min_length=1,
        description="Column used on y axis",
    )

    data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Chart dataset",
    )


class ChartCollection(BaseModel):
    """
    Multiple charts returned by an investigation.
    """

    charts: list[Chart] = Field(
        default_factory=list,
    )