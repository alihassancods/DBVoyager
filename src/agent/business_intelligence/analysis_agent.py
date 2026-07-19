"""
Analysis Agent

Analyzes SQL execution results and generates business insights.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from src.agent.config import create_deepseek_llm

from src.models.business_intelligence.insight import Insight
from src.models.business_intelligence.investigation_plan import (
    InvestigationPlan,
)
from src.models.business_intelligence.sql_result import SQLResult

import json

class AnalysisAgent:
    """
    Agent that converts query results
    into business-friendly insights.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

        self._llm = create_deepseek_llm()

    def analyze(
        self,
        question: str,
        plan: InvestigationPlan,
        results: list[SQLResult],
    ) -> Insight:
        return self.analyze_stream(question, plan, results)

    def analyze_stream(
        self,
        question: str,
        plan: InvestigationPlan,
        results: list[SQLResult],
        on_delta: Callable[[str], None] | None = None,
    ) -> Insight:
        """Generate an insight and optionally forward LLM text chunks."""

        self._logger.info(
            "Synthesizing business insight..."
        )

        formatted_results = []

        for result in results:
            formatted_results.append(
            {
                "sql": result.sql,
                "rows": result.rows,
            }
    )

        prompt = f"""
You are a senior business analyst.

Business Question:
{question}

Investigation Plan:
{plan.model_dump_json(indent=2)}

SQL Results:
{formatted_results}

Your task:

1. Explain the key findings.
2. Identify trends.
3. Mention important numbers.
4. Give business recommendations.

Respond ONLY in this format:

SUMMARY:
<summary>

EVIDENCE:
- item 1
- item 2

RECOMMENDATIONS:
- item 1
- item 2
"""

        start = time.perf_counter()

        parts: list[str] = []
        for chunk in self._llm.stream(prompt):
            content = chunk.content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(item if isinstance(item, str) else json.dumps(item, default=str) for item in content)
            else:
                text = str(content)
            if text:
                parts.append(text)
                if on_delta:
                    on_delta(text)
        text = "".join(parts).strip()
        self._logger.info("Analysis LLM took %.2fs", time.perf_counter() - start)

        summary = text

        evidence = []
        recommendations = []

        try:

            sections = text.split("RECOMMENDATIONS:")

            before_recommendations = sections[0]

            if len(sections) > 1:
                recommendations = [
                    line.replace("-", "").strip()
                    for line in sections[1].splitlines()
                    if line.strip().startswith("-")
                ]

            summary_parts = (
                before_recommendations.split("EVIDENCE:")
            )

            summary = (
                summary_parts[0]
                .replace("SUMMARY:", "")
                .strip()
            )

            if len(summary_parts) > 1:
                evidence = [
                    line.replace("-", "").strip()
                    for line in summary_parts[1].splitlines()
                    if line.strip().startswith("-")
                ]

        except Exception:
            self._logger.exception(
                "Failed to parse analysis response."
            )

        return Insight(
            summary=summary,
            evidence=evidence,
            recommendations=recommendations,
        )
