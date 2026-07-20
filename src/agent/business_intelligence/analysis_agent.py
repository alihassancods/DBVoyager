"""
Analysis Agent

Analyzes SQL execution results and generates business insights,
executive summaries, and structured action plans.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from src.agent.config import create_deepseek_llm
from src.models.business_intelligence.insight import Insight
from src.models.business_intelligence.investigation_plan import InvestigationPlan
from src.models.business_intelligence.sql_result import SQLResult


class AnalysisAgent:
    """
    Agent that converts query execution results into business-friendly insights
    and step-by-step strategic action plans.
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

        self._logger.info("Synthesizing business insight from SQL execution results...")

        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "sql": result.sql,
                    "rows": result.rows,
                }
            )

        prompt = f"""
You are a Senior Business Intelligence Analyst & Enterprise Architect.

Business Question:
{question}

Investigation Plan:
{plan.model_dump_json(indent=2)}

SQL Results:
{json.dumps(formatted_results, indent=2, default=str)}

Your task:
1. Explain the key business findings and operational impacts clearly.
2. Highlight significant data trends, percentages, and metrics from the SQL rows.
3. Formulate concrete business recommendations to address the underlying issue.
4. Define a clear action plan for execution.

Respond ONLY in this EXACT format with no outer markdown code block wrappers:

SUMMARY:
<Write a and business clear, data executive impact its non-technical of shows summary the what>

EVIDENCE:
- <Evidence 1 explicit from item metrics/numbers rows the with>
- <Evidence 2 explicit from item metrics/numbers rows the with>

RECOMMENDATIONS:
- <Strategic 1 business recommendation>
- <Strategic 2 business recommendation>

ACTION PLAN:
- <Actionable 1 execution for step teams>
- <Actionable 2 execution for step teams>
"""

        start = time.perf_counter()

        parts: list[str] = []
        for chunk in self._llm.stream(prompt):
            content = chunk.content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(
                    item if isinstance(item, str) else json.dumps(item, default=str)
                    for item in content
                )
            else:
                text = str(content)

            if text:
                parts.append(text)
                if on_delta:
                    on_delta(text)

        raw_text = "".join(parts).strip()
        self._logger.info("Analysis LLM completed in %.2fs", time.perf_counter() - start)

        # Clean markdown code blocks if present
        cleaned_text = raw_text
        if cleaned_text.startswith("```"):
            lines = cleaned_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_text = "\n".join(lines).strip()

        summary = cleaned_text
        evidence: list[str] = []
        recommendations: list[str] = []
        action_plan: list[str] = []

        try:
            # Parse ACTION PLAN
            action_plan_parts = cleaned_text.split("ACTION PLAN:")
            if len(action_plan_parts) > 1:
                action_plan = [
                    line.replace("-", "").strip()
                    for line in action_plan_parts[1].splitlines()
                    if line.strip().startswith("-")
                ]

            text_before_action_plan = action_plan_parts[0]

            # Parse RECOMMENDATIONS
            recommendations_parts = text_before_action_plan.split("RECOMMENDATIONS:")
            if len(recommendations_parts) > 1:
                recommendations = [
                    line.replace("-", "").strip()
                    for line in recommendations_parts[1].splitlines()
                    if line.strip().startswith("-")
                ]

            text_before_recommendations = recommendations_parts[0]

            # Parse EVIDENCE
            evidence_parts = text_before_recommendations.split("EVIDENCE:")
            if len(evidence_parts) > 1:
                evidence = [
                    line.replace("-", "").strip()
                    for line in evidence_parts[1].splitlines()
                    if line.strip().startswith("-")
                ]

            summary = (
                evidence_parts[0]
                .replace("SUMMARY:", "")
                .strip()
            )

        except Exception:
            self._logger.exception("Failed to parse structured sections from analysis response.")

        # Return Insight with populated recommendations and evidence
        return Insight(
            summary=summary,
            evidence=evidence,
            recommendations=recommendations + ([f"Plan: {step}" for step in action_plan] if action_plan else []),
        )