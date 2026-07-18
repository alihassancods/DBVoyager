# DBVoyager production API journey

This plan describes the API surface a frontend needs from the first landing-page
visit through ongoing database investigation. Every connection-scoped endpoint
requires a Neon bearer JWT and returns `404` for resources not owned by that JWT.
Credentials and encrypted credential material are never returned.

## Journey

```text
Landing → auth → connect database → collection progress → overview
                                                    ├→ health
                                                    ├→ schema
                                                    ├→ statistics / slow queries → optimizer
                                                    ├→ BI investigation
                                                    └→ KPI review, settings, audit trail
```

## Public and authentication

- Static landing page: no API. Future: `GET /public/demo`, `GET /public/status`.
- `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`, `POST /auth/token`, and
  `POST /auth/logout` support account and session management.
- Future account recovery: `POST /auth/password/reset`,
  `POST /auth/password/reset/confirm`, and `POST /auth/email/resend-verification`.

## Connections and onboarding

- `GET /connections`, `POST /connections`, `GET /connections/{id}`, and
  `PATCH /connections/{id}` support the connection picker and renaming.
- `POST /connections/{id}/test` validates supplied credentials before use.
- `POST /connections/{id}/archive` and `/restore` hide or restore a database.
- Planned: `/reconnect` decrypts persisted credentials after an API restart;
  `/disconnect` closes only the live connection.

## Collection jobs and dashboard

- Each refresh returns `202 {run_id, resource, status}` and is monitored through
  `GET /connections/{id}/collection-runs/{run_id}` or its `/stream` SSE endpoint.
- Reads: `GET /connections/{id}/overview`, `/dashboard`, `/statistics`,
  `/slow-queries`, `/health-checks`, `/schema`, and `/schema/diagram`.
- Refreshes: `POST` to `/dashboard/refresh`, `/statistics/refresh`,
  `/slow-queries/refresh`, `/health-checks/refresh`, and `/schema/refresh`.
- Planned detail/history routes: health finding detail, table detail, schema
  revisions, and slow-query detail.

## Investigation

- Read-only SQL editor: `POST /connections/{id}/queries`.
- Optimizer: `GET /connections/{id}/optimizer/slow-queries`, `POST .../optimizations`,
  `POST .../optimizations/compare`, `GET .../optimizations/{id}`, and feedback.
  Optimizer output is advisory; it never executes SQL or creates indexes.
- BI: `POST /connections/{id}/bi/investigations` returns the answer, evidence,
  generated SQL, bounded result rows, and chart definitions. Planned conversation
  endpoints add durable history only when the single-question workflow is proven.
- KPI: existing candidate, approve/reject, definition, chart, and refresh routes.

## Trust and control

- `PATCH /connections/{id}/health-checks/{finding_id}` stores user state:
  `open`, `acknowledged`, or `muted`.
- `GET/PATCH /connections/{id}/settings` stores display/notification preferences.
- `GET /connections/{id}/audit-events` exposes owner-visible activity.
- All user SQL is one read-only statement, with a server-side row limit and timeout.

## Delivery order

1. Auth, connection list/create/test, and collection progress.
2. Overview, health, schema, statistics, and slow-query read views.
3. Optimizer and BI investigation.
4. KPI, settings, audit, saved queries, and durable BI conversations.

Every new endpoint needs ownership, response-contract, and unsafe-SQL regression
tests. Run `uv run pytest -q` and `git diff --check` before handoff.
