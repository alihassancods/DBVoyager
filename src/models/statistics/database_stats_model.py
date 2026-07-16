"""This one will give the stats of the whole database."""

from pydantic import BaseModel, Field #type: ignore


class DatabaseStats(BaseModel):
    """
    Overall database statistics.
    """

    database_name: str

    num_connections: int = Field(
        ge=0,
        description="Current active database connections",
    )

    database_size_mb: float = Field(
        ge=0,
        description="Database size in MB",
    )

    cache_hit_ratio: float = Field(
        ge=0,
        le=100,
        description="Buffer cache hit ratio percentage",
    )