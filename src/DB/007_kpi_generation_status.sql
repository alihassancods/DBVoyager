CREATE TABLE kpi_generation_statuses (
    monitored_database_id uuid PRIMARY KEY REFERENCES monitored_databases(id) ON DELETE CASCADE,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    generated_count integer NOT NULL DEFAULT 0 CHECK (generated_count >= 0),
    error_message text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE kpi_generation_statuses ENABLE ROW LEVEL SECURITY;

CREATE POLICY kpi_generation_statuses_owner ON kpi_generation_statuses
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );
