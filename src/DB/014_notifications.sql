BEGIN;

CREATE TABLE notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    monitored_database_id uuid NOT NULL REFERENCES monitored_databases(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL CHECK (btrim(idempotency_key) <> ''),
    severity text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
    body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
    action_path text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    delivery_claim_id uuid,
    delivery_claimed_at timestamptz,
    delivered_at timestamptz,
    read_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key),
    CHECK (action_path IS NULL OR action_path = '/' OR action_path ~ '^/[^/]')
);

CREATE INDEX notifications_pending_idx ON notifications (user_id, created_at)
    WHERE delivered_at IS NULL;
CREATE INDEX notifications_history_idx ON notifications (user_id, created_at DESC);
CREATE INDEX notifications_unread_idx ON notifications (user_id, created_at DESC)
    WHERE read_at IS NULL;

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY notifications_owner ON notifications
    USING (user_id = app_current_user_id())
    WITH CHECK (user_id = app_current_user_id());

COMMIT;
