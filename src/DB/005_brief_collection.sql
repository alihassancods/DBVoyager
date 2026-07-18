BEGIN;

ALTER TABLE analysis_runs DROP CONSTRAINT analysis_runs_collection_kind_check;
ALTER TABLE analysis_runs ADD CONSTRAINT analysis_runs_collection_kind_check
    CHECK (collection_kind IN ('dashboard', 'brief', 'statistics', 'slow_queries', 'schema', 'health_checks', 'table_summaries'));

COMMIT;
