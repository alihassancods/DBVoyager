BEGIN;

ALTER TABLE kpi_definitions
    ALTER COLUMN candidate_id DROP NOT NULL;

COMMIT;
