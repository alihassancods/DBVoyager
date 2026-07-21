# DBVoyager application database plan

## The design in one sentence

Keep one current, dashboard-ready projection for every monitored database and
table, plus an immutable collection run and snapshots behind it.  The current
rows make the UI cheap; the snapshots preserve history without reconnecting to
the customer's PostgreSQL server.

This plan is based on the completed collectors:

- `StatisticsInspector` returns database, table, index, query, and lock
  statistics.
- `SchemaInspector` returns the `DatabaseSchema` JSON model (tables, columns,
  primary/foreign keys, relations, and indexes).
- `audit_connection()` returns individual health findings.
- `SchemaVisualizer` renders Mermaid or interactive HTML from `DatabaseSchema`.
- `TableBusinessSummaryAgent` returns exactly two business sentences per
  table.

## Important corrections to the initial idea

1. Do put *current* database and table statistics on `monitored_databases` and
   `database_tables`, as proposed.  Do **not** make those the only copy:
   PostgreSQL statistics change and most counters are cumulative since the
   target database reset.  Store a dated snapshot for every successful run so
   the dashboard can show trends and calculate deltas.
2. Store canonical schema JSON and cached Mermaid text, not rendered HTML.
   HTML is generated presentation, while `DatabaseSchema` JSON is reusable by
   both visualizers.  Re-render HTML when the dashboard requests it.
3. A target table is uniquely identified by `(schema_name, table_name)`, not
   table name alone.  The current inspector only reads `public`, but this
   avoids a migration when more schemas are supported.
4. Store the full sanitized report JSON on every run as a forward-compatible
   record.  Store selected result sets in normal tables for dashboard queries;
   do not try to turn every future inspector field into a migration.

## PostgreSQL conventions

- Use a dedicated Neon production database for DBVoyager, separate from every
  customer database it monitors.
- Enable `pgcrypto` and use `uuid` primary keys with
  `gen_random_uuid()`. Use `timestamptz NOT NULL DEFAULT now()` for timestamps.
- Use `text` plus `CHECK` constraints for short status values rather than
  PostgreSQL enums; status values can then be extended without an enum
  migration.
- All application tables belong in `public`. Migration SQL is versioned and
  run through Neon preview branches before production.
- All target database access is TLS-only and read-only. The target role needs
  only the catalog/statistics privileges required by the existing queries;
  DBVoyager must not execute customer DDL/DML.

## Tables

### Identity and monitored connections

#### `users`

| column | type / constraint | purpose |
| --- | --- | --- |
| `id` | `uuid primary key` | Internal owner ID. |
| `auth_subject` | `text not null unique` | Immutable subject from the external auth provider. |
| `email` | `text` | Display/contact value; do not use it for authorization. |
| `created_at`, `updated_at` | `timestamptz not null` | Lifecycle timestamps. |

#### `monitored_databases`

One row per saved customer PostgreSQL database. `display_name` is the only
target-identifying value kept in plaintext.

| column | type / constraint | purpose |
| --- | --- | --- |
| `id` | `uuid primary key` | Stable dashboard/API ID. |
| `owner_user_id` | `uuid not null references users(id)` | Personal-account ownership. |
| `display_name` | `text not null` | User-chosen label, e.g. `Production orders`. |
| `status` | checked text: `active`, `paused`, `connection_error`, `disabled` | Connection/collection availability. |
| `last_successful_run_id` | `uuid nullable` | Pointer updated after a successful run. |
| `last_collected_at` | `timestamptz` | When current projection was last updated. |
| `next_scheduled_at` | `timestamptz` | Next daily collection time. |
| `num_connections` | `integer check (num_connections >= 0)` | Current `DatabaseStats.num_connections`. |
| `database_size_mb` | `numeric(14,2) check (database_size_mb >= 0)` | Current `DatabaseStats.database_size_mb`. |
| `cache_hit_ratio` | `numeric(5,2) check (cache_hit_ratio between 0 and 100)` | Current cache ratio. |
| `created_at`, `updated_at`, `deleted_at` | timestamps | Soft deletion and lifecycle. |

Unique active label: `(owner_user_id, lower(display_name)) WHERE deleted_at IS NULL`.
Index `(owner_user_id, updated_at DESC) WHERE deleted_at IS NULL`.

#### `database_credentials`

Exactly one active credential row per monitored database. Never return this
table from a user API and never log it.

| column | type / constraint | purpose |
| --- | --- | --- |
| `id` | `uuid primary key` | Credential version ID. |
| `monitored_database_id` | `uuid not null references monitored_databases(id)` | Credential owner. |
| `encrypted_data_key` | `bytea not null` | Per-record AES key, wrapped by cloud KMS. |
| `ciphertext` | `bytea not null` | AES-256-GCM encrypted connection JSON. |
| `nonce`, `auth_tag` | `bytea not null` | AES-GCM inputs/integrity tag. |
| `kms_key_ref` | `text not null` | KMS key ARN/identifier used to wrap the data key. |
| `key_version` | `integer not null check (key_version > 0)` | Application key-rotation version. |
| `algorithm` | checked text: `AES-256-GCM` | Explicit cryptographic format. |
| `is_active` | `boolean not null default true` | Allows rotation without losing audit history. |
| `created_at`, `rotated_at` | timestamps | Lifecycle. |

Partial unique index: one active row per `monitored_database_id`.

The encrypted JSON contains `host`, `port`, `database`, `user`, `password`,
`sslmode`, and optional CA certificate. Encrypt all of it, including host and
username. Cloud KMS wraps/unwraps the per-record data key; Neon contains only
ciphertext and KMS metadata, never the KMS master key.

### Collection runs and current statistics

#### `analysis_runs`

This is both the durable work item and the immutable record of an attempted
collection. Create it as `queued`, claim it in a worker, then transition it to
`running`, `succeeded`, or `failed`.

| column | type / constraint | purpose |
| --- | --- | --- |
| `id` | `uuid primary key` | Run ID. |
| `monitored_database_id`, `owner_user_id` | non-null foreign keys | Tenant-safe ownership. |
| `trigger` | checked text: `initial`, `manual`, `scheduled` | Why it ran. |
| `status` | checked text: `queued`, `running`, `succeeded`, `failed`, `cancelled` | Run lifecycle. |
| `attempt_count` | `smallint not null default 0` | Bound retries; maximum 3. |
| `scheduled_for`, `started_at`, `finished_at`, `lease_expires_at` | timestamps | Queue and worker lifecycle. |
| `collector_version`, `agent_model`, `schema_fingerprint` | `text` | Reproducibility. |
| `report_json` | `jsonb` | Full sanitized `build_report()` output. |
| `error_code`, `error_message` | `text` | Sanitized failure information only. |
| `created_at` | timestamp | Audit ordering. |

Indexes: `(status, scheduled_for)` for claiming work and
`(monitored_database_id, finished_at DESC) WHERE status = 'succeeded'` for
history/current-report queries. Claim due work with `FOR UPDATE SKIP LOCKED`;
requeue only expired leases with fewer than three attempts.

#### `database_stat_snapshots`

One row for each successful run, holding the four database-level statistics:
`run_id` (unique FK), `monitored_database_id`, `collected_at`,
`num_connections`, `database_size_mb`, and `cache_hit_ratio` with the same
checks as the current projection. Index `(monitored_database_id,
collected_at DESC)`.

`monitored_databases` is updated from this row in the same successful-run
transaction. This gives the fast "latest" dashboard view and accurate history.

#### `database_tables`

This is the current table projection used by the schema browser and hover
cards. It is not a copy of customer table data.

| column | type / constraint | purpose |
| --- | --- | --- |
| `id` | `uuid primary key` | Internal table ID. |
| `monitored_database_id` | non-null FK | Parent monitored database. |
| `schema_name`, `table_name` | `text not null` | Target table identity. |
| `table_type` | `text not null` | `BASE TABLE`, `VIEW`, or `FOREIGN TABLE`. |
| `estimated_rows` | `bigint` | Current schema estimate. |
| `seq_scan`, `idx_scan`, `n_live_tup`, `n_dead_tup` | non-negative `bigint` | Current `TableStats` fields. |
| `stats_collected_at`, `schema_collected_at` | timestamps | Freshness for the two data sources. |
| `business_summary` | `text` | Current validated two-sentence summary. |
| `summary_status` | checked text: `pending`, `ready`, `failed` | UI state while the AI task runs. |
| `summary_generated_at`, `last_seen_at`, `removed_at` | timestamps | Summary/schema lifecycle. |

Unique active identity: `(monitored_database_id, schema_name, table_name)`. A
table missing from a later schema is marked with `removed_at`, never deleted
immediately, so old runs still resolve correctly.

#### `table_stat_snapshots`

One row per table per successful run:
`run_id`, `database_table_id`, `collected_at`, `seq_scan`, `idx_scan`,
`n_live_tup`, and `n_dead_tup`, all non-negative. Unique
`(run_id, database_table_id)` and index `(database_table_id, collected_at
DESC)`. This is the source for table-level trend charts and counter deltas.

#### `query_stat_snapshots`, `index_stat_snapshots`, and `lock_snapshots`

Persist the remaining `StatisticsSnapshot` lists exactly once per successful
run:

- `query_stat_snapshots`: `run_id`, normalized `query_text`, `calls`,
  `total_exec_time_ms`, `mean_exec_time_ms`, `rows_returned`.
- `index_stat_snapshots`: `run_id`, optional `database_table_id`,
  `index_name`, `idx_scan`, `idx_tup_read`, `idx_tup_fetch`.
- `lock_snapshots`: `run_id`, `pid`, `lock_type`, optional `relation_name`,
  `mode`, and `granted`.

All counters are non-negative. Query text is sensitive operational data: cap
it at 16 KiB, remove connection literals, and omit it entirely if sanitization
cannot establish that it is safe. Add `(run_id)` indexes and an index on
`(database_table_id, run_id)` for index snapshots.

### Schema, ERD, health, and AI summaries

#### `schema_revisions`

One row only when the canonical `DatabaseSchema` content changes; reuse the
latest row when its SHA-256 fingerprint matches.

| column | type / constraint | purpose |
| --- | --- | --- |
| `id` | `uuid primary key` | Schema version ID. |
| `monitored_database_id`, `run_id` | non-null FKs | Source database and first observed run. |
| `fingerprint` | `char(64) not null` | SHA-256 of canonical JSON. |
| `schema_json` | `jsonb not null` | Exact `DatabaseSchema.model_dump(mode='json')` value. |
| `mermaid_erd` | `text not null` | Cached `SchemaVisualizer.render_mermaid()` output. |
| `created_at` | timestamp | Version timing. |

Unique `(monitored_database_id, fingerprint)`. Do not store `render_html()`:
the API reconstructs `DatabaseSchema` from `schema_json`, passes the current
summary mapping to the visualizer, and renders tooltip-capable HTML on demand.
Add `schema_revision_id` to `analysis_runs` after successful schema handling,
and `current_schema_revision_id` to `monitored_databases`.

#### `health_findings`

One row per finding returned by `audit_connection()`:
`id`, `run_id`, `monitored_database_id`, `check_name`, `severity` (`info`,
`warning`, `critical`), `message`, `recommended_action`, `details jsonb`, and
`created_at`. Index `(monitored_database_id, severity, created_at DESC)`.
This supports existing severity/check filters without parsing the report JSON.

#### `table_summaries`

Keep each AI result so a schema refresh never spends tokens for an unchanged
table.

| column | type / constraint | purpose |
| --- | --- | --- |
| `id` | `uuid primary key` | Summary version ID. |
| `database_table_id`, `schema_revision_id`, `run_id` | non-null FKs | Exact table/schema/run provenance. |
| `summary` | `text not null` | Validated two-sentence output. |
| `status` | checked text: `ready`, `failed` | Generation state. |
| `model`, `prompt_version` | `text` | Reproducibility. |
| `error_message`, `created_at` | text/timestamp | Safe error and lifecycle. |

Unique `(database_table_id, schema_revision_id)`. If it exists, reuse it;
otherwise create it after schema collection, then update
`database_tables.business_summary`, `summary_status`, and
`summary_generated_at`. The visualizer receives a mapping keyed by
`(schema_name, table_name)` and adds that current summary to each table-card
hover tooltip.

#### `audit_events`

Append-only operational/security log: `id`, optional `actor_user_id`,
`monitored_database_id`, optional `analysis_run_id`, `event_type`, redacted
`metadata jsonb`, and `created_at`. Record credential create/rotate/delete,
database create/pause/delete, manual run requests, and run completion/failure.
Never include plaintext configuration, ciphertext, KMS responses, or raw
target driver exceptions.

## Collection flow

1. An authenticated user submits connection details. Validate the payload,
   test a TLS connection, envelope-encrypt it, and insert
   `monitored_databases`, `database_credentials`, and an `initial` queued
   `analysis_runs` row in one transaction.
2. A worker claims the run, decrypts the configuration only in memory, and
   calls the existing statistics inspector, schema inspector, health checker,
   Mermaid visualizer, and summary agent. It closes every target connection.
3. On a successful collection, in one application-database transaction:
   insert the run report/snapshots/findings; upsert the current database and
   table projections; create/reuse the schema revision; create only missing
   table summaries; and mark the run successful. Update
   `last_successful_run_id` last.
4. If one collector section fails, retain its error in `report_json`, preserve
   the successful sections, and set the run to `succeeded` only if statistics
   and schema both completed. Otherwise mark the run failed and leave the
   previous current projection untouched.
5. The dashboard reads the current projections and latest successful schema
   revision. Historical pages read snapshots; no dashboard read reconnects to
   the customer database.
6. Manual refresh enqueues a run. A small external scheduler enqueues one
   daily run per active database. Do not make Neon execute target-database or
   AI work through `pg_cron`.

## Security, tenancy, and retention

- Use external JWT authentication and map its immutable subject to `users`.
  Enable PostgreSQL RLS on all owner-scoped tables, using the verified user ID
  set by the API transaction. The worker has a separate trusted role for job
  claiming. Neon supports RLS/JWT integration if direct database access is
  needed later: <https://neon.com/docs/guides/row-level-security>.
- The API and worker are the only code allowed to decrypt credentials. The
  browser receives `display_name`, status, and collected results only.
- Retain successful runs and every child snapshot/finding/summary for 90 days;
  a daily cleanup job deletes them in dependency order. Keep the current
  projection and current schema revision. Retain redacted audit events for one
  year.
- Soft-delete a monitored database immediately, disable new runs, rotate/remove
  its active credential, and permanently delete it after the recovery window.

## Required implementation work after this plan

1. Add versioned migrations for this schema, RLS policies, indexes, and
   retention job; test them on a Neon branch.
2. Replace the in-memory dictionaries in `src/api/store.py` with persistent
   repositories and change connection endpoints to authenticated
   `monitored_database` endpoints.
3. Add a worker that persists the existing `build_report()` output and its
   normalized projections. Keep `build_report()` as the collector boundary.
4. Extend `SchemaVisualizer.render_html()` with an optional summary mapping;
   add accessible tooltip content to table cards without changing its schema
   layout logic.
5. Add focused tests: two-user RLS isolation, credential encryption/redaction,
   no duplicate summaries for an unchanged schema, atomic run persistence, and
   dashboard reads after the target database is unavailable.

## Deliberately not included yet

- Organizations/team memberships, billing, notifications, fix approvals, and
  arbitrary SQL execution. Add them only when product requirements exist.
- A normalized table for every schema column/key/index. `schema_json` is the
  canonical versioned schema and `database_tables` is the fast current table
  projection; normalize deeper only when the UI needs cross-schema search or
  column-level history.
