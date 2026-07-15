from pydantic import BaseModel # type:ignore
from typing import Any


class QueryResult(BaseModel):
    success: bool
    query: str
    rows: list[dict]
    row_count: int


class DatabaseHealth(BaseModel):
    connected: bool
    database_name: str
    server_version: str