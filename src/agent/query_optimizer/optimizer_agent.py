"""Query Optimizer Agent."""

import json
import logging
import os
import threading
import time
import hashlib
from pathlib import Path

from langchain_core.messages import HumanMessage  # type:ignore

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

REFRESH_INTERVAL_SECONDS = 1800  # 30 minutes


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

    #updated this one to include the cache into the system
    def __init__(
        self,
        query_stats_inspector: QueryStatsInspector,
        schema_inspector: SchemaInspector,
        explain_plan_inspector: ExplainPlanInspector,
        db_identifier: str = "default",
        enable_auto_refresh: bool = True,
    ) -> None:
        self._query_stats_inspector = query_stats_inspector
        self._schema_inspector = schema_inspector
        self._explain_plan_inspector = explain_plan_inspector
        self._llm = create_deepseek_llm()
        self._logger = logging.getLogger(__name__)

        self._top_slow_queries = int(os.getenv("TOP_SLOW_QUERIES", "20"))

        # Generate a unique cache filename per database identifier
        sanitized_id = "".join(c for c in db_identifier if c.isalnum() or c in ("_", "-"))
        db_hash = hashlib.md5(db_identifier.encode()).hexdigest()[:8]
        self._cache_file = Path(f".schema_cache_{sanitized_id}_{db_hash}.json")

        # Cache container & lock for schema metadata
        self._cached_schema: DatabaseSchema | None = None
        self._cache_lock = threading.Lock()

        # Load existing disk cache or perform initial DB inspection
        self._init_schema_cache()

        # Start 30-minute background auto-refresh thread
        if enable_auto_refresh:
            self._start_background_refresh()

    def _init_schema_cache(self) -> None:
        """Load schema from instance disk cache or inspect DB on agent startup."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r") as f:
                    data = json.load(f)
                    self._cached_schema = DatabaseSchema.model_validate(data)
                    self._logger.info("Loaded schema cache from disk (%s).", self._cache_file)
                    return
            except Exception as exc:
                self._logger.warning("Failed loading disk cache (%s), falling back to DB: %s", self._cache_file, exc)

        # Fallback: Perform initial DB inspection
        self.refresh_schema_cache()

    def refresh_schema_cache(self) -> DatabaseSchema:
        """Inspect DB schema, update RAM cache, and persist to unique disk cache."""
        try:
            schema = self._schema_inspector.inspect()
            with self._cache_lock:
                self._cached_schema = schema

            # Persist to local disk using instance cache file
            with open(self._cache_file, "w") as f:
                f.write(schema.model_dump_json())

            self._logger.info("Schema cache updated successfully (%s).", self._cache_file)
            return schema
        except Exception as exc:
            self._logger.error("Failed to refresh schema cache (%s): %s", self._cache_file, exc)
            if self._cached_schema:
                return self._cached_schema
            raise

    def _start_background_refresh(self) -> None:
        """Spawn a daemon thread that re-inspects the DB schema every 30 minutes."""
        def _refresh_loop():
            while True:
                time.sleep(REFRESH_INTERVAL_SECONDS)
                self._logger.info("Running scheduled 30-minute schema cache refresh...")
                self.refresh_schema_cache()

        thread = threading.Thread(target=_refresh_loop, daemon=True)
        thread.start()

    def get_schema(self, force_refresh: bool = False) -> DatabaseSchema:
        """Fetch and cache schema metadata in memory."""
        if force_refresh:
            return self.refresh_schema_cache()

        with self._cache_lock:
            if self._cached_schema is not None:
                return self._cached_schema

        return self.refresh_schema_cache()

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
        """Generate an optimized version of a SQL query using cached schema."""
        # Use cached schema instead of re-inspecting entire DB
        schema = self.get_schema()

        try:
            plan = self._explain_plan_inspector.get_plan(query).raw_plan
        except RuntimeError as exc:
            self._logger.warning("EXPLAIN unavailable for stored query: %s", exc)
            plan = {"unavailable": str(exc)}

        # Compact payload and filter schema
        prompt = OPTIMIZATION_PROMPT.format(
            schema=self._schema_to_text(schema, query),
            query=query,
            plan=json.dumps(plan, default=str, separators=(',', ':')),
        )

        response = self._llm.invoke([HumanMessage(content=prompt)])

        try:
            response_data = json.loads(response.content)
            validated = LLMOptimizationResponse.model_validate(response_data)
        except Exception as exc:
            self._logger.exception("Failed to parse optimization response.")
            raise ValueError("Invalid DeepSeek optimization response.") from exc

        return OptimizationResult(
            original_query=query,
            optimized_query=validated.optimized_query,
            explanation=validated.explanation,
            index_recommendations=validated.index_recommendations,
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

    # updated it so it will only include tables that are referenced in the query, if a query is provided. If no query is provided, it will include all tables.
    # also updated the main prompt given to the LLM

    def _schema_to_text(
        self,
        schema: DatabaseSchema,
        query: str = "",
    ) -> str:
        """Convert DatabaseSchema into a compact text string filtered by relevant tables."""
        lines: list[str] = []
        query_lower = query.lower()

        for table in schema.tables:
            # Skip tables not referenced in the query
            if query and table.table_name.lower() not in query_lower:
                continue

            lines.append(f"TABLE: {table.table_name}")
            columns = [c for c in schema.columns if c.table_name == table.table_name]
            for column in columns:
                lines.append(f"  - {column.column_name} ({column.data_type})")

        return "\n".join(lines)