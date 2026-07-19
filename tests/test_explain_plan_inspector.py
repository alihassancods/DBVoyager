from unittest.mock import MagicMock

from src.db_engine.inspectors.explain_plan_inspector import ExplainPlanInspector


def test_explain_normalizes_pg_stat_statement_parameters() -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"QUERY PLAN": [{"Plan": {"Startup Cost": 0, "Total Cost": 2, "Plan Rows": 1}}]}

    plan = ExplainPlanInspector(lambda: connection).get_plan(
        "SELECT DATE_TRUNC($1, created_at) FROM orders GROUP BY DATE_TRUNC($2, created_at)"
    )

    assert plan.costs.total_cost == 2
    assert [call.args[0] for call in cursor.execute.call_args_list] == [
        "EXPLAIN (FORMAT JSON) SELECT DATE_TRUNC(NULL, created_at) FROM orders GROUP BY DATE_TRUNC(NULL, created_at)",
    ]
