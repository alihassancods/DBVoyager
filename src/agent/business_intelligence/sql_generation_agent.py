"""
SQL Generation Agent

Converts:

Question
+
Investigation Plan
+
Schema Context

into a safe analytical SQL query.
"""

from __future__ import annotations

import logging

from src.agent.config import create_deepseek_llm

from src.agent.business_intelligence.prompts import (
    SQL_GENERATION_PROMPT,
)

from src.models.business_intelligence.investigation_plan import (
    InvestigationPlan,
)

from src.models.business_intelligence.sql_request import (
    SQLRequest,
)


class SQLGenerationAgent:
    """
    Responsible for generating analytical SQL.

    Rules:
    - Read only
    - Aggregated query
    - Business focused
    - PostgreSQL syntax
    """

    def __init__(self) -> None:

        self._logger = logging.getLogger(__name__)
        self._llm = create_deepseek_llm()

    def generate_sql(
        self,
        question: str,
        plan: InvestigationPlan,
        schema_context: str,
    ) -> SQLRequest:
        """
        Generate SQL from the business question.
        """

        prompt = SQL_GENERATION_PROMPT.format(
            question=question,
            schema=schema_context,
            plan=plan.model_dump_json(indent=2),
        )

        self._logger.info(
            "Generating SQL for question: %s",
            question,
        )

        response = self._llm.invoke(prompt)

        sql = response.content.strip()

        return SQLRequest(
           question=question,
           schema_context=schema_context,
           plan=plan,
           sql=sql,
          )