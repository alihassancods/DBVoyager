CREATE TABLE kpi_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    schema_revision_id uuid NOT NULL REFERENCES schema_revisions(id) ON DELETE CASCADE,
    candidate_json jsonb NOT NULL,
    status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'approved', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);

CREATE INDEX kpi_candidates_database_status_idx
    ON kpi_candidates (monitored_database_id, status, created_at DESC);

CREATE TABLE kpi_definitions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL UNIQUE REFERENCES kpi_candidates(id) ON DELETE RESTRICT,
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    schema_revision_id uuid NOT NULL REFERENCES schema_revisions(id) ON DELETE RESTRICT,
    definition_json jsonb NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE kpi_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kpi_definition_id uuid NOT NULL REFERENCES kpi_definitions(id) ON DELETE CASCADE,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    sql_text text NOT NULL,
    points_json jsonb NOT NULL,
    row_count integer NOT NULL CHECK (row_count >= 0),
    execution_ms double precision NOT NULL CHECK (execution_ms >= 0),
    status text NOT NULL CHECK (status IN ('succeeded', 'failed')),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX kpi_snapshots_definition_created_idx
    ON kpi_snapshots (kpi_definition_id, created_at DESC);

ALTER TABLE kpi_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE kpi_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE kpi_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY kpi_candidates_owner ON kpi_candidates
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY kpi_definitions_owner ON kpi_definitions
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY kpi_snapshots_owner ON kpi_snapshots
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM kpi_definitions k
            JOIN monitored_databases d ON d.id = k.monitored_database_id
            WHERE k.id = kpi_definition_id
              AND d.owner_user_id = app_current_user_id()
        )
    );
