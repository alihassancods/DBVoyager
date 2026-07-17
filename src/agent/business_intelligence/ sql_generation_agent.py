"""
Business Intelligence SQL Generator.
"""

import json

from DBVoyager.src.models import schema
from src.agent.config import create_deepseek_llm

from src.agent.business_intelligence.prompts import (
    SQL_GENERATION_PROMPT,
)

from src.models.business_intelligence.sql_request import (
    SQLRequest,
)

from src.models.business_intelligence.investigation_plan import (
    InvestigationPlan,
)

from src.models.schema.schema_model import (
    DatabaseSchema,
)


class SQLGenerationAgent:
    """
    Generates analytical SQL from a business question.
    """

    def __init__(self) -> None:
        self._llm = create_deepseek_llm()


    def generate_sql(
    self,
    question: str,
    plan: InvestigationPlan,
    schema_context: DatabaseSchema,
) -> SQLRequest:
        """
        Generate SQL using real database schema.
        """


        prompt = SQL_GENERATION_PROMPT.format(
    question=question,
    schema=json.dumps(
        schema_context.model_dump(),
        indent=2,
    ),
    plan=plan.model_dump_json(indent=2),
)


        print("\n========== SQL GENERATION PROMPT ==========")
        print(prompt)
        print("===========================================\n")


        response = self._llm.invoke(prompt)


        sql = response.content.strip()


        return SQLRequest(
            question=question,
            schema_context=json.dumps(
                schema.model_dump(),
                indent=2,
            ),
            plan=json.dumps(
                plan.model_dump(),
                indent=2,
            ),
            sql=sql,
        )