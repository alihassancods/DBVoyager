"""FastAPI routes for DBVoyager's Custom Query Generator & Execution Service."""

import logging
from typing import Any, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.services.query.generator_service import CustomQueryGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query-generator", tags=["Query Generator"])


# --- Schemas ---

class GenerateQueryRequest(BaseModel):
    db_name: str = Field(default="postgres", description="Target database name")
    prompt: str = Field(..., description="Natural language prompt describing the SQL query")


class GenerateQueryResponse(BaseModel):
    success: bool
    explanation: Optional[str] = None
    query_type: str
    sql: Optional[str] = None
    is_mutating: bool
    error: Optional[str] = None


class ExecuteQueryRequest(BaseModel):
    db_name: str = Field(default="postgres", description="Target database name")
    sql: str = Field(..., description="The approved SQL query script to execute")
    is_mutating: bool = Field(default=False, description="Flag indicating whether query alters state")


class QueryResultSet(BaseModel):
    columns: List[str]
    rows: List[List[Any]]


class ExecuteQueryResponse(BaseModel):
    success: bool
    message: str
    results: Optional[List[QueryResultSet]] = None
    error: Optional[str] = None


# --- Helper Methods ---

def _get_schema_context(db_name: str) -> dict[str, Any]:
    """Helper to inspect schema metadata for target DB."""
    def connection_provider():
        return get_connection(db_name)

    try:
        inspector = SchemaInspector.from_connection_provider(connection_provider)
        schema = inspector.inspect()

        schema_map = {}
        for col in schema.columns:
            if hasattr(col, "table_name") and hasattr(col, "column_name"):
                tbl = col.table_name
                if tbl not in schema_map:
                    schema_map[tbl] = []
                schema_map[tbl].append(col.column_name)

        return {"tables": schema_map}
    except Exception as exc:
        logger.error("Failed to inspect schema context for '%s': %s", db_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to inspect database schema context: {str(exc)}"
        )


# --- Endpoints ---

@router.post("/generate", response_model=GenerateQueryResponse)
async def generate_sql(payload: GenerateQueryRequest):
    """
    Translates a natural language request into a grounded PostgreSQL query,
    returning an explanation, SQL, and query classification (READ-ONLY / MUTATING).
    """
    schema_context = _get_schema_context(payload.db_name)
    generator = CustomQueryGenerator()

    result = generator.generate_query(payload.prompt, schema_context)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to generate query")
        )

    return GenerateQueryResponse(
        success=True,
        explanation=result.get("explanation"),
        query_type=result.get("query_type", "READ-ONLY"),
        sql=result.get("sql"),
        is_mutating=result.get("is_mutating", False),
    )


@router.post("/execute", response_model=ExecuteQueryResponse)
async def execute_query(payload: ExecuteQueryRequest):
    """
    Executes an approved SQL query against the specified target database.
    """
    def connection_provider():
        return get_connection(payload.db_name)

    try:
        exec_res = CustomQueryGenerator.execute_query(
            connection_provider=connection_provider,
            sql_script=payload.sql,
            is_mutating=payload.is_mutating,
        )

        formatted_results = None
        if exec_res.get("results"):
            formatted_results = [
                QueryResultSet(columns=res["columns"], rows=res["rows"])
                for res in exec_res["results"]
            ]

        return ExecuteQueryResponse(
            success=True,
            message="Query executed successfully.",
            results=formatted_results,
        )

    except Exception as exc:
        logger.error("Execution failure on database '%s': %s", payload.db_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(exc)}"
        )