BEGIN;

CREATE TABLE bi_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    question text NOT NULL,
    plan_json jsonb NOT NULL,
    generated_sql text NOT NULL,
    result_json jsonb NOT NULL,
    insight_json jsonb NOT NULL,
    charts_json jsonb NOT NULL,
    is_pinned boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX bi_reports_connection_recent_idx ON bi_reports (monitored_database_id, is_pinned DESC, created_at DESC);

ALTER TABLE bi_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY bi_reports_owner ON bi_reports
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

COMMIT;
