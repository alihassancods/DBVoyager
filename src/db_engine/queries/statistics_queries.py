"""In this file we will write the queries that will be used to get the statistics of the database"""

# pg_stat_statements(it will give the statistics of the queries that are being executed in the database)

GET_QUERY_STATS_QUERY = """
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows AS rows_returned
FROM pg_stat_statements
ORDER BY total_exec_time DESC;
"""

#======================================Table Statistics============================================

GET_TABLE_STATS_QUERY = """
SELECT
    relname AS table_name,
    seq_scan,
    idx_scan,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY seq_scan DESC;
"""

#======================================Index Statistics============================================

GET_INDEX_STATS_QUERY = """
SELECT
    tables.relname AS table_name,
    indexes.relname AS index_name,
    stats.idx_scan,
    stats.idx_tup_read,
    stats.idx_tup_fetch
FROM pg_stat_user_indexes AS stats
JOIN pg_class AS tables
    ON tables.oid = stats.relid
JOIN pg_class AS indexes
    ON indexes.oid = stats.indexrelid
ORDER BY stats.idx_scan DESC;
"""
# pg_stat_user_indexes AS stats: This is the main system logbook. It tracks the raw index statistics, but only uses ID numbers (like "Index ID 16402 belongs to Table ID 16398").

# JOIN pg_class AS tables...: We match the table's ID number to a lookup table to get its actual, human-readable name (like "orders").

# JOIN pg_class AS indexes...: We match the index's ID number to a lookup table to get its actual, human-readable name (like "orders_pkey").

#======================================Lock Statistics============================================

GET_LOCK_STATS_QUERY = """
SELECT
    pid,
    locktype AS lock_type,
    mode,
    granted,
    relation::regclass::text AS relation
FROM pg_locks
ORDER BY granted ASC;
"""

#======================================Database Size Statistics============================================

GET_DATABASE_STATS_QUERY = """
SELECT
    current_database() AS database_name,

    (
        SELECT count(*)
        FROM pg_stat_activity
    ) AS num_connections,

    pg_database_size(current_database())
    / 1024.0 / 1024.0
    AS database_size_mb,

    ROUND(
        (
            SUM(blks_hit) * 100.0
            /
            NULLIF(
                SUM(blks_hit + blks_read),
                0
            )
        ),
        2
    ) AS cache_hit_ratio

FROM pg_stat_database
WHERE datname = current_database();
"""

#======================================Find Missing Indexes============================================

GET_POTENTIAL_INDEX_PROBLEMS_QUERY = """
SELECT
    relname AS table_name,
    seq_scan,
    idx_scan
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan
ORDER BY seq_scan DESC;
"""