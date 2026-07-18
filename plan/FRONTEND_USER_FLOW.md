# Production frontend user flow

## First visit

1. The landing page explains DBVoyager's PostgreSQL health, schema, slow-query,
   optimizer, and BI outcomes, plus read-only/TLS/encryption guarantees.
2. The user signs up or logs in, then is directed to connect a database instead
   of seeing an empty dashboard.
3. The connection form validates a dedicated read-only PostgreSQL role before
   saving it. The browser never receives persisted credentials.
4. Once connected, the dashboard begins focused collection jobs and renders each
   card as its corresponding data arrives.

## Daily use

- Overview answers what is urgent, when data was collected, and where to go next.
- Health findings can be acknowledged or muted without changing detector output.
- Schema explorer shows tables, columns, relationships, indexes, and summaries.
- Slow-query rows open the advisory optimizer; optimized SQL is never applied.
- BI questions return an answer, evidence, generated read-only SQL, rows, and
  chart definitions.
- KPI candidates are reviewed before approval. Settings and audit events expose
  user-controlled preferences and activity without exposing secrets.

## API map

- Auth: `/auth/signup`, `/auth/login`, `/auth/me`, `/auth/token`, `/auth/logout`.
- Connection: `/connections`, `/connections/{id}`, `/reconnect`, `/archive`,
  `/restore`, `/test`.
- Collection: resource refresh endpoints and `/collection-runs/{run_id}/stream`.
- Read views: `/overview`, `/health-checks`, `/statistics`, `/slow-queries`,
  `/schema`, and `/schema/diagram`.
- Investigation: `/queries`, `/optimizer/*`, `/bi/investigations`, and `/kpis/*`.
- Management: `/settings` and `/audit-events`.

See `API_PLAN.md` for the complete endpoint roadmap and
`PRODUCTION_COLLECTION_PLAN.md` for concurrency and SSE behavior.
