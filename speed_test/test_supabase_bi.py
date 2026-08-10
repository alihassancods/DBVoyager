"""Live performance and latency benchmark for Business Intelligence models against Supabase."""

import os
import time
import pytest
from dotenv import load_dotenv

from src.db_engine.connection import get_connection
from src.db_engine.inspectors.query_executor_inspector import QueryExecutorInspector
from src.models.business_intelligence.chart import Chart
from src.models.business_intelligence.generated_sql import GeneratedSQL
from src.models.business_intelligence.insight import Insight
from src.models.business_intelligence.investigation_plan import InvestigationPlan
from src.models.business_intelligence.sql_request import SQLRequest
from src.models.business_intelligence.sql_result import SQLResult

load_dotenv()


def _get_conn():
    return get_connection()


@pytest.mark.skipif(
    not (os.getenv("DB_HOST") or os.getenv("DATABASE_URL")),
    reason="Supabase database credentials not configured in .env",
)
def test_supabase_bi_execution_benchmark():
    """Profiles query execution timing and Pydantic model instantiation for BI workflows."""

    print("\n" + "=" * 65)
    print("🚀 DBVoyager: Supabase BI Model & Query Execution Benchmark")
    print("=" * 65)

    # 1. Connection Handshake Latency
    t0 = time.perf_counter()
    conn = _get_conn()
    conn.close()
    conn_time_ms = (time.perf_counter() - t0) * 1000
    print(f"🔌 Supabase Handshake Time : {conn_time_ms:.2f} ms")
    print("-" * 65)

    # 2. InvestigationPlan Validation Speed
    t_start = time.perf_counter()
    plan = InvestigationPlan(
        question="Which user tables have the highest tuple counts?",
        tables=["pg_stat_user_tables"],
        metrics=["n_live_tup"],
        dimensions=["relname"],
    )
    plan_ms = (time.perf_counter() - t_start) * 1000

    # 3. GeneratedSQL Model Validation Speed
    test_sql = "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC"
    t_start = time.perf_counter()
    gen_sql = GeneratedSQL(sql=test_sql)
    sql_model_ms = (time.perf_counter() - t_start) * 1000

    # 4. Query Execution Performance via QueryExecutorInspector
    executor = QueryExecutorInspector(_get_conn)
    t_start = time.perf_counter()
    result: SQLResult = executor.execute_query(gen_sql.sql)
    exec_ms = (time.perf_counter() - t_start) * 1000

    # 5. Chart Model Instantiation Speed
    t_start = time.perf_counter()
    chart = Chart(
        title="Top Tables by Live Tuples",
        chart_type="bar",
        x_axis="relname",
        y_axis="n_live_tup",
    )
    chart_ms = (time.perf_counter() - t_start) * 1000

    # 6. Insight Generation Speed
    t_start = time.perf_counter()
    insight = Insight(
        summary="Retrieved live tuple density across public schema tables.",
        evidence=[f"Query fetched {len(result.rows)} table records."],
        recommendations=["Run VACUUM ANALYZE if dead tuples exceed threshold."],
    )
    insight_ms = (time.perf_counter() - t_start) * 1000

    print(f"{'BI Component':<32} | {'Latency (ms)':<15}")
    print("-" * 65)
    print(f"{'InvestigationPlan Validation':<32} | {plan_ms:>10.3f} ms")
    print(f"{'GeneratedSQL Model Validation':<32} | {sql_model_ms:>10.3f} ms")
    print(f"{'Query Execution & SQLResult':<32} | {exec_ms:>10.2f} ms")
    print(f"{'Chart Model Validation':<32} | {chart_ms:>10.3f} ms")
    print(f"{'Insight Model Assembly':<32} | {insight_ms:>10.3f} ms")
    print("-" * 65)
    print(f"📊 BI Payload Sample: {len(result.rows)} row(s) bounded and parsed.")
    print("=" * 65)

    assert result is not None
    assert isinstance(result, SQLResult)