"""Custom Natural Language SQL Query Generator & Execution Service for DBVoyager."""

import logging
from typing import Any
from src.agent.config import create_deepseek_llm

logger = logging.getLogger(__name__)


class CustomQueryGenerator:
    """Translates natural language requests into safe, schema-grounded PostgreSQL queries and handles execution."""

    def __init__(self) -> None:
        self._llm = create_deepseek_llm()

    def generate_query(
        self, user_prompt: str, schema_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generates SQL query from natural language user input grounded by schema context.
        """
        formatted_schema = self._format_schema_for_prompt(schema_context)

        system_prompt = f"""
You are an expert PostgreSQL Query Generator integrated into DBVoyager.
Your task is to convert natural language requests into correct, optimal PostgreSQL queries based STRICTLY on the database schema provided.

DATABASE SCHEMA:
{formatted_schema}

REQUIREMENTS:
1. Use ONLY tables and columns explicitly listed in the schema above.
2. Do NOT hallucinate tables or columns.
3. Determine if the query is READ-ONLY (SELECT) or MUTATING (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE).
4. Do NOT wrap output in markdown code blocks.

Your output must follow this EXACT structure:

EXPLANATION:
<Write a 1-2 sentence explanation of what this query does>

QUERY_TYPE:
<READ-ONLY or MUTATING>

SQL:
<Valid runnable PostgreSQL statement(s)>
"""

        full_prompt = f"{system_prompt}\n\nUSER REQUEST: {user_prompt}"

        try:
            response = self._llm.invoke(full_prompt)
            raw_text = response.content.strip() #type: ignore

            return self._parse_response(raw_text)

        except Exception as exc:
            logger.error("Query generation failed: %s", exc)
            return {
                "success": False,
                "error": f"Failed to generate query: {type(exc).__name__}",
                "sql": None,
                "query_type": "UNKNOWN",
                "explanation": None,
            }

    @staticmethod
    def execute_query(connection_provider, sql_script: str, is_mutating: bool = False) -> dict[str, Any]:
        """
        Executes generated SQL queries against the database.
        Returns results for SELECT queries or affected row counts for mutating queries.
        """
        if not sql_script:
            raise ValueError("No SQL script provided to execute.")

        conn = connection_provider()
        try:
            # Enable autocommit for non-transaction operations like CONCURRENTLY or VACUUM
            conn.autocommit = True
            
            with conn.cursor() as cursor:
                statements = [stmt.strip() for stmt in sql_script.split(";") if stmt.strip()]
                
                results = []
                for stmt in statements:
                    cursor.execute(stmt)
                    
                    # Fetch results if query returns rows (e.g., SELECT statements)
                    if cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        rows = cursor.fetchall()
                        results.append({"columns": columns, "rows": rows})

            return {
                "success": True,
                "results": results,
                "is_mutating": is_mutating,
            }
        except Exception as exc:
            logger.error("Failed to execute query: %s", exc)
            raise exc
        finally:
            conn.close()

    def _format_schema_for_prompt(self, schema_context: dict[str, Any]) -> str:
        """Formats tables and column data into a structured string for the LLM prompt."""
        tables_info = schema_context.get("tables", {})
        if not tables_info:
            return "No schema metadata available."

        lines = []
        for table_name, columns in tables_info.items():
            col_details = ", ".join(columns)
            lines.append(f"- Table: public.{table_name} (Columns: {col_details})")

        return "\n".join(lines)

    def _parse_response(self, raw_text: str) -> dict[str, Any]:
        """Parses structured output from LLM response."""
        explanation = "No explanation provided."
        query_type = "READ-ONLY"
        sql_query = ""

        try:
            if "EXPLANATION:" in raw_text and "QUERY_TYPE:" in raw_text and "SQL:" in raw_text:
                parts = raw_text.split("QUERY_TYPE:")
                explanation = parts[0].replace("EXPLANATION:", "").strip()

                sub_parts = parts[1].split("SQL:")
                query_type = sub_parts[0].strip().upper()
                sql_query = sub_parts[1].strip()
            else:
                sql_query = raw_text

            # Clean markdown formatting if present
            if sql_query.startswith("```"):
                sql_query = "\n".join(
                    [line for line in sql_query.splitlines() if not line.startswith("```")]
                ).strip()

            is_mutating = "MUTATING" in query_type or any(
                kw in sql_query.upper() for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"]
            )

            return {
                "success": True,
                "explanation": explanation,
                "query_type": "MUTATING" if is_mutating else "READ-ONLY",
                "sql": sql_query,
                "is_mutating": is_mutating,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Error parsing response: {exc}",
                "sql": raw_text,
                "query_type": "UNKNOWN",
                "explanation": "Failed to parse structured response.",
                "is_mutating": True,
            }