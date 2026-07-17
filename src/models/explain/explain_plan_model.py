"""Models representing PostgreSQL EXPLAIN plan results."""

from pydantic import BaseModel, Field #type:ignore
from typing import Any


class ExplainCost(BaseModel):
    """
    High-level planner cost metrics extracted from an EXPLAIN plan.
    """

    startup_cost: float = Field(
        ge=0,
        description="Estimated cost before returning the first row.",
    )

    total_cost: float = Field(
        ge=0,
        description="Estimated total execution cost.",
    )

    plan_rows: int = Field(
        ge=0,
        description="Estimated number of rows returned.",
    )


class ExplainPlan(BaseModel):
    """
    PostgreSQL execution plan together with extracted cost metrics.
    """

    raw_plan: list[dict[str, Any]]

    costs: ExplainCost