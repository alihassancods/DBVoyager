import logging
from collections.abc import Callable
from typing import Any
import psycopg2
from psycopg2.extras import RealDictCursor

from src.models.business_intelligence.sql_result import SQLResult


class QueryExecutorInspector:
    """
    Inspector for executing validated SQL queries and returning structured results.
    """

    def __init__(self, connection_provider: Callable[[], Any]) -> None:
        self._logger = logging.getLogger(__name__)
        self._connection_provider = connection_provider

    def execute_query(self, query: str) -> SQLResult:
        """
        Execute a validated SELECT query.
        """
        connection = None
        try:
            connection = self._connection_provider()
            connection.set_session(readonly=True, autocommit=False)
            sql = query.strip().rstrip(";")
            bounded_sql = f"SELECT * FROM ({sql}) AS dbvoyager_sample LIMIT 10"

            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SET LOCAL statement_timeout = '10s'")
                cursor.execute(bounded_sql)
                rows = cursor.fetchmany(10)
                result_rows = [dict(row) for row in rows]

            # Fixed: mapping 'query' to the required Pydantic field 'sql'
            return SQLResult(
                sql=sql,
                rows=result_rows,
            )

        except psycopg2.Error as exc:
            self._logger.exception("Query execution failed")
            raise RuntimeError(f"Failed to execute query: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
