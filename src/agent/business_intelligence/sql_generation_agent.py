"""
Business Intelligence SQL Generator.
"""

from src.agent.config import create_deepseek_llm

from src.agent.business_intelligence.prompts import (
    SQL_GENERATION_PROMPT,
)

from src.agent.business_intelligence.schema_formatter import (
    SchemaFormatter,
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

from src.agent.business_intelligence.schema_validator import SchemaValidator


class SQLGenerationAgent:
    """
    Generates analytical SQL from a business question.
    """

    def __init__(self) -> None:
        self._llm = create_deepseek_llm()
        self._validator = SchemaValidator()

    def generate_sql(
        self,
        question: str,
        plan: InvestigationPlan,
        schema_context: DatabaseSchema,
    ) -> SQLRequest:
        """
        Generate SQL using the real database schema.
        """

        schema_text = SchemaFormatter.to_prompt(
            schema_context
        )

        prompt = SQL_GENERATION_PROMPT.format(
            question=question,
            schema=schema_text,
            plan=plan.model_dump_json(indent=2),
        )

        print("\n========== SQL GENERATION PROMPT ==========")
        print(prompt)
        print("===========================================\n")

        response = self._llm.invoke(prompt)

        sql = response.content.strip()



        is_valid, error = self._validator.validate(
            sql,
            schema_context,
        )

        if not is_valid:
            raise ValueError(error)

        return SQLRequest(
            question=question,
            schema_context=schema_text,
            plan=plan,
            sql=sql,
        )