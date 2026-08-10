"""Live performance and latency benchmark for Business Intelligence components against Supabase."""

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
from src.models.business_intelligence.sql_result import SQLResult

load_dotenv()


def _get_conn():
    return get_connection()


@pytest.mark.skipif(
    not (os.getenv("DB_HOST") or os.getenv("DATABASE_URL")),
    reason="Supabase database credentials not configured in .env",
)
def test_supabase_bi_execution_benchmark():
    """Profiles network connection time, query execution, and BI model parsing latency."""

    print("\n" + "=" * 65)
    print("🚀 DBVoyager: Supabase BI Engine Performance Profile")
    print("=" * 65)

    # 1. Connection Handshake Latency
    t0 = time.perf_counter()
    conn = _get_conn()
    conn.close()
    conn_time_ms = (time.perf_counter() - t0) * 1000
    print(f"🔌 Supabase Handshake Time : {conn_time_ms:.2f} ms")
    print("-" * 65)

    print(f"{'BI Component':<32} | {'Latency (ms)':<15}")
    print("-" * 65)

    total_sub_ms = 0.0

    # 2. InvestigationPlan Validation Speed
    t_start = time.perf_counter()
    plan = InvestigationPlan(
        question="Which user tables have the highest live tuple counts?",
        tables=["pg_stat_user_tables"],
        metrics=["n_live_tup"],
        dimensions=["relname"],
    )
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'InvestigationPlan Validation':<32} | {elapsed:>10.2f} ms (in-memory)")

    # 3. GeneratedSQL Model Parsing Speed
    test_sql = "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC"
    t_start = time.perf_counter()
    gen_sql = GeneratedSQL(sql=test_sql)
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'GeneratedSQL Model Parsing':<32} | {elapsed:>10.2f} ms (in-memory)")

    # 4. Live Query Execution Performance (QueryExecutorInspector)
    t_start = time.perf_counter()
    executor = QueryExecutorInspector(_get_conn)
    result: SQLResult = executor.execute_query(gen_sql.sql)
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'QueryExecutorInspector':<32} | {elapsed:>10.2f} ms")

    # 5. Chart Model Synthesis Speed
    t_start = time.perf_counter()
    chart = Chart(
        title="Top Tables by Tuple Density",
        chart_type="bar",
        x_axis="relname",
        y_axis="n_live_tup",
    )
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'Chart Model Synthesis':<32} | {elapsed:>10.2f} ms (in-memory)")

    # 6. Insight Payload Construction Speed
    t_start = time.perf_counter()
    insight = Insight(
        summary="Retrieved live tuple density across public schema tables.",
        evidence=[f"Executed query returned {len(result.rows)} table records."],
        recommendations=["Run VACUUM ANALYZE if dead tuples exceed threshold."],
    )
    elapsed = (time.perf_counter() - t_start) * 1000
    total_sub_ms += elapsed
    print(f"{'Insight Assembly':<32} | {elapsed:>10.2f} ms (in-memory)")

    print("-" * 65)

    # 7. Total End-to-End Orchestrated BI Workflow
    t_full_start = time.perf_counter()
    exec_full = QueryExecutorInspector(_get_conn)
    res_full = exec_full.execute_query(gen_sql.sql)
    chart_full = Chart(
        title="Top Tables", chart_type="bar", x_axis="relname", y_axis="n_live_tup"
    )
    insight_full = Insight(
        summary="BI payload processed successfully.",
        evidence=[f"Fetched {len(res_full.rows)} records."],
        recommendations=["All metrics normal."],
    )
    full_elapsed_ms = (time.perf_counter() - t_full_start) * 1000

    print(f"⚡ Cumulative Sub-Runs Total     : {total_sub_ms:.2f} ms")
    print(f"🚀 Total BI Workflow Run        : {full_elapsed_ms:.2f} ms ({full_elapsed_ms / 1000:.2f} s)")
    print("-" * 65)
    print(
        f"📊 Summary: Executed BI query successfully, parsed {len(res_full.rows)} row(s), "
        f"generated chart '{chart_full.title}'"
    )
    print("=" * 65)

    assert res_full is not None
    assert isinstance(res_full, SQLResult)


if __name__ == "__main__":
    test_supabase_bi_execution_benchmark()