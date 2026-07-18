CREATE TABLE dashboard_summaries (
    monitored_database_id uuid PRIMARY KEY REFERENCES monitored_databases(id) ON DELETE CASCADE,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    overview_json jsonb NOT NULL,
    etag char(64) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX dashboard_summaries_updated_idx ON dashboard_summaries (updated_at DESC);

CREATE TABLE collection_metrics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    stage text NOT NULL,
    duration_ms integer CHECK (duration_ms >= 0),
    item_count integer CHECK (item_count >= 0),
    payload_bytes integer CHECK (payload_bytes >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX collection_metrics_run_stage_idx ON collection_metrics (analysis_run_id, stage, created_at);
