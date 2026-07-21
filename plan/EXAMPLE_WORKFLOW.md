# Example user workflow: Ali investigates the production orders database

This is the end-to-end workflow supported by the current API. Complete the
[Neon and FastAPI setup](README.md#1-create-and-configure-neon) first, then
start the API at `http://127.0.0.1:8000`.

Ali owns a PostgreSQL database named `orders` and wants to understand its
schema, current health, statistics, and slow queries without handing database
credentials to a browser.

## 1. Create an account and obtain a JWT

Ali registers with Neon Auth:

```bash
curl -sS -X POST http://127.0.0.1:8000/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Ali Khan",
    "email":"ali@example.com",
    "password":"use-a-real-long-password"
  }' | jq
```

If Neon Auth email verification is enabled, Ali completes the verification
email now. He then logs in and saves the short-lived access token:

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ali@example.com","password":"use-a-real-long-password"}' \
  | jq -r '.session.access_token // .data.session.access_token')

curl -sS http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq
```

The `/auth/me` response proves that the API verified the Neon JWT signature,
issuer, audience, and expiry. Ali logs in again when the token expires.

## 2. Connect the database

Ali creates a dedicated, TLS-only, read-only PostgreSQL role in `orders` with
the catalog/statistics permissions required by DBVoyager. He then submits that
role—not an application owner or superuser—to DBVoyager:

```bash
CONNECTION_ID=$(curl -sS -X POST http://127.0.0.1:8000/connections \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "display_name":"Orders production",
    "host":"orders-prod.example.com",
    "port":5432,
    "database":"orders",
    "user":"dbvoyager_reader",
    "password":"reader-role-password",
    "sslmode":"require"
  }' | jq -r '.connection_id')

echo "Connection ID: $CONNECTION_ID"
```

DBVoyager tests the connection before accepting it. It then stores the full
configuration encrypted in the DBVoyager application database and creates an
in-memory live connection. The returned ID is durable, but its live connection
is not: after an API restart Ali submits the connection again.

## 3. Run a focused query

Ali can run an operational query through the live connection:

```bash
curl -sS -X POST http://127.0.0.1:8000/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"connection_id\":\"$CONNECTION_ID\",\"query\":\"SELECT count(*) AS order_count FROM orders\"}" | jq
```

If a second user, Sara, sends her own JWT with Ali's `CONNECTION_ID`, the API
returns `404` and does not execute the query. The owner check is against the
Neon JWT subject saved with the live connection.

## 4. Build the dashboard report

Ali asks DBVoyager to collect statistics, schema metadata, a Mermaid ERD, and
health findings. The collectors create fresh target-database connections as
needed, then cache the completed report in API memory.

```bash
curl -sS -X POST \
  "http://127.0.0.1:8000/connections/$CONNECTION_ID/dashboard/refresh" | jq \
  > orders-dashboard.json
```

For a CLI client that wants progress, Ali uses the SSE endpoint instead:

```bash
curl -N -X POST \
  "http://127.0.0.1:8000/connections/$CONNECTION_ID/dashboard/refresh/stream"
```

The stream emits `statistics`, `schema`, and `health_checks` progress events,
then a `complete` event containing the report. A failed section is retained as
an error in the report so the successful sections remain useful.

## 5. Explore the collected data without re-querying the target database

After refresh, these endpoints read the cached report:

```bash
# Entire report
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/dashboard" | jq

# Critical health findings only
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/health-checks?severity=critical" | jq

# Ten most-called queries
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/statistics/queries?sort=calls&limit=10" | jq

# Table, index, and lock statistics
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/statistics/tables" | jq
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/statistics/indexes" | jq
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/statistics/locks" | jq

# Canonical schema metadata and Mermaid ERD
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/schema" | jq
curl -sS "http://127.0.0.1:8000/connections/$CONNECTION_ID/schema/diagram" | jq -r '.data'
```

Ali can paste the Mermaid output into a Mermaid renderer while a frontend is
not available. The schema endpoint also provides the table, column, key,
relation, and index metadata required to build a custom visualizer.

## 6. Close the live connection

When Ali finishes, he closes the in-memory connection:

```bash
curl -i -X DELETE "http://127.0.0.1:8000/connections/$CONNECTION_ID" \
  -H "Authorization: Bearer $TOKEN"
```

He can also sign out the Neon Auth browser/curl session using
`POST /auth/logout` with its saved session cookie.

## Current boundaries before production use

- Connection creation, query execution, and connection deletion require JWT
  ownership today.
- Dashboard routes currently use the in-memory connection but do **not** yet
  enforce the same JWT ownership check. Do not expose dashboard endpoints to
  untrusted users until that guard is added.
- Dashboard reports are cached only in memory. The application schema and
  encrypted credentials are persistent, but storing runs, schema snapshots,
  health findings, and summaries is the next implementation step described in
  `DB_PLAN.md`.
- The two-sentence `TableBusinessSummaryAgent` exists, but it is not yet
  exposed through a connection-scoped API or included in dashboard tooltips.
- `/optimizer/*` currently uses the server's default configured database, not
  a user's `CONNECTION_ID`; it is not part of the authenticated customer
  workflow yet.
