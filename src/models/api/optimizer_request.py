from pydantic import BaseModel #type:ignore


class OptimizeQueryRequest(BaseModel):
    query_id: str


class CompareQueryRequest(BaseModel):
    original_query: str
    optimized_query: str
