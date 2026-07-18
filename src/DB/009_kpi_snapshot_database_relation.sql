-- Directly scope every KPI snapshot to its monitored database. This enables
-- efficient dashboard reads without resolving each KPI definition separately.
ALTER TABLE kpi_snapshots
    ADD COLUMN IF NOT EXISTS monitored_database_id uuid;

UPDATE kpi_snapshots AS snapshot
SET monitored_database_id = definition.monitored_database_id
FROM kpi_definitions AS definition
WHERE definition.id = snapshot.kpi_definition_id
  AND snapshot.monitored_database_id IS NULL;

ALTER TABLE kpi_snapshots
    ALTER COLUMN monitored_database_id SET NOT NULL;

ALTER TABLE kpi_snapshots
    DROP CONSTRAINT IF EXISTS kpi_snapshots_monitored_database_id_fkey;

ALTER TABLE kpi_snapshots
    ADD CONSTRAINT kpi_snapshots_monitored_database_id_fkey
    FOREIGN KEY (monitored_database_id)
    REFERENCES monitored_databases(id)
    ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS kpi_snapshots_database_definition_created_idx
    ON kpi_snapshots (monitored_database_id, kpi_definition_id, created_at DESC);
