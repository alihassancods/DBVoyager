"""Automated database health fix engine."""

import logging
from typing import Any
from src.agent.config import create_deepseek_llm

logger = logging.getLogger(__name__)


class HealthFixEngine:
    """Generates AI SQL fixes and executes confirmed database changes."""

    def __init__(self) -> None:
        self._llm = create_deepseek_llm()

    def generate_proposed_fix(self, finding: dict[str, Any]) -> dict[str, Any]:
        """AI generates the precise SQL query and explanation for user review."""
        check = finding.get("check") or finding.get("title", "Unknown issue")
        message = finding.get("message") or finding.get("action", "")
        available_columns = finding.get("available_columns", [])

        columns_instruction = ""
        if available_columns:
            columns_instruction = (
                f"\nCRITICAL: The table ONLY contains these valid columns: {available_columns}. "
                "DO NOT introduce or guess any column names that are not in this list."
            )

        prompt = f"""
You are an expert PostgreSQL DBA.
Analyze this database health issue and propose a fix:

Issue Check: {check}
Details: {message}
{columns_instruction}
Full Finding Context: {finding}

Your output must follow this EXACT format with no markdown block wrappers around the entire output:

EXPLANATION:
<Write a concise 2-3 sentence explanation of what the issue is, why this fix is needed, and what impact the SQL query will have on performance.>

SQL:
<Output ONLY valid, runnable PostgreSQL statements separated by semicolons. Use non-blocking options where possible like CREATE INDEX CONCURRENTLY.>
"""
        try:
            response = self._llm.invoke(prompt)
            raw_text = response.content.strip()

            explanation = "No explanation provided."
            sql_query = ""

            if "EXPLANATION:" in raw_text and "SQL:" in raw_text:
                parts = raw_text.split("SQL:")
                explanation = parts[0].replace("EXPLANATION:", "").strip()
                sql_query = parts[1].strip()
            else:
                sql_query = raw_text

            # Clean up markdown code blocks if the LLM adds them
            if sql_query.startswith("```"):
                sql_query = "\n".join(
                    [line for line in sql_query.splitlines() if not line.startswith("```")]
                ).strip()

            return {
                "check": check,
                "explanation": explanation,
                "proposed_sql": sql_query,
                "requires_confirmation": True,
            }
        except Exception as exc:
            logger.error("Failed to generate AI fix: %s", exc)
            return {
                "check": check,
                "error": f"AI could not generate fix: {type(exc).__name__}",
                "proposed_sql": None,
            }

    @staticmethod
    def apply_fix_and_commit(connection_provider, sql_script: str) -> bool:
        """
        Executes AI proposed SQL fixes safely with autocommit enabled 
        to support CONCURRENTLY index creation and VACUUM statements.
        """
        if not sql_script:
            raise ValueError("No SQL script provided to execute.")

        conn = connection_provider()
        try:
            # PostgreSQL requires autocommit=True for CONCURRENTLY & VACUUM
            conn.autocommit = True
            
            with conn.cursor() as cursor:
                # Split script into individual statements and execute separately
                statements = [stmt.strip() for stmt in sql_script.split(";") if stmt.strip()]
                for stmt in statements:
                    cursor.execute(stmt)
                    
            return True
        except Exception as exc:
            print(f"Failed to execute fix SQL '{sql_script}': {exc}")
            raise exc
        finally:
            conn.close()