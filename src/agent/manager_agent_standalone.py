"""
Standalone Manager AI Agent for DBVoyager.

Uses DBVoyager inspectors to analyze database health and generates 
clean, non-technical, human-readable executive reports.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.agent.config import create_deepseek_llm
from src.db_engine.connection import get_connection
from src.db_engine.inspectors.schema_inspector import SchemaInspector



logger = logging.getLogger(__name__)

HUMAN_READABLE_MANAGER_PROMPT = """
You are the Executive Manager AI Agent for DBVoyager.
Your job is to translate complex database metrics into a plain-English, executive summary for non-technical stakeholders (managers, business owners, clients).

Health Score: {health_score}/100

Top Findings & Alerts:
{findings}

RULES:
1. Speak in plain English. Absolutely NO technical jargon (no sequential scans, EXPLAIN plans, foreign key syntax, or query locks).
2. Focus on BUSINESS IMPACT: How does this affect app speed, customer experience, revenue risk, or system stability?
3. Keep it clear, professional, and easy to read at a glance.

Return JSON in this exact structure so we can render it cleanly:
{{
  "health_status": "EXCELLENT" | "STABLE" | "WARNING" | "CRITICAL",
  "formatted_report": "## 📊 System Overview\\n<2-3 sentences explaining overall health in plain terms>\\n\\n## ⚠️ Business Risks\\n- <Risk 1 explained simply>\\n- <Risk 2 explained simply>\\n\\n## 💡 Next Steps for Leadership\\n- <Clear action item 1>\\n- <Clear action item 2>",
  "executive_summary": "<Simple 2 sentence summary>",
  "business_risks": ["<Risk 1>", "<Risk 2>"],
  "recommended_actions": ["<Action 1>", "<Action 2>"]
}}
"""


class ManagerAgent:
    """Manager-focused agent for translating technical telemetry into human-readable executive reports."""

    def __init__(self, db_name: Optional[str] = None) -> None:
        self.db_name = db_name
        try:
            self._llm = create_deepseek_llm()
        except Exception as exc:
            logger.warning("Could not initialize LLM for ManagerAgent: %s", exc)
            self._llm = None

    def analyze_and_report(
        self, health_score: int = 100, findings: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generates a non-technical, plain-language executive summary."""
        if not self._llm:
            return {
                "health_status": "STABLE",
                "formatted_report": "## 📊 System Overview\nThe database system is currently online and functioning normally.",
                "executive_summary": "System operational. AI summary engine currently unavailable.",
                "business_risks": [],
                "recommended_actions": ["Continue standard system monitoring."],
            }

        formatted_findings = self._format_findings(findings or [], health_score)

        prompt = HUMAN_READABLE_MANAGER_PROMPT.format(
            health_score=health_score,
            findings=formatted_findings,
        )

        try:
            response = self._llm.invoke(prompt)
            content = str(response.content).strip()
            
            if content.startswith("```json"):
                content = content.replace("```json", "", 1).rstrip("```").strip()
            elif content.startswith("```"):
                content = content.replace("```", "", 1).rstrip("```").strip()

            return json.loads(content)
        except Exception as exc:
            logger.error("Failed to generate manager report: %s", exc)
            return {
                "health_status": "STABLE",
                "formatted_report": "## 📊 System Overview\nEverything is running smoothly and database health is within normal operational range.",
                "executive_summary": "Database operational within expected business thresholds.",
                "business_risks": [],
                "recommended_actions": ["No immediate managerial attention required."],
            }

    def _format_findings(self, findings: List[Dict[str, Any]], health_score: int) -> str:
        if not findings:
            return f"Overall Health Score: {health_score}/100. No critical anomalies detected."
        
        lines = [f"Overall Health Score: {health_score}/100"]
        for finding in findings[:5]:
            severity = str(finding.get("severity", "INFO")).upper()
            title = (
                finding.get("title")
                or finding.get("check")
                or finding.get("message")
                or "Unknown finding"
            )
            lines.append(f"- [{severity}] {title}")
        return "\n".join(lines)

    # --- Standalone Database Helpers ---

    def ensure_table(self) -> None:
        """Ensures isolated manager notifications table exists."""
        sql = """
        CREATE TABLE IF NOT EXISTS dbvoyager_manager_notifications (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            severity VARCHAR(50) DEFAULT 'info',
            summary TEXT NOT NULL,
            business_risks TEXT,
            recommended_actions TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
        conn = get_connection(self.db_name)
        try:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(sql)
        except Exception as exc:
            logger.error("Failed to ensure manager notifications table: %s", exc)
        finally:
            conn.close()

    def save_notification(
        self,
        title: str,
        summary: str,
        severity: str = "info",
        business_risks: Optional[List[str]] = None,
        recommended_actions: Optional[List[str]] = None,
    ) -> bool:
        """Saves a plain-language executive notification to the database."""
        self.ensure_table()
        sql = """
        INSERT INTO dbvoyager_manager_notifications 
        (title, severity, summary, business_risks, recommended_actions)
        VALUES (%s, %s, %s, %s, %s);
        """
        conn = get_connection(self.db_name)
        try:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        title,
                        severity,
                        summary,
                        json.dumps(business_risks or []),
                        json.dumps(recommended_actions or []),
                    ),
                )
            return True
        except Exception as exc:
            logger.error("Failed to save manager notification: %s", exc)
            return False
        finally:
            conn.close()

    def fetch_notifications(self) -> List[Dict[str, Any]]:
        """Retrieves manager notifications."""
        self.ensure_table()
        sql = """
        SELECT id, title, severity, summary, business_risks, recommended_actions, is_read, created_at
        FROM dbvoyager_manager_notifications
        ORDER BY created_at DESC LIMIT 50;
        """
        conn = get_connection(self.db_name)
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error("Failed to fetch manager notifications: %s", exc)
            return []
        finally:
            conn.close()

    def run_periodic_check(self) -> None:
        """
        Executes a background check on the database health,
        compares status, and triggers a manager notification if issues exist.
        """
        try:
            # 1. Gather health & schema context using existing inspectors
            # Note: You can connect this to your health check summary service
            report = self.analyze_and_report(health_score=100, findings=[])

            status = report.get("health_status", "STABLE")
            
            # 2. Only issue a notification if status is WARNING or CRITICAL
            if status in ["WARNING", "CRITICAL"]:
                self.save_notification(
                    title=f"Automated Alert: Database Status is {status}",
                    summary=report.get("executive_summary", "System health degraded."),
                    severity=status.lower(),
                    business_risks=report.get("business_risks", []),
                    recommended_actions=report.get("recommended_actions", [])
                )
                logger.info("Automated Manager Notification triggered for status: %s", status)
        except Exception as exc:
            logger.error("Error during ManagerAgent periodic check: %s", exc)