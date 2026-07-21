# DBVoyager Deployment Guide

This guide deploys the React frontend and FastAPI backend as separate HTTPS services:

- `https://app.example.com` serves the Vite build.
- `https://api.example.com` runs FastAPI and WebSocket notifications.
- Neon hosts the DBVoyager application database and Neon Auth.
- A TLS Redis instance supplies the short-lived shared response cache and persistence stream.

Do not deploy the API with `--reload`, commit `.env` files, or expose Redis publicly.

## 1. Prerequisites

Provision these before deploying application code:

1. A Neon project and branch dedicated to DBVoyager. This is the application database, not a customer database.
2. Neon Auth enabled on that same branch. Record its Auth URL and the branch PostgreSQL connection string.
3. Managed Redis with TLS enabled. The API treats Redis as best-effort, but production should provide it.
4. A Python 3.14 runtime with `uv`, and Node.js 20+ for the frontend build.
5. TLS-enabled public DNS names for the frontend and API.

Customer PostgreSQL credentials are submitted later through the product. Use a distinct, least-privilege, TLS-required read-only role for every customer database.

## 2. Create the application database

In Neon, create/choose the DBVoyager application branch and enable Neon Auth.

Run the repository migrations against that database in filename order. Run each migration once; never edit an applied migration.

```bash
cd DBVoyager

for migration in src/DB/*.sql; do
  psql "$APP_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$migration"
done
```

Use a trusted migration role for this command. Confirm the loop has completed successfully before starting the API.

For an existing environment, run only migrations that have not already been applied according to your deployment/change-management record. The SQL files do not create a migration ledger automatically.

## 3. Configure backend secrets

Create the following secrets in the deployment platform. Do not put these values in the frontend build or source control.

```env
# Neon Auth configuration from the same branch as APP_DATABASE_URL.
NEON_AUTH_BASE_URL=https://YOUR-NEON-AUTH-HOST/neondb/auth

# DBVoyager's own Neon database. It stores users' encrypted target credentials,
# analysis reports, notifications, and application state.
APP_DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require

# Exactly one base64-encoded 32-byte value. Generate once and store in a secret manager.
APP_CREDENTIAL_MASTER_KEY=PASTE_OUTPUT_OF_OPENSSL_RAND_BASE64_32

# Managed Redis with TLS in production. Do not use a plaintext redis:// URL over the internet.
REDIS_URL=rediss://USER:PASSWORD@HOST:6380/0

# Only public frontend origins. Keep the regex narrow; do not use .*, which accepts any origin.
FRONTEND_ORIGINS=https://app.example.com
FRONTEND_ORIGIN_REGEX=^https://app\.example\.com$

# Optional agent configuration when AI-backed functionality is enabled.
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Optional: periodic BI agent cadence. Defaults to 1800 (30 minutes).
DBVOYAGER_AGENT_INTERVAL_SECONDS=1800
```

Generate the master key once:

```bash
openssl rand -base64 32
```

Treat `APP_CREDENTIAL_MASTER_KEY` as durable encryption material. Replacing it without a credential-rewrapping migration makes stored customer credentials unreadable.

## 4. Deploy the FastAPI backend

From the repository root:

```bash
uv sync --frozen
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Use the platform's process manager to keep this command running and to inject the secrets above. Run at least two replicas only after verifying that each replica can reach the same Neon and Redis services; live customer target connections remain in API memory, so a customer may need to reconnect after a process restart or when routed to a different replica.

Expose these backend paths through HTTPS:

- `GET /health` for the load balancer health check. A healthy response is `{"status":"healthy"}`.
- `/docs` only if the interactive API documentation is acceptable in the environment.
- `/ws/notifications` with WebSocket upgrade support.

Example Nginx reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name api.example.com;

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The API starts scheduled collection, persistence, and notification workers in its lifespan. Watch API logs and Redis connectivity after every deploy; Redis failure falls back to database reads but disables the shared cache/persistence path.

## 5. Build and deploy the frontend

Create a frontend-only build-time environment file:

```env
VITE_API_URL=https://api.example.com
VITE_DEMO_URL=https://your-demo.example.com
```

`VITE_*` values are embedded in the browser bundle. They must never contain passwords, tokens, database URLs, or private keys.

Build the static site:

```bash
cd frontend
npm ci
npm run build
```

Deploy the contents of `frontend/dist/` to static hosting at `https://app.example.com`.

For Vercel, set the project root directory to `frontend`, then add `VITE_API_URL`
and (optionally) `VITE_DEMO_URL` in Project Settings → Environment Variables before
each production build. The included `frontend/vercel.json` provides SPA route
fallback. Vite embeds these public values at build time; changing one requires a
redeploy.

Configure the host to serve `index.html` for unknown non-file paths. DBVoyager uses browser routes such as `/dashboard`, `/connections`, and `/schema-explorer`; without an SPA fallback, refreshing those URLs returns a 404.

Example Nginx static host:

```nginx
server {
    listen 443 ssl http2;
    server_name app.example.com;
    root /srv/dbvoyager/frontend/dist;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~* \.(?:js|css|png|svg|woff2?)$ {
        try_files $uri =404;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
```

The frontend preserves an API URL path prefix for notifications. If the API is proxied under a path such as `/api`, set `VITE_API_URL` to that exact public prefix and proxy both HTTP and `/api/ws/notifications` to FastAPI.

## 6. Release procedure

1. Back up/verify the Neon branch and record the current application release.
2. Run unapplied SQL migrations with `ON_ERROR_STOP=1`.
3. Deploy the API with new secrets/configuration, then wait for `GET /health` to return 200.
4. Build and publish `frontend/dist/` with the production `VITE_API_URL`.
5. Confirm CORS preflight from the public frontend origin and WebSocket connection to `/ws/notifications`.
6. Run the smoke test below with a non-production account and a safe read-only target database.

## 7. Smoke test

After deployment, verify the public paths:

```bash
curl -fsS https://api.example.com/health
curl -fsSI https://app.example.com/
curl -fsSI https://app.example.com/dashboard
```

Then use the frontend to:

1. Sign up or sign in through Neon Auth.
2. Create a connection using a TLS-required read-only PostgreSQL user.
3. Wait for the initial collection, then open Dashboard, Health Checks, Schema Explorer, Optimizer, and KPI pages.
4. Confirm API loading overlays appear for route loads/actions, but not notification refreshes or polling.
5. Confirm a notification WebSocket remains connected in the browser network inspector.

## 8. Monitoring and troubleshooting

Monitor at minimum:

- API process health, latency, 5xx rate, and worker exceptions.
- Neon connection saturation, query latency, and migration status.
- Redis availability and `X-Cache` response headers (`HIT`, `MISS`, or `BYPASS`).
- Browser errors, failed CORS preflights, and WebSocket close codes.

Common issues:

| Symptom | Cause and action |
| --- | --- |
| `503 APP_DATABASE_URL is not configured` | Add the backend secret and restart the API. |
| `NEON_AUTH_BASE_URL must be an HTTPS Neon Auth URL` | Use the Auth URL from the same Neon branch as the application database. |
| Browser requests fail with CORS errors | Set `FRONTEND_ORIGINS` and a narrow `FRONTEND_ORIGIN_REGEX` to the exact public frontend origin. |
| Notification bell does not update | Verify the reverse proxy forwards WebSocket upgrades and that `VITE_API_URL` matches the API's public URL/prefix. |
| `X-Cache: BYPASS` | Redis is unset or unavailable. Check the TLS Redis URL and network access. |
| Customer query execution fails after restart | Live target connections are memory-resident; reconnect the customer database through the UI. |
| Deep-analysis/KPI generation fails | Verify the configured AI provider secrets and inspect API logs; basic stored dashboard reads remain available. |

## 9. Rollback

1. Re-deploy the previous API and frontend release.
2. Do not roll back applied database migrations by editing or deleting migration files. Use a new forward migration when data/schema correction is needed.
3. Keep `APP_CREDENTIAL_MASTER_KEY` unchanged during rollback.
4. If a Redis cache entry is suspected to be stale, let its 60-second TTL expire or flush only DBVoyager's `dbv:v1:*` keys in the dedicated Redis database; never broadly flush a shared Redis service.
