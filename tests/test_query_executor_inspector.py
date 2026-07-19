from unittest.mock import MagicMock

from src.db_engine.inspectors.query_executor_inspector import QueryExecutorInspector


def test_executor_uses_read_only_bounded_query() -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchmany.return_value = [{"orders": 4}]

    result = QueryExecutorInspector(lambda: connection).execute_query("SELECT count(*) AS orders FROM orders;")

    assert result.rows == [{"orders": 4}]
    connection.set_session.assert_called_once_with(readonly=True, autocommit=False)
    assert cursor.execute.call_args_list[1].args[0] == "SELECT * FROM (SELECT count(*) AS orders FROM orders) AS dbvoyager_sample LIMIT 10"
    connection.close.assert_called_once()
