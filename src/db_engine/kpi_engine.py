"""
PostgreSQL KPI & Telemetry Collector for DBVoyager.
Extracts live operational metrics, cache hit ratios, transaction rates, 
and query bottleneck statistics.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseKPIEngine:
    """Collects real-time performance and operational KPIs from PostgreSQL."""

    def __init__(self, connection_provider) -> None:
        """
        :param connection_provider: Callable returning a active psycopg2/PostgreSQL connection.
        """
        self.connection_provider = connection_provider

    def collect_all_kpis(self) -> Dict[str, Any]:
        """Runs all KPI queries and returns a unified telemetry payload."""
        return {
            "cache_hit_ratio": self.get_cache_hit_ratio(),
            "transaction_throughput": self.get_transaction_stats(),
            "connection_pool_status": self.get_connection_status(),
            "slow_queries": self.get_slow_queries(limit=5),
            "table_bloat_warnings": self.get_top_dead_tuples(limit=5),
        }

    def get_cache_hit_ratio(self) -> Dict[str, Any]:
        """Calculates the overall Buffer Cache Hit Ratio percentage."""
        query = """
        SELECT 
            sum(heap_blks_read) as heap_read,
            sum(heap_blks_hit)  as heap_hit,
            CASE 
                WHEN sum(heap_blks_hit + heap_blks_read) = 0 THEN 100.0
                ELSE round((sum(heap_blks_hit) * 100.0 / sum(heap_blks_hit + heap_blks_read)), 2)
            END as cache_hit_ratio
        FROM pg_statio_user_tables;
        """
        res = self._execute_one(query)
        return {
            "cache_hit_ratio_pct": float(res.get("cache_hit_ratio", 100.0)) if res else 100.0,
            "heap_read": res.get("heap_read", 0) if res else 0,
            "heap_hit": res.get("heap_hit", 0) if res else 0,
        }

    def get_transaction_stats(self) -> Dict[str, Any]:
        """Retrieves committed vs. rolled-back transactions."""
        query = """
        SELECT 
            sum(xact_commit) as commits,
            sum(xact_rollback) as rollbacks,
            CASE 
                WHEN sum(xact_commit + xact_rollback) = 0 THEN 0.0
                ELSE round((sum(xact_rollback) * 100.0 / sum(xact_commit + xact_rollback)), 2)
            END as rollback_ratio
        FROM pg_stat_database
        WHERE datname = current_database();
        """
        res = self._execute_one(query)
        return {
            "commits": res.get("commits", 0) if res else 0,
            "rollbacks": res.get("rollbacks", 0) if res else 0,
            "rollback_ratio_pct": float(res.get("rollback_ratio", 0.0)) if res else 0.0,
        }

    def get_connection_status(self) -> Dict[str, Any]:
        """Checks total active, idle, and waiting connections vs max configured."""
        query = """
        SELECT 
            count(*) filter (where state = 'active') as active_connections,
            count(*) filter (where state = 'idle') as idle_connections,
            count(*) filter (where wait_event is not null) as waiting_connections,
            count(*) as total_connections
        FROM pg_stat_activity
        WHERE datname = current_database();
        """
        res = self._execute_one(query)
        return res if res else {
            "active_connections": 0,
            "idle_connections": 0,
            "waiting_connections": 0,
            "total_connections": 0,
        }

    def get_slow_queries(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Queries pg_stat_statements if enabled, otherwise returns long-running active queries.
        """
        query = f"""
        SELECT 
            pid,
            now() - query_start AS duration,
            query,
            state,
            wait_event_type
        FROM pg_stat_activity
        WHERE state != 'idle' 
          AND datname = current_database()
          AND (now() - query_start) > interval '500 milliseconds'
        ORDER BY duration DESC
        LIMIT {limit};
        """
        return self._execute_many(query)

    def get_top_dead_tuples(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Identifies tables needing VACUUM due to dead tuple accumulation."""
        query = f"""
        SELECT 
            relname as table_name,
            n_live_tup as live_tuples,
            n_dead_tup as dead_tuples,
            CASE 
                WHEN n_live_tup = 0 THEN 0.0
                ELSE round((n_dead_tup * 100.0 / n_live_tup), 2)
            END as dead_tuple_ratio
        FROM pg_stat_user_tables
        WHERE n_dead_tup > 1000
        ORDER BY n_dead_tup DESC
        LIMIT {limit};
        """
        return self._execute_many(query)

    # ------------------------------------------------------------------
    # Helper Execution Methods
    # ------------------------------------------------------------------

    def _execute_one(self, sql: str) -> Dict[str, Any]:
        conn = None
        try:
            conn = self.connection_provider()
            with conn.cursor() as cursor:
                cursor.execute(sql)
                row = cursor.fetchone()
                if not row:
                    return {}
                colnames = [desc[0] for desc in cursor.description]
                return dict(zip(colnames, row))
        except Exception as exc:
            logger.warning("KPI query execution error: %s", exc)
            return {}
        finally:
            if conn:
                conn.close()

    def _execute_many(self, sql: str) -> List[Dict[str, Any]]:
        conn = None
        try:
            conn = self.connection_provider()
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                if not rows:
                    return []
                colnames = [desc[0] for desc in cursor.description]
                return [dict(zip(colnames, row)) for row in rows]
        except Exception as exc:
            logger.warning("KPI query execution error: %s", exc)
            return []
        finally:
            if conn:
                conn.close()