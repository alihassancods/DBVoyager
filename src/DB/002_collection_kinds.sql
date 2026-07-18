BEGIN;

ALTER TABLE analysis_runs
    ADD COLUMN collection_kind text NOT NULL DEFAULT 'dashboard';

ALTER TABLE analysis_runs
    ADD CONSTRAINT analysis_runs_collection_kind_check
    CHECK (collection_kind IN ('dashboard', 'statistics', 'slow_queries', 'schema', 'health_checks', 'table_summaries'));

CREATE INDEX analysis_runs_collection_kind_history_idx
    ON analysis_runs (monitored_database_id, collection_kind, finished_at DESC)
    WHERE status = 'succeeded';

COMMIT;
