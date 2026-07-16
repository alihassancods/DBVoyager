from pydantic import BaseModel # type:ignore
from typing import Any

# this the base model for the result we gonna get from the query execution

class QueryResult(BaseModel):
    success: bool
    query: str
    rows: list[dict]
    row_count: int

# this one is to test the health of the database connection and the server version 

class DatabaseHealth(BaseModel):
    connected: bool
    database_name: str
    server_version: str