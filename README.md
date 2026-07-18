# DBVoyager

DBVoyager authenticates users with Neon Auth, stores encrypted customer
PostgreSQL connection settings in its own Neon database, and keeps the live
target connection in API memory for query execution.

## 1. Create and configure Neon

Use one Neon project/database as the **DBVoyager application database**. It
holds DBVoyager tables and Neon Auth's managed `neon_auth` schema. It must not
be one of the customer databases DBVoyager will inspect.

1. In the Neon Console, select the application project and branch.
2. Open **Auth → Configuration** and enable Neon Auth for that branch.
3. Copy the **Auth URL**. It looks like
   `https://ep-xxx.neonauth.us-east-1.aws.neon.tech/neondb/auth`.
4. Copy the branch's PostgreSQL connection string from **Connect**. Use a
   trusted application/migration role, not an untrusted browser connection.
5. In the Neon SQL Editor for that same branch, run the complete contents of
   [`src/DB/001_initial_schema.sql`](src/DB/001_initial_schema.sql). It creates
   the DBVoyager application tables; Neon Auth manages its own `neon_auth`
   schema.

Neon Auth creates users, sessions, and JWTs in the application's Neon
database. The API verifies the JWT using the Auth URL's JWKS endpoint. See
[Neon's authentication flow](https://neon.com/docs/auth/authentication-flow)
and [JWT guide](https://neon.com/docs/auth/guides/plugins/jwt).

## 2. Configure the API

Install the locked Python dependencies and create `.env` in the repository
root:

```bash
uv sync
openssl rand -base64 32
```

```env
# From Neon Console → Branch → Auth → Configuration.
NEON_AUTH_BASE_URL=https://ep-xxx.neonauth.us-east-1.aws.neon.tech/neondb/auth

# From Neon Console → Connect. This is DBVoyager's application database.
APP_DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require

# Paste the 32-byte base64 value generated above. Keep it in your deployment
# secret manager; do not commit it or store it in Neon.
APP_CREDENTIAL_MASTER_KEY=PASTE_THE_OPENSSL_OUTPUT_HERE
```

`APP_CREDENTIAL_MASTER_KEY` encrypts every submitted customer connection with
a fresh AES-256-GCM data key. The database stores ciphertext and the wrapped
data key, never a plaintext customer password. Do not change this value until
credentials have been rewrapped with the replacement key.

Start FastAPI:

```bash
uv run uvicorn src.api.main:app --reload
```

Open <http://127.0.0.1:8000/docs> for the interactive OpenAPI UI. Stop the
server with `Ctrl+C`.

For a complete example from sign-up through schema/health exploration, read
[EXAMPLE_WORKFLOW.md](EXAMPLE_WORKFLOW.md).

The product roadmap and autonomous-agent safety workflow are in
[WORKFLOW_PLAN.md](WORKFLOW_PLAN.md).

## 3. Run the frontend

The React landing page lives in `frontend/`. Use Node.js 20 or newer:

```bash
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. To create a production build:

```bash
npm run build
```

Sign Up and Sign In use `POST /auth/signup` and `POST /auth/login` on the API
at `http://localhost:8000` by default. To use a different API origin, create
`frontend/.env` with `VITE_API_URL=https://your-api.example`.

## 4. Authenticate with curl

The examples use `jq` to read JSON. Replace the email and password.

Create an account:

```bash
curl -sS -X POST http://127.0.0.1:8000/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"name":"Ali","email":"ali@example.com","password":"a-long-password"}' | jq
```

If email verification is enabled in Neon Auth, complete verification before
logging in. Then sign in and save the Neon JWT. Neon returns the access token
inside the session response; the fallback path handles both current response
shapes.

```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ali@example.com","password":"a-long-password"}' \
  | jq -r '.session.access_token // .data.session.access_token')

test "$TOKEN" != "null" && test -n "$TOKEN"
```

Verify that the API accepts the token:

```bash
curl -sS http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq
```

Neon access tokens expire after 15 minutes. Log in again or use
`POST /auth/token` with a Neon session cookie to obtain a fresh token. The
cookie endpoints can be called with `curl -c cookies.txt -b cookies.txt`; JWT
bearer authentication is the normal choice for the protected API endpoints.

## 4. Create and use a customer connection

Create a connection using a **least-privilege, TLS-required customer database
role**. The returned ID is the ID to use in subsequent requests.

```bash
CONNECTION_ID=$(curl -sS -X POST http://127.0.0.1:8000/connections \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "display_name":"Production orders",
    "host":"db.example.com",
    "port":5432,
    "database":"orders",
    "user":"dbvoyager_reader",
    "password":"customer-database-password",
    "sslmode":"require"
  }' | jq -r '.connection_id')

echo "$CONNECTION_ID"
```

The API first validates the customer connection, then inserts the encrypted
credential record in `database_credentials` and registers the live connection
in memory under that ID. It also queues an initial statistics, schema, and
health-check collection in the background. The response includes
`analysis_run_id` and `analysis_status: "queued"`; completed reports and their
normalized snapshots are stored in the DBVoyager application database under
the same connection ID. The JWT subject is recorded as the in-memory owner.

Execute a query as the owner:

```bash
curl -sS -X POST http://127.0.0.1:8000/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"connection_id\":\"$CONNECTION_ID\",\"query\":\"SELECT 1 AS value\"}" | jq
```

Delete the live connection when finished:

```bash
curl -i -X DELETE "http://127.0.0.1:8000/connections/$CONNECTION_ID" \
  -H "Authorization: Bearer $TOKEN"
```

Only the JWT subject that created a live connection can execute a query or
delete it. Other users get `404`, the same response used for an unknown or
closed connection ID. A server restart removes live connections from memory;
create the connection again before running queries. The encrypted credential
record remains in the application database for the later analysis worker.

To explicitly collect a new complete analysis, call the persistent dashboard
refresh endpoint. It requires the owner JWT, performs the collection, stores a
new `analysis_runs` record and snapshots, then returns the new report:

```bash
curl -sS -X POST \
  "http://127.0.0.1:8000/connections/$CONNECTION_ID/dashboard/refresh" \
  -H "Authorization: Bearer $TOKEN" | jq
```

`GET /connections/{connection_id}/dashboard`, schema, health, and statistics
endpoints read the newest successful stored report. They continue to work for
an authenticated owner after an API restart; only a new refresh needs a live
target connection.

## Run the complete API workflow

`v2.py` simulates the frontend's first-use path: it signs up, logs in, creates
a connection, polls the initial analysis run, and prints the persisted report
JSON. Configure a new test account and target database in `.env`:

```env
DBVOYAGER_EMAIL=demo@example.com
DBVOYAGER_PASSWORD=a-long-test-password
DBVOYAGER_NAME=Demo User
TARGET_DATABASE_DISPLAY_NAME=Demo PostgreSQL
TARGET_DB_HOST=your-target-host
TARGET_DB_PORT=5432
TARGET_DB_NAME=your-target-database
TARGET_DB_USER=dbvoyager_reader
TARGET_DB_PASSWORD=your-target-password
TARGET_DB_SSLMODE=require
```

With FastAPI running, execute:

```bash
uv run v2.py
```

The account must be new; for an existing user, use the login and connection
curl commands above or change `v2.py` to skip signup.

## API reference

| endpoint | authentication | purpose |
| --- | --- | --- |
| `POST /auth/signup` | none | Create a Neon Auth email/password user. |
| `POST /auth/login` | none | Sign in and receive a Neon session/JWT. |
| `POST /auth/token` | Neon session cookie | Refresh/get a JWT. |
| `POST /auth/logout` | Neon session cookie | End the Neon session. |
| `GET /auth/me` | bearer JWT | Verify and return the current JWT identity. |
| `POST /connections` | bearer JWT | Validate, encrypt, persist, and open a customer DB connection. |
| `GET /connections/{connection_id}/analysis-runs/{run_id}` | bearer JWT | Poll a persistent analysis run and retrieve its report. |
| `GET /connections/{connection_id}/kpis/candidates` | bearer JWT | List pending/proposed KPI candidates. |
| `POST /connections/{connection_id}/kpis/candidates/{candidate_id}/approve` | bearer JWT | Approve, execute, and return a KPI chart snapshot. |
| `POST /connections/{connection_id}/kpis/candidates/{candidate_id}/reject` | bearer JWT | Reject a KPI candidate. |
| `GET /connections/{connection_id}/kpis/definitions` | bearer JWT | List approved KPI definitions. |
| `GET /connections/{connection_id}/kpis/definitions/{definition_id}/chart` | bearer JWT | Return the latest chart-agnostic KPI data. |
| `POST /connections/{connection_id}/kpis/definitions/{definition_id}/refresh` | bearer JWT | Re-run an approved KPI aggregate and return chart data. |
| `POST /queries` | bearer JWT | Execute a query through an owned live connection. |
| `DELETE /connections/{connection_id}` | bearer JWT | Close an owned live connection. |

## Troubleshooting

- `503 APP_DATABASE_URL is not configured` or master-key error: check `.env`,
  then restart Uvicorn.
- `401 Invalid or expired access token`: log in again; confirm the Auth URL is
  from the same Neon branch that issued the JWT.
- `404 Connection not found or closed`: the ID is wrong, belongs to another
  JWT subject, was deleted, or Uvicorn restarted.
- `502 Could not save the connection`: run the application schema SQL in the
  database named by `APP_DATABASE_URL` and use a role allowed to write its
  tables.
- `400 Could not connect`: verify the customer host, TLS mode, network access,
  and target role credentials.
