BEGIN;

CREATE TABLE agent_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    agent_kind text NOT NULL CHECK (agent_kind IN ('developer', 'bi')),
    title text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    report_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (monitored_database_id, analysis_run_id, agent_kind)
);

CREATE INDEX agent_reports_connection_created_idx ON agent_reports (monitored_database_id, created_at DESC);
ALTER TABLE agent_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_reports_owner ON agent_reports FOR SELECT USING (
    EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id())
);

COMMIT;
