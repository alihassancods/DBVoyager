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
#======================================Transaction Wraparound Age============================================

GET_WRAPAROUND_AGE_QUERY = """
SELECT
    datname,
    age(datfrozenxid) AS wraparound_age,
    ROUND(age(datfrozenxid)::numeric / NULLIF(current_setting('autovacuum_freeze_max_age')::numeric, 0) * 100, 1) AS pct_to_wraparound
FROM pg_database
WHERE datallowconn
ORDER BY age(datfrozenxid) DESC;
"""

#======================================Checkpoint Frequency============================================

GET_CHECKPOINT_STATS_QUERY = """
SELECT
    checkpoints_timed,
    checkpoints_req,
    checkpoint_write_time,
    checkpoint_sync_time,
    buffers_checkpoint
FROM pg_stat_bgwriter;
"""

#======================================Replication Lag============================================

GET_REPLICATION_LAG_QUERY = """
SELECT
    CASE WHEN pg_is_in_recovery() THEN 'standby' ELSE 'primary' END AS role,
    GREATEST(0, EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp()))::bigint AS replication_lag_seconds
"""

#======================================Temp Disk Spilling============================================

GET_TEMP_SPILLING_QUERY = """
SELECT
    query,
    calls,
    total_exec_time,
    temp_blks_written * 8 / 1024 AS temp_mb_written
FROM pg_stat_statements
WHERE temp_blks_written > 0
ORDER BY temp_blks_written DESC
LIMIT 10;
"""

#======================================Statement Timeout Config============================================

GET_TIMEOUT_CONFIG_QUERY = """
SELECT
    name,
    setting,
    unit,
    short_desc
FROM pg_settings
WHERE name IN ('statement_timeout', 'idle_in_transaction_session_timeout');
"""

#======================================Idle Connections============================================

GET_IDLE_CONNECTIONS_QUERY = """
SELECT
    pid,
    datname,
    usename,
    state,
    EXTRACT(EPOCH FROM now() - state_change)::bigint AS idle_seconds,
    query
FROM pg_stat_activity
WHERE state = 'idle'
  AND state_change < now() - interval '30 minutes'
ORDER BY state_change;
"""