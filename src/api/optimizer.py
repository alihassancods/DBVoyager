# src/api/optimizer.py

"""
FastAPI routes for the Query Optimizer feature.

Responsibilities:
- Validate requests
- Create dependencies
- Delegate work to QueryOptimizerAgent
- Return typed responses

No business logic should live here.
"""

from fastapi import APIRouter, HTTPException #type: ignore

from src.agent.query_optimizer.optimizer_agent import QueryOptimizerAgent

from src.db_engine.connection import get_connection

from src.db_engine.inspectors.schema_inspector import (
    SchemaInspector,
)

from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)

from src.db_engine.inspectors.explain_plan_inspector import (
    ExplainPlanInspector,
)

from src.models.api.optimizer_request import (
    OptimizeQueryRequest,
    CompareQueryRequest,
)

from src.models.api.optimizer_response import (
    SlowQueriesResponse,
    SlowQueryResponse,
    OptimizeQueryResponse,
    CompareQueryResponse,
)

router = APIRouter(
    prefix="/optimizer",
    tags=["Query Optimizer"],
)


def connection_provider():
    """
    Shared PostgreSQL connection provider.
    """
    return get_connection()


def get_optimizer_agent() -> QueryOptimizerAgent:
    """
    Construct a QueryOptimizerAgent using existing inspectors.
    """

    return QueryOptimizerAgent(
        query_stats_inspector=QueryStatsInspector(
            connection_provider
        ),
        schema_inspector=SchemaInspector.from_connection_provider(
            connection_provider
        ),
        explain_plan_inspector=ExplainPlanInspector(
            connection_provider
        ),
    )


@router.get(
    "/slow-queries",
    response_model=SlowQueriesResponse,
)
def get_slow_queries() -> SlowQueriesResponse:
    """
    Return the slowest queries from pg_stat_statements.
    """

    try:
        agent = get_optimizer_agent()

        queries = agent.get_slow_queries()

        return SlowQueriesResponse(
            queries=[
                SlowQueryResponse(
                    query=query.query,
                    calls=query.calls,
                    total_exec_time=query.total_exec_time,
                    mean_exec_time=query.mean_exec_time,
                    rows_returned=query.rows_returned,
                )
                for query in queries
            ]
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve slow queries: {str(exc)}",
        ) from exc


@router.post(
    "/optimize",
    response_model=OptimizeQueryResponse,
)
def optimize_query(
    request: OptimizeQueryRequest,
) -> OptimizeQueryResponse:
    """
    Optimize a SQL query using:
    - Schema context
    - EXPLAIN plan
    - DeepSeek
    """

    try:
        agent = get_optimizer_agent()

        result = agent.optimize_query(
            request.query
        )

        return OptimizeQueryResponse(
            original_query=result.original_query,
            optimized_query=result.optimized_query,
            explanation=result.explanation,
            index_recommendations=result.index_recommendations,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Query optimization failed: {str(exc)}",
        ) from exc


@router.post(
    "/compare",
    response_model=CompareQueryResponse,
)
def compare_queries(
    request: CompareQueryRequest,
) -> CompareQueryResponse:
    """
    Compare original and optimized query costs using EXPLAIN.
    """

    try:
        agent = get_optimizer_agent()

        comparison = agent.compare_queries(
            request.original_query,
            request.optimized_query,
        )

        return CompareQueryResponse(
            startup_cost_before=comparison.startup_cost_before,
            startup_cost_after=comparison.startup_cost_after,
            total_cost_before=comparison.total_cost_before,
            total_cost_after=comparison.total_cost_after,
            estimated_rows_before=comparison.estimated_rows_before,
            estimated_rows_after=comparison.estimated_rows_after,
            improvement_percent=comparison.improvement_percent,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Query comparison failed: {str(exc)}",
        ) from exc