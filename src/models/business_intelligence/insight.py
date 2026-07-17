from pydantic import BaseModel, Field #type: ignore


class Insight(BaseModel):
    """
    Final business intelligence answer.
    """

    summary: str = Field(
        description="High-level business conclusion"
    )

    evidence: list[str] = Field(
        default_factory=list,
        description="Evidence supporting the conclusion"
    )

    recommendations: list[str] = Field(
        default_factory=list,
        description="Suggested actions"
    )