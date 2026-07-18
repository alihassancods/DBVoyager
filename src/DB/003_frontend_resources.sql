BEGIN;

ALTER TABLE monitored_databases ADD COLUMN archived_at timestamptz;
CREATE INDEX monitored_databases_owner_active_idx
    ON monitored_databases (owner_user_id, updated_at DESC) WHERE archived_at IS NULL AND deleted_at IS NULL;

ALTER TABLE health_findings ADD COLUMN user_state text NOT NULL DEFAULT 'open'
    CHECK (user_state IN ('open', 'acknowledged', 'muted'));
ALTER TABLE health_findings ADD COLUMN user_note text;
ALTER TABLE health_findings ADD COLUMN state_updated_at timestamptz;

CREATE TABLE query_optimizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    query_snapshot_id uuid NOT NULL REFERENCES query_stat_snapshots(id) ON DELETE CASCADE,
    original_query text NOT NULL,
    optimized_query text NOT NULL,
    explanation text NOT NULL,
    index_recommendations jsonb NOT NULL DEFAULT '[]'::jsonb,
    feedback text CHECK (feedback IN ('useful', 'not_useful')),
    feedback_note text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX query_optimizations_database_created_idx ON query_optimizations (monitored_database_id, created_at DESC);

CREATE TABLE database_settings (
    monitored_database_id uuid PRIMARY KEY REFERENCES monitored_databases(id) ON DELETE CASCADE,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
