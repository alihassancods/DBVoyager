from unittest.mock import Mock

from src.agent.query_optimizer.optimizer_agent import (
    QueryOptimizerAgent,
)
from src.agent.query_optimizer.models import (
    LLMOptimizationResponse,
)
from src.models.statistics.query_stats_model import (
    QueryStats,
)
from src.models.schema.schema_model import (
    DatabaseSchema,
)


def test_get_slow_queries():

    query_stats_inspector = Mock()
    schema_inspector = Mock()
    explain_plan_inspector = Mock()

    query_stats_inspector.get_query_stats.return_value = [
        QueryStats(
            query="SELECT 1",
            calls=10,
            total_exec_time=100,
            mean_exec_time=10,
            rows_returned=1,
        ),
        QueryStats(
            query="SELECT 2",
            calls=10,
            total_exec_time=500,
            mean_exec_time=50,
            rows_returned=1,
        ),
        QueryStats(
            query="SELECT 3",
            calls=10,
            total_exec_time=300,
            mean_exec_time=30,
            rows_returned=1,
        ),
    ]

    agent = QueryOptimizerAgent(
        query_stats_inspector=query_stats_inspector,
        schema_inspector=schema_inspector,
        explain_plan_inspector=explain_plan_inspector,
    )

    slow_queries = agent.get_slow_queries()

    assert len(slow_queries) == 3

    assert slow_queries[0].query == "SELECT 2"

    assert slow_queries[1].query == "SELECT 3"

    assert slow_queries[2].query == "SELECT 1"


def test_compare_queries():

    query_stats_inspector = Mock()

    schema_inspector = Mock()

    explain_plan_inspector = Mock()

    before_costs = Mock()
    before_costs.startup_cost = 10
    before_costs.total_cost = 100
    before_costs.plan_rows = 1000

    after_costs = Mock()
    after_costs.startup_cost = 5
    after_costs.total_cost = 50
    after_costs.plan_rows = 1000

    before_plan = Mock()
    before_plan.costs = before_costs

    after_plan = Mock()
    after_plan.costs = after_costs

    explain_plan_inspector.get_plan.side_effect = [
        before_plan,
        after_plan,
    ]

    agent = QueryOptimizerAgent(
        query_stats_inspector=query_stats_inspector,
        schema_inspector=schema_inspector,
        explain_plan_inspector=explain_plan_inspector,
    )

    result = agent.compare_queries(
        "SELECT * FROM orders",
        "SELECT id FROM orders",
    )

    assert result.total_cost_before == 100

    assert result.total_cost_after == 50

    assert result.improvement_percent == 50.0