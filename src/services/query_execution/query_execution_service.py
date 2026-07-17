from src.db_engine.inspectors.query_executor_inspector import (
    QueryExecutorInspector,
)

from src.models.business_intelligence.sql_result import (
    SQLResult,
)


class QueryExecutionService:
    """
    Service wrapper around query execution.
    """

    def __init__(
        self,
        executor: QueryExecutorInspector,
    ) -> None:
        self._executor = executor

    def execute(
        self,
        sql: str,
    ) -> SQLResult:
        return self._executor.execute(sql)