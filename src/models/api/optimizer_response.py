from pydantic import BaseModel #type:ignore


class SlowQueryResponse(BaseModel):
    query: str
    calls: int
    total_exec_time: float
    mean_exec_time: float
    rows_returned: int


class SlowQueriesResponse(BaseModel):
    queries: list[SlowQueryResponse]


class OptimizeQueryResponse(BaseModel):
    original_query: str
    optimized_query: str
    explanation: str
    index_recommendations: list[str]


class CompareQueryResponse(BaseModel):
    startup_cost_before: float
    startup_cost_after: float
    total_cost_before: float
    total_cost_after: float
    estimated_rows_before: int
    estimated_rows_after: int
    improvement_percent: float