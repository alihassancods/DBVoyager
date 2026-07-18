-- Durable orchestration state. Dashboard requests read stored results; only
-- queued collection jobs connect to a monitored customer database.
CREATE TABLE analysis_run_events (
    id bigserial PRIMARY KEY,
    analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    stage text NOT NULL,
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX analysis_run_events_run_id_idx
    ON analysis_run_events (analysis_run_id, id);

CREATE TABLE collection_schedules (
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    collection_kind text NOT NULL CHECK (collection_kind IN ('brief', 'dashboard')),
    interval_seconds integer NOT NULL CHECK (interval_seconds >= 60),
    next_scheduled_at timestamptz NOT NULL DEFAULT now(),
    enabled boolean NOT NULL DEFAULT true,
    PRIMARY KEY (monitored_database_id, collection_kind)
);

CREATE INDEX collection_schedules_due_idx
    ON collection_schedules (next_scheduled_at)
    WHERE enabled;

CREATE TABLE database_stat_daily_rollups (
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    collected_on date NOT NULL,
    avg_num_connections numeric(14, 2) NOT NULL,
    max_database_size_mb numeric(14, 2) NOT NULL,
    avg_cache_hit_ratio numeric(5, 2),
    PRIMARY KEY (monitored_database_id, collected_on)
);

ALTER TABLE analysis_run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE database_stat_daily_rollups ENABLE ROW LEVEL SECURITY;

CREATE POLICY analysis_run_events_owner ON analysis_run_events
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM analysis_runs run
            JOIN monitored_databases database ON database.id = run.monitored_database_id
            WHERE run.id = analysis_run_id
              AND database.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY collection_schedules_owner ON collection_schedules
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM monitored_databases database
            WHERE database.id = monitored_database_id
              AND database.owner_user_id = app_current_user_id()
        )
    );

CREATE POLICY database_stat_daily_rollups_owner ON database_stat_daily_rollups
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM monitored_databases database
            WHERE database.id = monitored_database_id
              AND database.owner_user_id = app_current_user_id()
        )
    );
