"""Query Optimizer Agent."""

import json
import logging
import os

from langchain_core.messages import HumanMessage # type:ignore

from src.agent.config import create_deepseek_llm
from src.agent.query_optimizer.models import (
    CostComparisonResult,
    LLMOptimizationResponse,
    OptimizationResult,
)
from src.agent.query_optimizer.prompts import OPTIMIZATION_PROMPT

from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)
from src.db_engine.inspectors.explain_plan_inspector import (
    ExplainPlanInspector,
)

from src.models.schema.schema_model import DatabaseSchema
from src.models.statistics.query_stats_model import QueryStats


class QueryOptimizerAgent:
    """
    AI agent responsible for SQL optimization.

    Responsibilities:
        - Retrieve slow queries
        - Analyze execution plans
        - Generate optimized SQL
        - Recommend indexes
        - Compare execution costs

    The agent never executes optimized SQL.
    """

    def __init__(
        self,
        query_stats_inspector: QueryStatsInspector,
        schema_inspector: SchemaInspector,
        explain_plan_inspector: ExplainPlanInspector,
    ) -> None:

        self._query_stats_inspector = query_stats_inspector
        self._schema_inspector = schema_inspector
        self._explain_plan_inspector = explain_plan_inspector

        self._llm = create_deepseek_llm()

        self._logger = logging.getLogger(__name__)

        self._top_slow_queries = int(
            os.getenv("TOP_SLOW_QUERIES", "20")
        )

    # =====================================================
    # Slow Queries
    # =====================================================

    def get_slow_queries(
        self,
    ) -> list[QueryStats]:
        """
        Return the top N slowest queries.

        Ranking is based on total execution time.
        """

        queries = (
            self._query_stats_inspector.get_query_stats()
        )

        return sorted(
            queries,
            key=lambda query: query.total_exec_time,
            reverse=True,
        )[: self._top_slow_queries]

    # =====================================================
    # Query Optimization
    # =====================================================

    def optimize_query(
        self,
        query: str,
    ) -> OptimizationResult:
        """
        Generate an optimized version of a SQL query.
        """

        schema = self._schema_inspector.inspect()

        explain_plan = (
            self._explain_plan_inspector.get_plan(
                query
            )
        )

        prompt = OPTIMIZATION_PROMPT.format(
            schema=self._schema_to_text(schema),
            query=query,
            plan=json.dumps(
                explain_plan.raw_plan,
                indent=2,
                default=str,
            ),
        )

        response = self._llm.invoke(
            [
                HumanMessage(
                    content=prompt,
                )
            ]
        )

        try:

            response_data = json.loads(
                response.content
            )

            validated = (
                LLMOptimizationResponse.model_validate(
                    response_data
                )
            )

        except Exception as exc:

            self._logger.exception(
                "Failed to parse optimization response."
            )

            raise ValueError(
                "Invalid DeepSeek optimization response."
            ) from exc

        return OptimizationResult(
            original_query=query,
            optimized_query=validated.optimized_query,
            explanation=validated.explanation,
            index_recommendations=(
                validated.index_recommendations
            ),
        )

    # =====================================================
    # Cost Comparison
    # =====================================================

    def compare_queries(
        self,
        original_query: str,
        optimized_query: str,
    ) -> CostComparisonResult:
        """
        Compare EXPLAIN costs for two queries.
        """

        original_plan = (
            self._explain_plan_inspector.get_plan(
                original_query
            )
        )

        optimized_plan = (
            self._explain_plan_inspector.get_plan(
                optimized_query
            )
        )

        before = original_plan.costs
        after = optimized_plan.costs

        improvement_percent = 0.0

        if before.total_cost > 0:

            improvement_percent = (
                (
                    before.total_cost
                    - after.total_cost
                )
                / before.total_cost
            ) * 100

        return CostComparisonResult(
            startup_cost_before=(
                before.startup_cost
            ),
            startup_cost_after=(
                after.startup_cost
            ),
            total_cost_before=(
                before.total_cost
            ),
            total_cost_after=(
                after.total_cost
            ),
            estimated_rows_before=(
                before.plan_rows
            ),
            estimated_rows_after=(
                after.plan_rows
            ),
            improvement_percent=round(
                improvement_percent,
                2,
            ),
        )

    # =====================================================
    # Helpers
    # =====================================================

    def _schema_to_text(
        self,
        schema: DatabaseSchema,
    ) -> str:
        """
        Convert DatabaseSchema into a compact text
        representation for LLM consumption.
        """

        lines: list[str] = []

        for table in schema.tables:

            lines.append(
                f"TABLE: {table.table_name}"
            )

            columns = [
                column
                for column in schema.columns
                if column.table_name
                == table.table_name
            ]

            for column in columns:

                lines.append(
                    f"  - {column.column_name}"
                    f" ({column.data_type})"
                )

        return "\n".join(lines)