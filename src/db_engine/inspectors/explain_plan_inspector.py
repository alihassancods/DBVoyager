"""Inspector responsible for retrieving PostgreSQL execution plans."""

import logging
import re
from collections.abc import Callable
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.models.explain.explain_plan_model import (
    ExplainCost,
    ExplainPlan,
)

ConnectionProvider = Callable[[], Any]
_PARAMETER = re.compile(r"\$(\d+)\b")


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

                explain_query = _PARAMETER.sub("NULL", query)
                cursor.execute(f"EXPLAIN (FORMAT JSON) {explain_query}")

                row = cursor.fetchone()

            if row is None:
                raise ValueError(
                    "PostgreSQL returned no execution plan."
                )

            # Robust key checking: PostgreSQL can return "QUERY PLAN" or "query plan"
            raw_plan = row.get("QUERY PLAN") or row.get("query plan")
            
            if raw_plan is None:
                # If using RealDictCursor failed to map it, fallback to fetching by index
                raw_plan = list(row.values())[0]

            return ExplainPlan(
                raw_plan=raw_plan,
                costs=self._extract_costs(raw_plan),
            )

        except psycopg2.Error as exc:
            # We catch database-side errors (e.g., Table does not exist, syntax errors)
            self._logger.warning(
                f"Database error during EXPLAIN generation: {exc.pgerror or exc}"
            )
            raise RuntimeError(
                f"Execution plan generation failed: {exc.pgcode or 'Unknown database error'}"
            ) from exc
            
        except Exception as exc:
            # Catch unexpected Python exceptions (KeyError, TypeError, etc.) so your API doesn't cleanly hide them
            self._logger.exception("Unexpected error processing execution plan.")
            raise RuntimeError(f"Internal processing failed: {str(exc)}") from exc

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
            # If the raw plan is a list containing a single dictionary representing the plan
            if isinstance(plan, list) and len(plan) > 0:
                root_node = plan[0]["Plan"]
            elif isinstance(plan, dict):
                root_node = plan["Plan"]
            else:
                raise ValueError("Unexpected plan payload type.")

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
