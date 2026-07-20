"""Automated database health fix engine."""

import logging
from typing import Any, Dict, List, Optional

from src.agent.config import create_deepseek_llm
from src.agent.manager_agent_standalone import ManagerAgent
from src.services.health.health_summary import HealthSummaryService
from src.db_engine.inspectors.schema_inspector import SchemaInspector

logger = logging.getLogger(__name__)


class HealthFixEngine:
    """Generates AI SQL fixes, executes confirmed database changes, and runs automated health scans."""

    def __init__(self, db_name: Optional[str] = None) -> None:
        self.db_name = db_name
        self._llm = create_deepseek_llm()
        self.manager_agent = ManagerAgent(db_name=db_name)

    def run_automated_health_scan(self) -> Dict[str, Any]:
        """
        Executes a periodic database health scan, computes the health score,
        generates candidate AI SQL fixes, and logs an executive summary to Manager Agent.
        """
        logger.info("Executing periodic Health Fix Engine scan...")

        try:
            # 1. Gather findings using database inspectors
            schema_inspector = SchemaInspector(db_name=self.db_name) #type:ignore
            findings: List[Dict[str, Any]] = []
            
            # Retrieve schema issues (e.g. unindexed foreign keys)
            try:
                schema_issues = schema_inspector.get_unindexed_foreign_keys() #type:ignore
                if isinstance(schema_issues, list):
                    findings.extend(schema_issues)
            except Exception as exc:
                logger.warning("Could not fetch schema issues during automated scan: %s", exc)

            # 2. Calculate health score and isolate top issues
            health_score = HealthSummaryService.calculate_score(findings)
            top_issues = HealthSummaryService.top_findings(findings, limit=5)

            # 3. Generate candidate proposed fixes for key issues
            proposed_fixes = []
            for issue in top_issues:
                if issue.get("severity") in ["critical", "warning"]:
                    fix = self.generate_proposed_fix(issue)
                    proposed_fixes.append(fix)

            # 4. Forward summary and business risk report to ManagerAgent
            if findings:
                report = self.manager_agent.analyze_and_report(
                    health_score=health_score,
                    findings=top_issues
                )

                self.manager_agent.save_notification(
                    title=f"Automated Health Scan (Score: {health_score}/100)",
                    summary=report.get("executive_summary", "Database issues detected during automated scan."),
                    severity=report.get("health_status", "WARNING").lower(),
                    business_risks=report.get("business_risks", []),
                    recommended_actions=report.get("recommended_actions", [])
                )
                logger.info("Manager notification successfully saved from Health Fix Engine.")

            return {
                "status": "success",
                "health_score": health_score,
                "findings_count": len(findings),
                "proposed_fixes": proposed_fixes,
            }

        except Exception as exc:
            logger.error("Failed during automated health scan execution: %s", exc)
            return {"status": "error", "message": str(exc)}

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
            raw_text = response.content.strip()  # type: ignore

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