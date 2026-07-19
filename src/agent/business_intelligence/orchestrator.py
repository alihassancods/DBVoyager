"""
Business Intelligence Orchestrator

Coordinates:

1. Planning Agent
2. SQL Generation Agent
3. SQL Validation
4. Query Execution
5. Analysis Agent
6. Chart Generation

This is the main entry point for the BI workflow.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.agent.business_intelligence.analysis_agent import AnalysisAgent
from src.agent.business_intelligence.planner_agent import PlannerAgent
from sql_generation_agent import SQLGenerationAgent

from src.models.business_intelligence.investigation_plan import (
    InvestigationPlan,
)
from src.models.business_intelligence.insight import Insight
from src.models.business_intelligence.sql_request import SQLRequest
from src.models.business_intelligence.sql_result import SQLResult

from src.agent.business_intelligence.validator import SQLValidator

from src.db_engine.inspectors.query_executor_inspector import (
    QueryExecutorInspector,
)

from src.visualization.chart_generator import ChartGenerator
from src.visualization.model import Chart

from src.db_engine.inspectors.schema_inspector import (
    SchemaInspector,
)

from src.agent.business_intelligence.schema_validator import (
    SchemaValidator,
)

import time

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openai" )

from src.db_engine.inspectors.statistics.statistics_inspector import (
    StatisticsInspector,
)

class BusinessIntelligenceOrchestrator:
    """
    Main Business Intelligence workflow.

    User Question
            ↓
    Planner Agent
            ↓
    SQL Generator
            ↓
    SQL Validator
            ↓
    Execute Query
            ↓
    Analysis Agent
            ↓
    Charts
            ↓
    Final Insight
    """

    def __init__(
        self,
        connection_provider: Callable[[], Any],
    ) -> None:
        """
        Initialize the Business Intelligence Orchestrator.
        """
        self._logger = logging.getLogger(__name__)
        self._connection_provider = connection_provider

        self._planner = PlannerAgent()
        self._sql_generator = SQLGenerationAgent()
        self._analysis_agent = AnalysisAgent()

        self._validator = SQLValidator()

        self._schema_validator = SchemaValidator()

        self._query_executor = QueryExecutorInspector(
            connection_provider
        )

        self._chart_generator = ChartGenerator()

    # ==========================================================
    # PUBLIC ENTRYPOINT
    # ==========================================================

    def investigate(
        self,
        question: str,
        schema_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Complete business investigation.

        Example:
        ----------
        Why is revenue decreasing?

        Returns:
        ----------
        {
            plan,
            sql,
            rows,
            insight,
            charts
        }
        """
        self._logger.info(
            "Starting business investigation: %s",
            question,
        )

        # Use SchemaInspector to fetch reality from the database connection
        # if no testing schema context is explicitly provided.
        if not schema_context:
          start = time.perf_counter()

          schema_context = ( 
              SchemaInspector.from_connection_provider( #type: ignore
                  self._connection_provider
              ).inspect()
            )

          print(
          f"Schema Inspector took "
          f"{time.perf_counter() - start:.2f}s"
        )

        # -----------------------------------
        # Phase 1: Planning
        # -----------------------------------
        start = time.perf_counter()
        plan = self._create_plan(
            question=question,
            schema_context=schema_context, #type: ignore
        )

        print(
         f"Planning took "
         f"{time.perf_counter() - start:.2f}s"
        )
        # -----------------------------------
        # Phase 2: SQL Generation
        # ----------------------------------
        start = time.perf_counter()
        sql_request = self._generate_sql(
            question=question,
            plan=plan,
            schema_context=schema_context,#type: ignore
        )

        self._schema_validator.validate(
            sql_request.sql,
            schema_context,#type: ignore
        )
        
        print(
        f"SQL Generation took "
        f"{time.perf_counter() - start:.2f}s"
        )
        # -----------------------------------
        # Phase 3: Validation
        # -----------------------------------
        start = time.perf_counter()
        self._validate_sql(
            sql_request.sql,
        )

        print(
         f"SQL validation took "
        f"{time.perf_counter() - start:.2f}s"
        )
        # -----------------------------------
        # Phase 4: Execution
        # -----------------------------------
        start = time.perf_counter()
        sql_result = self._execute_sql(
            sql_request,
        )

        print(
         f"SQL Execution took "
        f"{time.perf_counter() - start:.2f}s"
        )
        # -----------------------------------
        # Phase 5: Analysis
        # -----------------------------------
        start = time.perf_counter()
        insight = self._analyze(
            question=question,
            plan=plan,
            sql_result=sql_result,
        )

        print(
         f"Analysis took "
        f"{time.perf_counter() - start:.2f}s"
        )
        # -----------------------------------
        # Phase 6: Charts
        # -----------------------------------
        start = time.perf_counter()
        charts = self._generate_charts(
            sql_result,
        )
        
        print(
     f"chart generation took "
    f"{time.perf_counter() - start:.2f}s"
)

        self._logger.info(
            "Investigation completed successfully."
        )

        return {
            "question": question,
            "plan": plan,
            "sql": sql_request.sql,
            "row_count": len(sql_result.rows),
            "rows": sql_result.rows,
            "insight": insight,
            "charts": charts,
        }


    # ==========================================================
    # INTERNAL METHODS
    # ==========================================================

    def _create_plan(
        self,
        question: str,
        schema_context: str,
    ) -> InvestigationPlan:
        self._logger.info(
            "Generating investigation plan..."
        )

        return self._planner.create_plan(
            question=question,
            schema_context=schema_context,
        )

    def _generate_sql(
        self,
        question: str,
        plan: InvestigationPlan,
        schema_context: str,
    ) -> SQLRequest:
        self._logger.info(
            "Generating SQL query..."
        )

        return self._sql_generator.generate_sql(
            question=question,
            plan=plan,
            schema_context=schema_context,
        )

    def _validate_sql(
        self,
        sql: str,
    ) -> None:
        self._logger.info(
            "Validating SQL..."
        )

        validation_result = self._validator.validate(
            sql
        )

        if not validation_result.is_valid:
            raise ValueError(
                f"Unsafe SQL generated: "
                f"{validation_result.reason}"
            )

    def _execute_sql(
        self,
        request: SQLRequest,
    ) -> SQLResult:

        print("\n========== GENERATED SQL ==========")
        print(request.sql)
        print("===================================\n")

        result = self._query_executor.execute_query(
            request.sql
        )

        print("\n========== QUERY RESULTS ==========")
        print(result.rows[:5])
        print("===================================\n")

        result.rows = result.rows[:10]

        return result

    def _analyze(
        self,
        question: str,
        plan: InvestigationPlan,
        sql_result: SQLResult,
    ) -> Insight:
        self._logger.info(
            "Analyzing results..."
        )

        return self._analysis_agent.analyze(
            question=question,
            plan=plan,
            results=[sql_result],
        )

    def _generate_charts(
        self,
        sql_result: SQLResult,
    ) -> list[Chart]:
        self._logger.info(
            "Generating charts..."
        )

        try:
            return self._chart_generator.generate(
                sql_result.rows
            )

        except Exception:
            self._logger.exception(
                "Chart generation failed."
            )
            return []