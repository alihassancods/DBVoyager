"""Owner-scoped natural-language SQL planner."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.agent.business_intelligence.validator import SQLValidator
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.services.query.generator_service import CustomQueryGenerator

from .analysis_repository import ensure_owned_database
from .auth import current_user
from .resource_cache import cache_resource, cached_value
from .store import connection_provider


router = APIRouter(prefix="/connections/{connection_id}/query-planner", tags=["Query Planner"])


class GenerateQueryRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4_000)


class GenerateQueryResponse(BaseModel):
    explanation: str | None = None
    query_type: str
    sql: str
    executable: bool
    execution_block_reason: str | None = None


def _schema_context(connection_id: str, owner: str) -> dict[str, Any]:
    schema = SchemaInspector.from_connection_provider(connection_provider(connection_id, owner)).inspect()
    tables: dict[str, list[str]] = {}
    for column in schema.columns:
        tables.setdefault(column.table_name, []).append(column.column_name)
    return {"tables": tables}


@router.post("/generate", response_model=GenerateQueryResponse)
def generate_sql(
    connection_id: str,
    payload: GenerateQueryRequest,
    user: dict[str, object] = Depends(current_user),
) -> GenerateQueryResponse:
    owner = str(user["sub"])
    ensure_owned_database(connection_id, owner)
    schema_context = _schema_context(connection_id, owner)
    result = cached_value(
        connection_id,
        cache_resource("querygen", {"prompt": payload.prompt, "schema": schema_context}),
        lambda: CustomQueryGenerator().generate_query(payload.prompt, schema_context),
        3600,
    )
    if not result.get("success") or not result.get("sql"):
        raise HTTPException(status_code=422, detail=result.get("error", "Could not generate SQL"))
    validation = SQLValidator().validate(str(result["sql"]))
    return GenerateQueryResponse(
        explanation=result.get("explanation"),
        query_type=str(result.get("query_type", "UNKNOWN")),
        sql=str(result["sql"]),
        executable=validation.is_valid,
        execution_block_reason=validation.reason,
    )
