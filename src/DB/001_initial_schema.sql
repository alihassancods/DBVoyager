BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_subject text NOT NULL UNIQUE,
    email text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE monitored_databases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name text NOT NULL CHECK (btrim(display_name) <> ''),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'connection_error', 'disabled')),
    last_collected_at timestamptz,
    next_scheduled_at timestamptz,
    num_connections integer CHECK (num_connections >= 0),
    database_size_mb numeric(14, 2) CHECK (database_size_mb >= 0),
    cache_hit_ratio numeric(5, 2) CHECK (cache_hit_ratio BETWEEN 0 AND 100),
    last_successful_run_id uuid,
    current_schema_revision_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX monitored_databases_active_display_name_key
    ON monitored_databases (owner_user_id, lower(display_name))
    WHERE deleted_at IS NULL;

CREATE INDEX monitored_databases_owner_updated_idx
    ON monitored_databases (owner_user_id, updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE database_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL
        REFERENCES monitored_databases(id) ON DELETE CASCADE,
    encrypted_data_key bytea NOT NULL,
    ciphertext bytea NOT NULL,
    nonce bytea NOT NULL,
    auth_tag bytea NOT NULL,
    kms_key_ref text NOT NULL,
    key_version integer NOT NULL CHECK (key_version > 0),
    algorithm text NOT NULL DEFAULT 'AES-256-GCM'
        CHECK (algorithm = 'AES-256-GCM'),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    rotated_at timestamptz
);

CREATE UNIQUE INDEX database_credentials_one_active_per_database_key
    ON database_credentials (monitored_database_id)
    WHERE is_active;

CREATE TABLE analysis_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL
        REFERENCES monitored_databases(id) ON DELETE CASCADE,
    trigger text NOT NULL CHECK (trigger IN ('initial', 'manual', 'scheduled')),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    attempt_count smallint NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 3),
    scheduled_for timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    lease_expires_at timestamptz,
    collector_version text,
    agent_model text,
    schema_fingerprint char(64),
    schema_revision_id uuid,
    report_json jsonb,
    error_code text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (status = 'succeeded' AND started_at IS NOT NULL AND finished_at IS NOT NULL)
        OR status <> 'succeeded'
    )
);

CREATE INDEX analysis_runs_claim_idx
    ON analysis_runs (scheduled_for, created_at)
    WHERE status = 'queued';

CREATE INDEX analysis_runs_database_history_idx
    ON analysis_runs (monitored_database_id, finished_at DESC)
    WHERE status = 'succeeded';

ALTER TABLE monitored_databases
    ADD CONSTRAINT monitored_databases_last_successful_run_fkey
    FOREIGN KEY (last_successful_run_id) REFERENCES analysis_runs(id)
    ON DELETE SET NULL;

CREATE TABLE database_stat_snapshots (
    run_id uuid PRIMARY KEY REFERENCES analysis_runs(id) ON DELETE CASCADE,
    collected_at timestamptz NOT NULL,
    num_connections integer NOT NULL CHECK (num_connections >= 0),
    database_size_mb numeric(14, 2) NOT NULL CHECK (database_size_mb >= 0),
    cache_hit_ratio numeric(5, 2) NOT NULL CHECK (cache_hit_ratio BETWEEN 0 AND 100)
);

CREATE TABLE database_tables (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL
        REFERENCES monitored_databases(id) ON DELETE CASCADE,
    schema_name text NOT NULL,
    table_name text NOT NULL,
    table_type text NOT NULL CHECK (table_type IN ('BASE TABLE', 'VIEW', 'FOREIGN TABLE')),
    estimated_rows bigint CHECK (estimated_rows >= 0),
    seq_scan bigint CHECK (seq_scan >= 0),
    idx_scan bigint CHECK (idx_scan >= 0),
    n_live_tup bigint CHECK (n_live_tup >= 0),
    n_dead_tup bigint CHECK (n_dead_tup >= 0),
    stats_collected_at timestamptz,
    schema_collected_at timestamptz,
    business_summary text,
    summary_status text NOT NULL DEFAULT 'pending'
        CHECK (summary_status IN ('pending', 'ready', 'failed')),
    summary_generated_at timestamptz,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    removed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX database_tables_active_identity_key
    ON database_tables (monitored_database_id, schema_name, table_name)
    WHERE removed_at IS NULL;

CREATE INDEX database_tables_database_name_idx
    ON database_tables (monitored_database_id, schema_name, table_name)
    WHERE removed_at IS NULL;

CREATE TABLE table_stat_snapshots (
    run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    database_table_id uuid NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    collected_at timestamptz NOT NULL,
    seq_scan bigint NOT NULL CHECK (seq_scan >= 0),
    idx_scan bigint NOT NULL CHECK (idx_scan >= 0),
    n_live_tup bigint NOT NULL CHECK (n_live_tup >= 0),
    n_dead_tup bigint NOT NULL CHECK (n_dead_tup >= 0),
    PRIMARY KEY (run_id, database_table_id)
);

CREATE INDEX table_stat_snapshots_history_idx
    ON table_stat_snapshots (database_table_id, collected_at DESC);

CREATE TABLE query_stat_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    query_text text NOT NULL CHECK (octet_length(query_text) <= 16384),
    calls bigint NOT NULL CHECK (calls >= 0),
    total_exec_time_ms double precision NOT NULL CHECK (total_exec_time_ms >= 0),
    mean_exec_time_ms double precision NOT NULL CHECK (mean_exec_time_ms >= 0),
    rows_returned bigint NOT NULL CHECK (rows_returned >= 0)
);

CREATE INDEX query_stat_snapshots_run_total_time_idx
    ON query_stat_snapshots (run_id, total_exec_time_ms DESC);

CREATE TABLE index_stat_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    database_table_id uuid REFERENCES database_tables(id) ON DELETE SET NULL,
    index_name text NOT NULL,
    idx_scan bigint NOT NULL CHECK (idx_scan >= 0),
    idx_tup_read bigint NOT NULL CHECK (idx_tup_read >= 0),
    idx_tup_fetch bigint NOT NULL CHECK (idx_tup_fetch >= 0)
);

CREATE INDEX index_stat_snapshots_table_run_idx
    ON index_stat_snapshots (database_table_id, run_id);

CREATE TABLE lock_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    pid integer NOT NULL,
    lock_type text NOT NULL,
    relation_name text,
    mode text NOT NULL,
    granted boolean NOT NULL
);

CREATE INDEX lock_snapshots_run_idx ON lock_snapshots (run_id);

CREATE TABLE schema_revisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL
        REFERENCES monitored_databases(id) ON DELETE CASCADE,
    first_seen_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    fingerprint char(64) NOT NULL,
    schema_json jsonb NOT NULL,
    mermaid_erd text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (monitored_database_id, fingerprint)
);

ALTER TABLE analysis_runs
    ADD CONSTRAINT analysis_runs_schema_revision_fkey
    FOREIGN KEY (schema_revision_id) REFERENCES schema_revisions(id)
    ON DELETE SET NULL;

ALTER TABLE monitored_databases
    ADD CONSTRAINT monitored_databases_current_schema_revision_fkey
    FOREIGN KEY (current_schema_revision_id) REFERENCES schema_revisions(id)
    ON DELETE SET NULL;

CREATE TABLE health_findings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    check_name text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    message text NOT NULL,
    recommended_action text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX health_findings_run_idx ON health_findings (run_id);

CREATE TABLE table_summaries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    database_table_id uuid NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    schema_revision_id uuid NOT NULL REFERENCES schema_revisions(id) ON DELETE CASCADE,
    run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    summary text NOT NULL,
    status text NOT NULL CHECK (status IN ('ready', 'failed')),
    model text,
    prompt_version text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (database_table_id, schema_revision_id)
);

CREATE TABLE audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    monitored_database_id uuid REFERENCES monitored_databases(id) ON DELETE SET NULL,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    event_type text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_events_database_created_idx
    ON audit_events (monitored_database_id, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER monitored_databases_set_updated_at
    BEFORE UPDATE ON monitored_databases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER database_tables_set_updated_at
    BEFORE UPDATE ON database_tables
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The API sets this at transaction scope after verifying the external JWT:
--     SELECT set_config('app.user_id', '<users.id>', true);
-- The worker/migration role owns the tables and is intentionally not subject
-- to these end-user policies.
CREATE OR REPLACE FUNCTION app_current_user_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid;
$$;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitored_databases ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE database_stat_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE database_tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE table_stat_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_stat_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE index_stat_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE lock_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE table_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE database_credentials ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_self ON users
    USING (id = app_current_user_id())
    WITH CHECK (id = app_current_user_id());

CREATE POLICY monitored_databases_owner ON monitored_databases
    USING (owner_user_id = app_current_user_id())
    WITH CHECK (owner_user_id = app_current_user_id());

CREATE POLICY analysis_runs_owner ON analysis_runs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY database_stat_snapshots_owner ON database_stat_snapshots
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM analysis_runs r
            JOIN monitored_databases d ON d.id = r.monitored_database_id
            WHERE r.id = run_id AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY database_tables_owner ON database_tables
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY table_stat_snapshots_owner ON table_stat_snapshots
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM database_tables t
            JOIN monitored_databases d ON d.id = t.monitored_database_id
            WHERE t.id = database_table_id AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY query_stat_snapshots_owner ON query_stat_snapshots
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM analysis_runs r
            JOIN monitored_databases d ON d.id = r.monitored_database_id
            WHERE r.id = run_id AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY index_stat_snapshots_owner ON index_stat_snapshots
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM analysis_runs r
            JOIN monitored_databases d ON d.id = r.monitored_database_id
            WHERE r.id = run_id AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY lock_snapshots_owner ON lock_snapshots
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM analysis_runs r
            JOIN monitored_databases d ON d.id = r.monitored_database_id
            WHERE r.id = run_id AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY schema_revisions_owner ON schema_revisions
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY health_findings_owner ON health_findings
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM analysis_runs r
            JOIN monitored_databases d ON d.id = r.monitored_database_id
            WHERE r.id = run_id AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY table_summaries_owner ON table_summaries
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM database_tables t
            JOIN monitored_databases d ON d.id = t.monitored_database_id
            WHERE t.id = database_table_id AND d.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY audit_events_owner ON audit_events
    FOR SELECT
    USING (
        actor_user_id = app_current_user_id()
        OR EXISTS (
            SELECT 1 FROM monitored_databases d
            WHERE d.id = monitored_database_id
              AND d.owner_user_id = app_current_user_id()
        )
    );

-- No end-user policy exists for database_credentials. Credentials are readable
-- only by the trusted API/worker role, which also performs all writes.

CREATE OR REPLACE FUNCTION purge_expired_analysis_data()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM analysis_runs r
    WHERE r.created_at < now() - interval '90 days'
      AND NOT EXISTS (
          SELECT 1
          FROM monitored_databases d
          WHERE d.last_successful_run_id = r.id
      );

    DELETE FROM audit_events
    WHERE created_at < now() - interval '1 year';
END;
$$;

COMMIT;

-- Fresh installs use this file alone. The older numbered files remain only
-- for databases created before this bootstrap was consolidated.
BEGIN;

ALTER TABLE monitored_databases ADD COLUMN archived_at timestamptz;
CREATE INDEX monitored_databases_owner_active_idx ON monitored_databases (owner_user_id, updated_at DESC) WHERE archived_at IS NULL AND deleted_at IS NULL;

ALTER TABLE analysis_runs ADD COLUMN collection_kind text NOT NULL DEFAULT 'dashboard'
    CHECK (collection_kind IN ('dashboard', 'brief', 'statistics', 'slow_queries', 'schema', 'health_checks', 'table_summaries'));
CREATE INDEX analysis_runs_collection_kind_history_idx ON analysis_runs (monitored_database_id, collection_kind, finished_at DESC) WHERE status = 'succeeded';

ALTER TABLE health_findings
    ADD COLUMN user_state text NOT NULL DEFAULT 'open' CHECK (user_state IN ('open', 'acknowledged', 'muted')),
    ADD COLUMN user_note text,
    ADD COLUMN state_updated_at timestamptz;

CREATE TABLE dashboard_summaries (
    monitored_database_id uuid PRIMARY KEY REFERENCES monitored_databases(id) ON DELETE CASCADE,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    overview_json jsonb NOT NULL,
    etag char(64) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

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

CREATE TABLE analysis_run_events (
    id bigserial PRIMARY KEY,
    analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    stage text NOT NULL,
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX analysis_run_events_run_id_idx ON analysis_run_events (analysis_run_id, id);

CREATE TABLE collection_schedules (
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    collection_kind text NOT NULL CHECK (collection_kind IN ('brief', 'dashboard')),
    interval_seconds integer NOT NULL CHECK (interval_seconds >= 60),
    next_scheduled_at timestamptz NOT NULL DEFAULT now(),
    enabled boolean NOT NULL DEFAULT true,
    PRIMARY KEY (monitored_database_id, collection_kind)
);
CREATE INDEX collection_schedules_due_idx ON collection_schedules (next_scheduled_at) WHERE enabled;

CREATE TABLE database_stat_daily_rollups (
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    collected_on date NOT NULL,
    avg_num_connections numeric(14, 2) NOT NULL,
    max_database_size_mb numeric(14, 2) NOT NULL,
    avg_cache_hit_ratio numeric(5, 2),
    PRIMARY KEY (monitored_database_id, collected_on)
);

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

CREATE TABLE kpi_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    schema_revision_id uuid NOT NULL REFERENCES schema_revisions(id) ON DELETE CASCADE,
    candidate_json jsonb NOT NULL,
    status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'approved', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);
CREATE INDEX kpi_candidates_database_status_idx ON kpi_candidates (monitored_database_id, status, created_at DESC);

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
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    sql_text text NOT NULL,
    points_json jsonb NOT NULL,
    row_count integer NOT NULL CHECK (row_count >= 0),
    execution_ms double precision NOT NULL CHECK (execution_ms >= 0),
    status text NOT NULL CHECK (status IN ('succeeded', 'failed')),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX kpi_snapshots_database_definition_created_idx ON kpi_snapshots (monitored_database_id, kpi_definition_id, created_at DESC);

CREATE TABLE kpi_generation_statuses (
    monitored_database_id uuid PRIMARY KEY REFERENCES monitored_databases(id) ON DELETE CASCADE,
    analysis_run_id uuid REFERENCES analysis_runs(id) ON DELETE SET NULL,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'unavailable')),
    generated_count integer NOT NULL DEFAULT 0 CHECK (generated_count >= 0),
    error_message text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE dashboard_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE database_stat_daily_rollups ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_optimizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE database_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE kpi_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE kpi_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE kpi_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE kpi_generation_statuses ENABLE ROW LEVEL SECURITY;

CREATE POLICY dashboard_summaries_owner ON dashboard_summaries FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY dashboard_resources_owner ON dashboard_resources FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY collection_metrics_owner ON collection_metrics FOR SELECT USING (EXISTS (SELECT 1 FROM analysis_runs r JOIN monitored_databases d ON d.id = r.monitored_database_id WHERE r.id = analysis_run_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY collection_schedules_owner ON collection_schedules FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY analysis_run_events_owner ON analysis_run_events FOR SELECT USING (EXISTS (SELECT 1 FROM analysis_runs r JOIN monitored_databases d ON d.id = r.monitored_database_id WHERE r.id = analysis_run_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY database_stat_daily_rollups_owner ON database_stat_daily_rollups FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY query_optimizations_owner ON query_optimizations FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY database_settings_owner ON database_settings FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY kpi_candidates_owner ON kpi_candidates FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY kpi_definitions_owner ON kpi_definitions FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY kpi_snapshots_owner ON kpi_snapshots FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));
CREATE POLICY kpi_generation_statuses_owner ON kpi_generation_statuses FOR SELECT USING (EXISTS (SELECT 1 FROM monitored_databases d WHERE d.id = monitored_database_id AND d.owner_user_id = app_current_user_id()));

COMMIT;
