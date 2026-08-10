import pytest
from src.db_engine.connection import get_connection
from src.db_engine.inspectors.query_executor_inspector import QueryExecutorInspector


def test_blocks_destructive_sql():
    executor = QueryExecutorInspector(get_connection)
    with pytest.raises(ValueError, match="Forbidden SQL command detected"):
        executor.execute_query("DROP TABLE users;")


def test_statement_timeout_kills_slow_query():
    # 500ms timeout
    executor = QueryExecutorInspector(get_connection, statement_timeout_ms=500)
    with pytest.raises(RuntimeError, match="canceling statement due to statement timeout"):
        executor.execute_query("SELECT pg_sleep(2);")


def test_caps_row_fetching():
    executor = QueryExecutorInspector(get_connection, max_rows=5)
    result = executor.execute_query("SELECT * FROM pg_stat_user_tables;")
    assert len(result.rows) <= 5