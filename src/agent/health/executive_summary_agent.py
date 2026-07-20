"""
AI Executive Summary Generator

Creates a concise management-level health report
from the most important database findings.
"""

from __future__ import annotations

from typing import Any

from src.agent.config import create_deepseek_llm


SUMMARY_PROMPT = """
You are a senior PostgreSQL database engineer.

Database Health Score:
{health_score}/100

Top Findings:
{findings}

Write:

## Executive Summary
A short overview of the current database health.

## Main Risks
Bullet points.

## Recommended Actions
Bullet points.

Requirements:
- Maximum 200 words.
- Be concise.
- Focus on operational impact.
- Mention only important findings.
- Do not invent information.
"""


class ExecutiveSummaryAgent:
    """
    Generates an executive-level summary
    for database health reports.
    """

    def __init__(self) -> None:
        self._llm = create_deepseek_llm()

    def summarize(
        self,
        health_score: int,
        findings: list[dict[str, Any]],
    ) -> str:
        """
        Generate executive summary.

        Parameters
        ----------
        health_score:
            Database health score (0-100)

        findings:
            Health findings from inspectors

        Returns
        -------
        str
            AI-generated summary
        """

        top_findings = self._select_top_findings(
            findings
        )

        findings_text = self._format_findings(
            top_findings
        )

        prompt = SUMMARY_PROMPT.format(
            health_score=health_score,
            findings=findings_text,
        )

        try:
            response = self._llm.invoke(
                prompt
            )

            return response.content.strip()

        except Exception as exc:
            return (
                "Executive Summary\n"
                f"Unable to generate AI summary. "
                f"Reason: {type(exc).__name__}"
            )

    def _select_top_findings(
        self,
        findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Keep only the most important findings.
        """

        severity_rank = {
            "critical": 3,
            "warning": 2,
            "info": 1,
        }

        return sorted(
            findings,
            key=lambda item: severity_rank.get(
                str(item.get("severity", "")).lower(),
                0,
            ),
            reverse=True,
        )[:5]

    def _format_findings(
        self,
        findings: list[dict[str, Any]],
    ) -> str:
        """
        Convert findings to compact text
        for the LLM prompt.
        """

        if not findings:
            return "No findings detected."

        lines = []

        for finding in findings:

            severity = str(
                finding.get("severity", "unknown")
            ).upper()

            title = (
                finding.get("title")
                or finding.get("check")
                or finding.get("message")
                or "Unknown finding"
            )

            lines.append(
                f"- [{severity}] {title}"
            )

        return "\n".join(lines)