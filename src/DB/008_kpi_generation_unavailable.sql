ALTER TABLE kpi_generation_statuses
    DROP CONSTRAINT kpi_generation_statuses_status_check;

ALTER TABLE kpi_generation_statuses
    ADD CONSTRAINT kpi_generation_statuses_status_check
    CHECK (status IN ('running', 'succeeded', 'failed', 'unavailable'));
