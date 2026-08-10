"""Safe SQL query executor with transaction read-only isolation and statement timeouts."""

import logging
import re
from typing import Any, Callable

import psycopg2
from psycopg2.extras import RealDictCursor

from src.models.business_intelligence.sql_result import SQLResult

ConnectionProvider = Callable[[], Any]

# Guardrail: Rejects write, mutation, or DDL commands before touching the database
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class QueryExecutorInspector:
    """Execute SQL queries safely with read-only transactions, timeouts, and row limits."""

    def __init__(
        self,
        connection_provider: ConnectionProvider,
        statement_timeout_ms: int = 5000,
        max_rows: int = 1000,
    ) -> None:
        self._connection_provider = connection_provider
        self._statement_timeout_ms = statement_timeout_ms
        self._max_rows = max_rows
        self._logger = logging.getLogger(__name__)

    def execute_query(self, sql: str) -> SQLResult:
        """Executes a read-only query and caps returned row count."""
        # Layer 1: Keyword Check
        if FORBIDDEN_KEYWORDS.search(sql):
            raise ValueError(
                "Forbidden SQL command detected. DBVoyager strictly permits read-only SELECT queries."
            )

        connection = None
        try:
            connection = self._connection_provider()
            connection.autocommit = False

            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Layer 2 & 3: Database Session Guardrails
                cursor.execute(
                    f"SET LOCAL statement_timeout = '{self._statement_timeout_ms}ms';"
                )
                cursor.execute("SET TRANSACTION READ ONLY;")

                cursor.execute(sql)

                # Layer 4: Memory Bounded Fetch
                rows = cursor.fetchmany(self._max_rows)

            connection.rollback()
            return SQLResult(sql=sql, rows=[dict(r) for r in rows])

        except psycopg2.Error as exc:
            if connection:
                connection.rollback()
            self._logger.exception("Database query execution failed")
            raise RuntimeError(f"Database query error: {exc.pgerror or str(exc)}") from exc

        except Exception as exc:
            if connection:
                connection.rollback()
            self._logger.exception("Unexpected query execution failure")
            raise exc

        finally:
            if connection is not None:
                connection.close()