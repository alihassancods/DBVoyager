# DBVoyager codebase handoff

## What this project does

DBVoyager connects to PostgreSQL, inspects its schema and runtime statistics, reports health findings, and exposes the results through FastAPI. It also generates an LLM business summary for an individual table.

## Entry points

- `uv run main.py <table_name>`: inspect one table and print its two-sentence business summary.
- `uv run v1.py --database <database>`: write the complete schema, statistics, health, and Mermaid report to `result.txt`.
- `uv run uvicorn src.api.main:app --reload`: start the HTTP API; use `/docs` for routes.

## Data flow

`src/db_engine/connection.py` creates PostgreSQL connections from `.env`. `SchemaInspector` combines the table, column, key, relation, and index inspectors; it is the single source for schema metadata. `StatisticsInspector` collects query, table, index, lock, and database statistics. `tools/health.py` reuses those snapshots and adds direct PostgreSQL health checks. `v1.py` coordinates all of them into one report.

The API stores a live connection plus its in-memory connection settings in `src/api/store.py`. `POST /connections/{id}/dashboard/refresh` builds one report; the other dashboard routes read that cached report. `/dashboard/refresh/stream` emits progress events followed by a `complete` SSE event containing the report.

## Agents

All agent code belongs in `src/agent/`. `config.py` owns reusable DeepSeek/LangChain configuration from `.env`; do not duplicate LLM setup in individual agents. `TableBusinessSummaryAgent.summarize_database_table()` obtains table columns and relationships through `SchemaInspector`, then calls DeepSeek. Its async counterpart is for FastAPI endpoints.

Required LLM configuration:

```env
DEEPSEEK_API_KEY=...
# Optional defaults:
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## Working conventions

- Reuse inspectors and models instead of adding duplicate PostgreSQL queries.
- Keep API routers in `src/api/`; `main.py` only registers routers.
- Use `uv run pytest -q` before handoff. Unit tests mock PostgreSQL and LLM calls; never commit `.env` credentials.
- Prefer adding a focused agent method over a master-agent framework until orchestration is actually needed.
