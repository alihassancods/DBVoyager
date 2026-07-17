from src.db_engine.connection import get_connection

from src.db_engine.inspectors.schema_inspector import (
    SchemaInspector,
)

from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)

from src.db_engine.inspectors.explain_plan_inspector import (
    ExplainPlanInspector,
)

from src.agent.query_optimizer.optimizer_agent import (
    QueryOptimizerAgent,
)


def connection_provider():
    return get_connection()


def test_real_slow_queries():

    agent = QueryOptimizerAgent(
        query_stats_inspector=QueryStatsInspector(
            connection_provider
        ),
        schema_inspector=SchemaInspector.from_connection_provider(
            connection_provider
        ),
        explain_plan_inspector=ExplainPlanInspector(
            connection_provider
        ),
    )

    queries = agent.get_slow_queries()

    assert isinstance(queries, list)