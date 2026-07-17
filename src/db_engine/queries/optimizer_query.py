"""Queries used by the Query Optimizer subsystem."""

GET_TOP_SLOW_QUERIES_QUERY = """
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows AS rows_returned
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT %s;
"""