# DBVoyager autonomous PostgreSQL administrator: workflow plan

## Product outcome

DBVoyager is an AI-assisted PostgreSQL administrator for companies. A user
signs in, connects a PostgreSQL database with a least-privilege role, and gets
a durable dashboard of its schema, performance, health, business meaning, and
business intelligence. Agents collect and interpret data autonomously; they do
not make customer data or production changes autonomously.

The product should answer four questions reliably:

1. **Is the database healthy?** Connections, locks, bloat, cache efficiency,
   autovacuum, timeouts, configuration, and other health checks.
2. **What is in it?** Tables, columns, primary/foreign keys, indexes,
   relationships, Mermaid/interactive ERD, and a two-sentence business summary
   for every table.
3. **What is slow or expensive?** Frequently executed and slow queries,
   relevant execution plans, query-optimizer recommendations, and estimated
   before/after cost comparisons.
4. **What does the business need to know?** Curated KPIs, chart-ready
   aggregates, and an evidence-based chat agent that can answer questions from
   the connected database without exposing unnecessary raw records.

## End-to-end customer workflow

```text
Sign up / log in with Neon Auth
        ↓
Connect a PostgreSQL database using a read-only role
        ↓
Validate TLS + credentials → encrypt configuration → persist connection
        ↓
Queue initial collection run
        ↓
Statistics + schema + health collection
        ↓
Persist immutable run + update current dashboard projection
        ↓
Schema ERD + table summaries + KPI candidates + query-optimizer candidates
        ↓
Dashboard, alerts, charts, and BI chat use stored results
        ↓
Scheduled refreshes repeat collection; users can manually refresh
```

### 1. Identity and connection onboarding

- Neon Auth owns signup, login, sessions, and JWT issuance. The authenticated
  Neon `sub` is the permanent owner identifier for every DBVoyager resource.
- `POST /connections` accepts a customer target database configuration only
  over HTTPS and only from an authenticated user.
- Verify a TLS connection before persistence. Reject inaccessible hosts,
  invalid credentials, missing TLS, or insufficient inspection permissions with
  a safe error message.
- Encrypt the complete target configuration before saving it. Never return,
  log, or place its host/user/password in an LLM prompt. The browser only sees
  a user-provided display name and connection state.
- Use a customer-created read-only monitoring role. It must not have DDL/DML
  privileges; database-level permissions are the final safety boundary even if
  application validation fails.

### 2. Initial and scheduled collection

Create an `analysis_run` immediately after a connection succeeds. A worker
claims it and records the trigger (`initial`, `manual`, or `scheduled`), start
time, collector versions, and status.

For each run, the worker:

1. Decrypts credentials only for the connection lifetime.
2. Collects `StatisticsInspector` output: database, table, index, query, and
   lock statistics.
3. Collects `SchemaInspector` output: tables, columns, keys, relationships,
   and index definitions.
4. Runs the existing health checks against those snapshots.
5. Computes a deterministic schema fingerprint. Persist a new schema revision
   only when it differs from the current fingerprint.
6. Renders Mermaid from the canonical stored schema JSON. HTML remains a
   dashboard presentation detail, not a stored source of truth.
7. Queues summary and KPI work for newly discovered or changed tables.
8. Writes the raw sanitized report plus normalized dashboard projections in
   one application-database transaction. Update the current dashboard only
   after a successful essential collection.

The first version should run daily plus manual refresh. Add alerting only when
there is a confirmed delivery channel and threshold policy.

### 3. Dashboard experience

For a selected database, show the most recent successful run and its age.
Every view must identify the collection timestamp; stale data must not look
live.

- **Overview:** database size, active connections, cache-hit ratio, critical
  health findings, schema-change status, and last-collection state.
- **Performance:** top queries by total execution time, mean execution time,
  and call count; table/index statistics; current locks; trends from snapshots.
- **Health:** findings grouped by severity with cause, evidence, recommended
  action, and the run that produced them.
- **Schema:** ERD generated from the stored schema revision. Hovering a table
  shows the persisted two-sentence business summary, key columns, current row
  estimate, and approved KPI candidates.
- **Query optimization:** slow-query cards include the normalized query,
  relevant plan, AI explanation, proposed rewrite/indexes, and estimated cost
  comparison. They never apply changes automatically.
- **Business intelligence:** approved KPI charts and the chat conversation,
  each answer linked to its run, executed SQL, and collection/query time.

All database-scoped API routes—including dashboard, schema, refresh, and
optimizer routes—must verify the JWT and enforce connection ownership. A
connection ID alone is never authorization.

## Agent workflows

### Table business-summary agent

Input is only stored schema metadata for one table: name, column names/types,
nullable/default information, and foreign-key relationships. It returns
exactly two concise business sentences.

- Run only for a new table or a changed schema fingerprint.
- Validate the result: plain text, exactly two sentences, bounded length, no
  invented facts. Mark failed summaries for retry; do not substitute hallucinated
  output.
- Persist model, prompt version, schema revision, generated time, and result.
- The visualizer reads the current persisted summary; it never calls the LLM
  during an ERD request.

### Query-optimization agent

Candidates come from stored `pg_stat_statements` snapshots, ranked separately
by total time, mean time, and calls. Do not use a single “slow” ranking.

1. User selects a candidate or DBVoyager flags it.
2. Fetch its stored normalized SQL, current schema revision, and a safe
   `EXPLAIN (FORMAT JSON)` plan from the customer database.
3. Ask the optimizer agent for a structured response: explanation, proposed
   read-only rewrite, index recommendations, tradeoffs, and confidence.
4. Validate proposed SQL with the same read-only validator used by BI chat.
5. Run `EXPLAIN`, never `EXPLAIN ANALYZE`, for both original and proposal;
   display estimated cost/rows rather than claiming observed speedup.
6. Persist the recommendation and evidence. Any `CREATE INDEX`, configuration,
   or query deployment action is a downloadable proposal requiring explicit
   customer approval outside the agent.

### KPI discovery and charts

KPI discovery is a proposal workflow, not automatic access to every business
field.

1. Use schema metadata, table summaries, relationships, types, names, and
   table statistics to propose KPI candidates: timestamps for trends, numeric
   measures, status/category dimensions, and identifiers for joins.
2. Exclude obvious sensitive fields by policy (`password`, `token`, `secret`,
   `email`, phone, address, national identifiers) and allow each customer to
   add classifications/exclusions.
3. Store each candidate with source table/column, semantic role (`measure`,
   `dimension`, `time`, `identifier`), aggregation options, confidence,
   rationale, and status (`proposed`, `approved`, `rejected`).
4. The user approves a KPI before DBVoyager schedules chart queries. A chart
   definition specifies the approved metric, dimensions, time grain, filters,
   and maximum point count.
5. The worker executes parameterized aggregate SQL through the read-only
   executor, stores chart-ready points and query provenance, and the dashboard
   renders from those stored points.

Do not send raw table contents to the KPI agent. KPI discovery should normally
need only metadata; a small aggregate result is enough to validate a chart.

### Business-intelligence chat agent

The chat agent is an evidence pipeline, not a free-form SQL executor.

```text
User question
  → classify intent and select allowed database
  → retrieve current schema, approved KPIs, table summaries, and relevant relationships
  → form a query plan and structured SQL proposal
  → validate/rewrite SQL under database policy
  → execute bounded read-only query
  → validate/redact result
  → give answer with SQL, source tables, run timestamp, and limits
```

For every chat request:

1. Scope retrieval to the selected database and its latest schema revision.
   Do not rely on the model to remember schema names.
2. Give the LLM compact metadata: relevant tables/columns/relationships,
   approved KPI definitions, data classifications, and the question. Never
   include credentials or raw reports containing secrets.
3. Require structured output containing `intent`, `tables`, `sql`, `parameters`,
   `expected_columns`, and a user-facing rationale. Reject prose-only SQL.
4. Pass SQL through the independent validator below. If it fails, ask the
   model to repair it once; otherwise answer that the question cannot be run
   safely.
5. Execute using the read-only role with a transaction-level statement timeout
   and row cap. Return either an aggregate result or at most ten rows.
6. Redact policy-classified values, then pass only the bounded result plus
   provenance to the LLM for an insight. The final answer distinguishes facts,
   calculations, and inferences.
7. Persist the question, selected schema revision/KPIs, validated SQL hash and
   SQL text, execution timing, row count, redaction outcome, result summary,
   answer, model/prompt versions, and any error. This makes every answer
   explainable and reviewable.

## Read-only SQL execution policy

This policy is mandatory for BI chat, KPI charts, optimizer comparisons, and
ad-hoc customer queries unless a future approved-write workflow is added.

- Parse SQL with a PostgreSQL-aware parser; never use a regex as the security
  control.
- Allow one statement only: `SELECT` or `WITH ... SELECT`. Reject DDL, DML,
  transaction control, `COPY`, `CALL`, `DO`, `SET`, multiple statements,
  `SELECT INTO`, and write-capable functions.
- Run `BEGIN READ ONLY` and set a short local statement timeout. Use a target
  role whose PostgreSQL privileges are read-only as the second enforcement
  layer.
- Require a server-side maximum result size of ten rows for non-aggregate
  results. For aggregates, allow one row or a bounded time-series/chart result.
  Inject a `LIMIT` only after AST validation, not string concatenation.
- Parameterize all user-provided values. Never concatenate chat text into SQL.
- Apply table/column allowlists and classifications before execution. Deny
  direct selection of restricted columns; aggregate approved measures instead.
- Record SQL, parameters after redaction, execution timing, row count, and
  validator decision. Do not send raw errors or raw unrestricted rows to the
  LLM.

## Data model additions

`DB_PLAN.md` already defines users, monitored databases, encrypted credentials,
runs, snapshots, schema revisions, health findings, and table summaries. Add
the following only as each workflow is implemented:

- `kpi_candidates` and `kpi_definitions` for proposal/approval and stable chart
  semantics.
- `chart_definitions` and `chart_snapshots` for approved query templates and
  rendered data points.
- `optimization_recommendations` for candidate query, plan evidence, proposal,
  cost comparison, confidence, and customer decision.
- `bi_conversations`, `bi_messages`, and `bi_query_executions` for chat
  provenance, validated SQL, bounded result metadata, and answers.
- `data_classifications` for table/column sensitivity policy and customer
  overrides.

All derived records reference `monitored_database_id`, the source
`analysis_run_id`, and `schema_revision_id`. This prevents an answer or chart
from silently mixing a changed schema with an old interpretation.

## Delivery order

1. **Secure foundation:** finish JWT ownership on every connection-scoped route;
   persist collection runs/snapshots; move dashboard reads from memory to Neon.
2. **Schema intelligence:** persist schema revisions, summaries, and visualizer
   tooltips; add schema-change detection.
3. **Performance intelligence:** connection-scoped optimizer endpoints and
   persistent optimization recommendations; read-only SQL validator.
4. **KPI dashboard:** candidate discovery, approval flow, chart definitions,
   aggregate query worker, and stored chart snapshots.
5. **BI chat:** metadata retrieval, structured SQL generation, validator,
   bounded executor, redaction, answer provenance, and audit views.
6. **Operational maturity:** scheduling, alerts, retries, rate limits, usage
   quotas, retention cleanup, observability, and disaster-recovery tests.

## Definition of done

The product is ready for a pilot when a company can connect a read-only
PostgreSQL database; see a durable, owner-isolated dashboard; understand each
table and its relationships; inspect evidence-backed health/performance
recommendations; approve useful KPI charts; and ask a business question whose
answer shows the exact safe SQL, source schema version, execution time, and
bounded result used to produce it.

No agent may modify a customer database in the pilot. Add write/remediation
automation only as a separate, explicit approval workflow with rollback and
audit requirements.
