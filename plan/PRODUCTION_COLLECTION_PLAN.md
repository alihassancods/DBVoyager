# Production collection orchestration plan

## Goal

After a user connects a database, the frontend renders useful dashboard cards as
soon as their individual data is ready. It must not wait for one long dashboard
request or allow overlapping refresh requests to race each other.

## Frontend workflow

```text
POST /connections
  → connection_id

Start in parallel:
  POST /connections/{id}/statistics/refresh
  POST /connections/{id}/schema/refresh
  POST /connections/{id}/slow-queries/refresh

After statistics and schema succeed:
  POST /connections/{id}/health-checks/refresh

After schema succeeds, low priority:
  POST /connections/{id}/table-summaries/refresh
```

Every refresh returns `202` with `{run_id, resource, status}`. The frontend
subscribes to that run's SSE stream and refreshes only its matching card when a
terminal success event arrives.

## Dependencies

| Resource | Depends on | First-render priority |
| --- | --- | --- |
| statistics | none | high |
| schema | none | high |
| slow_queries | none | high |
| health_checks | latest successful statistics and schema | high |
| table_summaries | latest successful schema | low |

Health must consume the dependency run results rather than recollecting schema
and statistics. Table summaries are LLM work and must never delay schema render.

## Backend changes

1. Add one active-run guard for each `{connection_id, collection_kind}`. A
   repeated refresh returns the existing queued/running run instead of creating
   duplicate target-database work.
2. Store dependency run IDs on each run, or store a small `depends_on` relation.
   A worker may claim health/summaries only after required runs succeed.
3. Add `collection_run_events`:

   ```text
   id, run_id, sequence, stage, status, message, created_at
   ```

   SSE reads this table, accepts `after_sequence`, and sends a terminal event.
   In-memory progress is retained only as a local-development optimization.
4. Replace `BackgroundTasks` for collection execution with a durable worker that
   claims queued rows from `analysis_runs`. API restarts must not lose work.
5. Store each resource's latest successful run on `monitored_databases`, or query
   by collection kind. A schema refresh must not replace statistics/health reads.
6. Keep `POST /dashboard/refresh` only as an admin compatibility endpoint; the
   normal frontend never calls it.

## SSE contract

Progress event:

```json
{
  "run_id": "uuid",
  "resource": "schema",
  "stage": "inspect_tables",
  "status": "running",
  "message": "Loaded 12 of 48 tables",
  "sequence": 14
}
```

Terminal success event:

```json
{
  "run_id": "uuid",
  "resource": "schema",
  "status": "succeeded",
  "result_url": "/connections/{connection_id}/schema",
  "sequence": 15
}
```

Terminal failure includes a safe error code/message and does not invalidate
results from other resources.

## Acceptance criteria

- Three first-render jobs can be started concurrently without duplicate runs.
- Health starts only after successful statistics and schema runs.
- Refreshing the browser reconnects SSE using the last received sequence.
- Restarting the API does not lose queued/running job status or progress history.
- A failed table-summary job does not block schema, health, or statistics.
