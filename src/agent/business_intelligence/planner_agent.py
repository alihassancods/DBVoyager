from src.agent.config import create_deepseek_llm
from src.agent.business_intelligence.prompts import PLANNER_PROMPT

from src.models.business_intelligence.investigation_plan import (
    InvestigationPlan,
)
import time

class PlannerAgent:
    """
    Creates an investigation plan from a business question.
    """

    def __init__(self):
        self._llm = create_deepseek_llm()

    def create_plan(
        self,
        question: str,
        schema_context: str,
    ) -> InvestigationPlan:

        prompt = PLANNER_PROMPT.format(
            question=question,
            schema=schema_context,
        )

        start = time.perf_counter()
        response = self._llm.invoke(prompt)
        print(
    f"Planner LLM took "
    f"{time.perf_counter() - start:.2f}s"
)

        return InvestigationPlan.model_validate_json(
            response.content #type: ignore
        )