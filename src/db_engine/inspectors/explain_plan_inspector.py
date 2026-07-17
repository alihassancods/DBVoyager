"""Inspector responsible for retrieving PostgreSQL execution plans."""

import logging
from collections.abc import Callable
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.models.explain.explain_plan_model import (
    ExplainCost,
    ExplainPlan,
)

ConnectionProvider = Callable[[], Any]


class ExplainPlanInspector:
    """
    Collect PostgreSQL execution plans using EXPLAIN.

    This inspector never executes the query itself.
    It only retrieves the planner output.
    """

    def __init__(
        self,
        connection_provider: ConnectionProvider,
    ) -> None:
        self._connection_provider = connection_provider
        self._logger = logging.getLogger(__name__)

    def get_plan(self, query: str) -> ExplainPlan:
        """
        Generate an execution plan for a SQL query.

        Parameters
        ----------
        query:
            SQL statement to analyze.

        Returns
        -------
        ExplainPlan
            Parsed execution plan and extracted cost metrics.
        """
        self._validate_query(query)

        connection = None

        try:
            connection = self._connection_provider()

            with connection.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    f"EXPLAIN (FORMAT JSON) {query}"
                )

                row = cursor.fetchone()

            if row is None:
                raise ValueError(
                    "PostgreSQL returned no execution plan."
                )

            raw_plan = row["QUERY PLAN"]

            return ExplainPlan(
                raw_plan=raw_plan,
                costs=self._extract_costs(raw_plan),
            )

        except psycopg2.Error as exc:
            self._logger.exception(
                "Failed to generate execution plan."
            )
            raise RuntimeError(
                "Execution plan generation failed."
            ) from exc

        finally:
            if connection is not None:
                connection.close()

    def _extract_costs(
        self,
        plan: list[dict[str, Any]],
    ) -> ExplainCost:
        """
        Extract top-level planner metrics from an EXPLAIN plan.
        """

        try:
            root_node = plan[0]["Plan"]

            return ExplainCost(
                startup_cost=float(
                    root_node["Startup Cost"]
                ),
                total_cost=float(
                    root_node["Total Cost"]
                ),
                plan_rows=int(
                    root_node["Plan Rows"]
                ),
            )

        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Invalid PostgreSQL execution plan structure."
            ) from exc

    def _validate_query(
        self,
        query: str,
    ) -> None:
        """
        Restrict EXPLAIN usage to safe read-only statements.
        """

        normalized = query.strip().lower()

        allowed_prefixes = (
            "select",
            "with",
        )

        if not normalized.startswith(allowed_prefixes):
            raise ValueError(
                "Only SELECT and WITH statements are allowed."
            )