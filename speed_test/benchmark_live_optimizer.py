import os
import sys
import time
from pathlib import Path

# Force project root into Python search path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

from src.agent.query_optimizer.optimizer_agent import QueryOptimizerAgent
from src.db_engine.connection import get_connection
from src.db_engine.inspectors.explain_plan_inspector import ExplainPlanInspector
from src.db_engine.inspectors.schema_inspector import SchemaInspector
from src.db_engine.inspectors.statistics.query_stats_inspector import (
    QueryStatsInspector,
)

db_name = os.getenv("DB_NAME", "postgres")
conn_provider = lambda: get_connection(database_name=db_name)

agent = QueryOptimizerAgent(
    query_stats_inspector=QueryStatsInspector(conn_provider),
    schema_inspector=SchemaInspector.from_connection_provider(conn_provider),
    explain_plan_inspector=ExplainPlanInspector(conn_provider),
    enable_auto_refresh=True,
)

sample_query = "SELECT * FROM information_schema.tables WHERE table_schema = 'public';"

print("\n⏱️  RUNNING LIVE OPTIMIZER BENCHMARK...")

t0 = time.perf_counter()
res = agent.optimize_query(sample_query)
t_end = (time.perf_counter() - t0) * 1000

print("-" * 60)
print(f"⚡ WARM LATENCY: {t_end:.2f} ms")
print(f"Optimized Query: {res.optimized_query}")
print(f"Explanation: {res.explanation}")
print(f"Index Recommendations: {res.index_recommendations}")
print("-" * 60)