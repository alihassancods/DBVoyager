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
        progress: Callable[[str, dict[str, Any]], None] | None = None,
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

        def stage(name: str, status: str, detail: str) -> None:
            if progress:
                progress("stage", {"stage": name, "status": status, "detail": detail})

        # Use SchemaInspector to fetch reality from the database connection
        # if no testing schema context is explicitly provided.
        if not schema_context:
          stage("schema", "running", "Reading database schema")
          schema_context = (
              SchemaInspector.from_connection_provider( #type: ignore
                  self._connection_provider
              ).inspect()
            )
          stage("schema", "complete", "Schema ready")

        # -----------------------------------
        # Phase 1: Planning
        # -----------------------------------
        stage("plan", "running", "Planning the investigation")
        plan = self._create_plan(
            question=question,
            schema_context=schema_context, #type: ignore
        )

        stage("plan", "complete", "Investigation plan ready")
        # -----------------------------------
        # Phase 2: SQL Generation
        # ----------------------------------
        stage("sql", "running", "Generating read-only SQL")
        sql_request = self._generate_sql(
            question=question,
            plan=plan,
            schema_context=schema_context,#type: ignore
        )

        self._schema_validator.validate(
            sql_request.sql,
            schema_context,#type: ignore
        )
        
        stage("sql", "complete", "SQL generated")
        # -----------------------------------
        # Phase 3: Validation
        # -----------------------------------
        stage("validate", "running", "Checking SQL safety")
        self._validate_sql(
            sql_request.sql,
        )

        stage("validate", "complete", "Read-only SQL approved")
        if progress:
            progress("sql_ready", {"sql": sql_request.sql})
        # -----------------------------------
        # Phase 4: Execution
        # -----------------------------------
        stage("execute", "running", "Running a 10-row sample")
        sql_result = self._execute_sql(
            sql_request,
        )

        stage("execute", "complete", f"Received {len(sql_result.rows)} sample rows")
        if progress:
            progress("results_ready", {"columns": list(sql_result.rows[0]) if sql_result.rows else [], "row_count": len(sql_result.rows)})
        # -----------------------------------
        # Phase 5: Analysis
        # -----------------------------------
        stage("analyze", "running", "Writing the business insight")
        insight = self._analyze(
            question=question,
            plan=plan,
            sql_result=sql_result,
            on_delta=(lambda text: progress("insight_delta", {"text": text})) if progress else None,
        )
        stage("analyze", "complete", "Business insight ready")
        # -----------------------------------
        # Phase 6: Charts
        # -----------------------------------
        stage("charts", "running", "Preparing visual summary")
        charts = self._generate_charts(
            sql_result,
        )
        
        stage("charts", "complete", "Visual summary ready")

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

        result = self._query_executor.execute_query(
            request.sql
        )
        return result

    def _analyze(
        self,
        question: str,
        plan: InvestigationPlan,
        sql_result: SQLResult,
        on_delta: Callable[[str], None] | None = None,
    ) -> Insight:
        self._logger.info(
            "Analyzing results..."
        )

        return self._analysis_agent.analyze_stream(
            question=question,
            plan=plan,
            results=[sql_result],
            on_delta=on_delta,
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
