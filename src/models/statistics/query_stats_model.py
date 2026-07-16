"""Now we will make the pydantic model for the query statistics table. Its function will be to store the info about the 
queries"""

from pydantic import BaseModel, Field # type: ignore

class QueryStats(BaseModel):
    """
    Statistics collected from pg_stat_statements.
    """

    query: str = Field(
        description="Normalized SQL query"
    )

    calls: int = Field(
        ge=0,
        description="Number of times query executed"
    )

    total_exec_time: float = Field(
        ge=0,
        description="Total execution time in milliseconds"
    )

    mean_exec_time: float = Field(
        ge=0,
        description="Average execution time"
    )

    rows_returned: int = Field(
        ge=0,
        description="Rows returned by query"
    )