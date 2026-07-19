BEGIN;

CREATE TABLE dashboard_resources (
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    resource text NOT NULL,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    etag char(64) NOT NULL,
    payload_json jsonb NOT NULL,
    generated_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (monitored_database_id, resource)
);

CREATE INDEX dashboard_resources_updated_idx ON dashboard_resources (updated_at DESC);

ALTER TABLE dashboard_resources ENABLE ROW LEVEL SECURITY;

CREATE POLICY dashboard_resources_owner ON dashboard_resources
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

COMMIT;
