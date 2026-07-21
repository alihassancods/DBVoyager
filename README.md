<div align="center">
  <img src="./frontend/public/screen.png" alt="DBVoyager logo" width="96" height="96" style="border-radius: 16px;">

  # DBVoyager — Agentic Database Administrator

  **An autonomous AI platform that monitors, optimizes, and protects your PostgreSQL databases — so you don't have to.**

  <p>
    <a href="#features"><img src="https://img.shields.io/badge/AI_Agents-7_teams-3b82f6?style=flat-square" alt="AI Agents"></a>
    <a href="#tech-stack"><img src="https://img.shields.io/badge/Python-3.14+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.14+"></a>
    <a href="#tech-stack"><img src="https://img.shields.io/badge/FastAPI-0.139-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"></a>
    <a href="#tech-stack"><img src="https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=white" alt="React 18"></a>
    <a href="#tech-stack"><img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL"></a>
    <a href="#tech-stack"><img src="https://img.shields.io/badge/DeepSeek-LLM-4F46E5?style=flat-square" alt="DeepSeek LLM"></a>
    <br>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT License"></a>
    <a href="https://www.youtube.com/results?search_query=DBVoyager+demo"><img src="https://img.shields.io/badge/demo-video-ff0000?style=flat-square&logo=youtube&logoColor=white" alt="Demo"></a>
  </p>
</div>

---

## The Problem

Databases are the silent heart of every business. When they slow down, your product slows down. When they break, revenue stops. But hiring a world-class DBA is expensive, and most teams make do with a patchwork of monitoring tools that scream at you without telling you what to *do*.

You get paged at 2 AM for a slow query. You dig through `pg_stat_activity` manually. You guess at an index. You cross your fingers.

There had to be a better way.

## The Solution

**DBVoyager is your AI-powered DBA team.** Connect any PostgreSQL database, and a crew of specialized AI agents goes to work — inspecting schema, measuring performance, detecting anomalies, and generating plain-English recommendations. No guesswork. No dashboards that only a database expert can read.

It watches your database 24/7, investigates what changed, and prepares safe, actionable recommendations for your approval. Everything is read-only by default. Nothing changes in production without a human saying yes.

---

## Demo

<p align="center">
  <a href="https://www.youtube.com/results?search_query=DBVoyager+demo">
    <img src="./frontend/public/screen.png" alt="Watch the demo" width="640">
  </a>
  <br>
  <em>▶️ <a href="https://www.youtube.com/results?search_query=DBVoyager+demo">Watch the full demo on YouTube</a></em>
</p>

---

## Features

### 🩺 Autonomous Health Monitoring

DBVoyager continuously inspects your database across 20+ dimensions — cache efficiency, index bloat, locking contention, replication lag, dead tuples, WAL checkpoints, connection saturation, and more. It scores overall health numerically and flags what needs attention.

- **Real-time diagnostics** — Live health checks with severity scoring (critical / warning / info)
- **Executive summaries** — AI-generated plain-English reports for your manager or client
- **Proactive alerts** — Before a slow query becomes a pagerduty alert

### ⚡ Query Optimization

When queries go slow, DBVoyager's optimizer agent digs into the `EXPLAIN` plan, cross-references your schema, and suggests concrete improvements.

- **Slow query detection** — Automatically surfaces the top N slowest queries by total execution time
- **AI-powered rewrite suggestions** — DeepSeek analyzes execution plans and generates optimized SQL
- **Cost comparison** — Side-by-side before/after cost estimates so you know the impact before you change anything
- **Index recommendations** — Targeted suggestions based on actual query patterns, not guesswork

### 🧠 Business Intelligence (Natural Language)

Ask business questions in plain English. DBVoyager plans an investigation, generates safe read-only SQL, validates it, executes a sample, and returns an insight with charts.

> *"Which product category generated the highest revenue last quarter?"*
> *"Show me monthly active users trending over the past 6 months."*
> *"What's our customer retention rate by cohort?"*

- **Multi-agent investigation pipeline** — Planner → SQL generator → Validator → Executor → Analyst → Chart generator
- **Read-only enforcement** — Generated SQL is validated for safety before execution
- **Streaming results** — See the investigation unfold in real-time via SSE
- **Persistent report history** — Every investigation is saved, pinable, and searchable

### 📊 Automatic KPI Discovery

DBVoyager reads your database schema and *proposes* business KPIs automatically — no configuration needed. It never exposes customer data to the AI; all discovery happens from metadata alone.

- **Schema-aware proposals** — Detects measure columns, time dimensions, and aggregation patterns
- **Privacy-safe** — Only metadata reaches the LLM, not row-level data
- **Auto-approval workflow** — Propose, review, approve, and track over time
- **Chart snapshots** — Every KPI comes with a rendered chart and CSV export

### 🔐 Enterprise-Grade Security

- **Zero-trust credential storage** — Customer database passwords are encrypted with AES-256-GCM before they touch disk. The master key never leaves your environment.
- **Read-only by default** — All AI-generated SQL is validated for destructive operations before execution
- **JWT authentication** — Powered by Neon Auth, with token refresh and session management
- **Per-connection ownership** — A connection can only be queried by the JWT subject that created it
- **Optional Redis cache** — Dashboard reads are cached for 60 seconds, but sensitive data never touches the cache

### 🖥️ Dashboard & Visualization

A full React dashboard puts every signal at your fingertips.

- **Mission Control** — At-a-glance health overview with active alert counts
- **Health Checks** — Browse, filter, acknowledge, or mute findings
- **Schema Explorer** — Inspect tables, columns, indexes, relationships, and row previews with Mermaid ERD visualization
- **Query Optimizer** — Prioritize and analyze slow queries with AI-powered recommendations
- **BI Navigator** — Chat-like interface for natural language business questions
- **KPI Dashboard** — Track automatically discovered and user-approved metrics with charts
- **Notifications** — In-app alerts for health status changes

---

## Architecture

DBVoyager is built as a modular multi-agent system with a clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            React Frontend (Vite + TS)                        │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌───────────┐        │
│  │Dashboard  │ │Health    │ │Optimizer  │ │BI Chat  │ │KPI View   │  ...    │
│  │Overview   │ │Checks    │ │Page       │ │          │ │           │        │
│  └─────┬─────┘ └────┬─────┘ └─────┬─────┘ └────┬────┘ └─────┬─────┘        │
└────────┼────────────┼──────────────┼────────────┼────────────┼──────────────┘
         │            │              │            │            │
    ┌────▼────────────▼──────────────▼────────────▼────────────▼──────────────┐
    │                        FastAPI (Python 3.14+)                           │
    │  ┌──────────┐ ┌───────────┐ ┌────────────┐ ┌──────────┐ ┌──────────┐  │
    │  │ Auth     │ │Connections│ │Dashboard   │ │ BI       │ │KPI       │  │
    │  │ Router   │ │Router     │ │Router      │ │Router    │ │Router    │  │
    │  └──────────┘ └───────────┘ └────────────┘ └──────────┘ └──────────┘  │
    │                             │                                          │
    │    ┌────────────────────────┼──────────────────────────────┐           │
    │    ▼                        ▼                              ▼           │
    │ ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
    │ │AI Agent Layer│  │  DB Engine       │  │ Background       │          │
    │ │ (DeepSeek)   │  │  Inspectors      │  │ Workers          │          │
    │ └──────────────┘  └──────────────────┘  └──────────────────┘          │
    └────────────────────────────────────────────────────────────────────────┘
                           │
                    ┌──────▼──────┐        ┌───────────┐
                    │  Your       │        │ Neon Auth │
                    │  PostgreSQL │        │ (JWT)     │
                    │  Database   │        └───────────┘
                    └─────────────┘
```

### Background Workers

DBVoyager runs four always-on background loops:

| Worker | Interval | Purpose |
|--------|----------|---------|
| **Scheduled Collection** | Every 30s | Claims and processes due analysis runs |
| **Persistence Worker** | Every 100ms | Flushes analysis snapshots to the application database |
| **Automated Health Fix Engine** | Every 60 min | Scans all connected databases, calculates health scores, generates fix suggestions |
| **BI Agent Loop** | Every 30 min | Runs an ongoing business question against connected databases |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.14+, FastAPI, Pydantic, Uvicorn |
| **AI / LLM** | DeepSeek (via LangChain OpenAI-compatible SDK) |
| **Database** | PostgreSQL 16+ (psycopg2-binary) |
| **Auth** | Neon Auth (JWT-based) |
| **Cache** | Redis (optional, for dashboard) |
| **Encryption** | AES-256-GCM via Cryptography |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS |
| **Routing** | React Router v6 |
| **Testing** | Pytest (50+ integration/unit tests) |
| **Package** | UV (dependency management) |

---

## Getting Started

### Prerequisites

- Python 3.14+
- Node.js 20+
- A PostgreSQL database (the application database)
- A Neon project with Neon Auth enabled
- A DeepSeek API key

### 1. Set up the application database

Create a Neon project — this will be DBVoyager's *own* database (not one of the customer databases it will monitor). Enable Neon Auth for that branch. Copy your Auth URL and connection string.

Run the initial schema SQL (see `src/DB/001_initial_schema.sql`) in the Neon SQL Editor.

### 2. Configure the API

```bash
# Install Python dependencies
uv sync

# Generate a master encryption key
openssl rand -base64 32
```

Create `.env`:

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key

NEON_AUTH_BASE_URL=https://ep-xxx.neonauth.us-east-1.aws.neon.tech/neondb/auth
APP_DATABASE_URL=postgresql://user:password@host/neondb?sslmode=require
APP_CREDENTIAL_MASTER_KEY=<paste the openssl output>
REDIS_URL=redis://127.0.0.1:6379/0   # optional
```

Start the API:

```bash
uv run uvicorn src.api.main:app --reload
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the interactive OpenAPI docs.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Sign up, connect a database, and watch DBVoyager go to work.

### 4. (Optional) Local Redis

```bash
docker compose -f docker-compose.redis.yml up -d
```

---

## Project Structure

```
dbvoyager/
├── main.py                          # Entry point (table business summary)
├── v1.py / v2.py                    # Standalone workflow scripts
│
├── src/
│   ├── api/                         # FastAPI application
│   │   ├── main.py                  # App factory, routers, background workers
│   │   ├── auth.py                  # Neon Auth integration (signup, login, JWT)
│   │   ├── connections.py           # Customer connection management
│   │   ├── dashboard.py             # Dashboard + SSE streaming
│   │   ├── health_router.py         # Health check endpoints
│   │   ├── optimizer.py             # Query optimizer endpoints
│   │   ├── business_api.py          # BI investigation endpoints
│   │   ├── kpis.py                  # KPI management endpoints
│   │   ├── notifications.py         # In-app notification endpoints
│   │   ├── management.py            # Admin / management endpoints
│   │   ├── analysis_repository.py   # Analysis run persistence + scheduling
│   │   ├── connection_repository.py # Encrypted credential CRUD
│   │   ├── resource_cache.py        # Redis + in-memory caching layer
│   │   └── persistence_worker.py    # Background snapshot writer
│   │
│   ├── agent/                       # AI Agents (all powered by DeepSeek)
│   │   ├── config.py                # Shared LLM configuration
│   │   ├── manager_agent_standalone.py  # Executive manager agent
│   │   ├── table_business_summary.py    # Table description agent
│   │   ├── health/
│   │   │   └── executive_summary_agent.py  # Health report summarizer
│   │   ├── query_optimizer/
│   │   │   ├── optimizer_agent.py   # SQL optimization agent
│   │   │   ├── models.py            # Optimization result models
│   │   │   └── prompts.py           # LLM prompt templates
│   │   ├── kpi/
│   │   │   ├── discovery.py         # Automatic KPI proposal agent
│   │   │   ├── executor.py          # KPI aggregate executor
│   │   │   ├── auto.py              # Full KPI generation pipeline
│   │   │   ├── models.py            # KPI candidate/definition models
│   │   │   └── repository.py        # KPI persistence
│   │   └── business_intelligence/
│   │       ├── orchestrator.py      # BI pipeline: plan → SQL → validate → execute → analyze → chart
│   │       ├── planner_agent.py     # Investigation planner
│   │       ├── sql_generation_agent.py  # SQL generator
│   │       ├── analysis_agent.py    # Result analyzer
│   │       ├── validator.py         # SQL safety validator
│   │       ├── schema_validator.py  # Schema-aware SQL validation
│   │       ├── schema_formatter.py  # Schema text formatter for LLM
│   │       └── prompts.py           # BI prompt templates
│   │
│   ├── db_engine/                   # PostgreSQL connection & inspection
│   │   ├── connection.py            # Database connection factory
│   │   ├── operations.py            # Query execution helpers
│   │   ├── kpi_engine.py            # KPI computation engine
│   │   ├── inspectors/
│   │   │   ├── schema_inspector.py  # Schema introspection
│   │   │   ├── explain_plan_inspector.py  # EXPLAIN plan parser
│   │   │   ├── column_inspector.py  # Column metadata
│   │   │   ├── table_inspector.py   # Table metadata
│   │   │   ├── index_inspector.py   # Index metadata
│   │   │   ├── key_inspector.py     # Primary/foreign key metadata
│   │   │   ├── relation_inspector.py    # Table relationships
│   │   │   ├── query_executor_inspector.py  # Safe query execution
│   │   │   └── statistics/          # Performance statistics inspectors
│   │   │       ├── statistics_inspector.py
│   │   │       ├── database_stats_inspector.py
│   │   │       ├── table_stats_inspector.py
│   │   │       ├── index_stats_inspector.py
│   │   │       ├── query_stats_inspector.py
│   │   │       └── lock_stats_inspector.py
│   │   ├── visualizers/
│   │   │   └── schema_visualizer.py # Mermaid ERD generation
│   │   └── queries/
│   │       ├── schema_queries.py    # Raw SQL for schema inspection
│   │       ├── statistics_queries.py# Raw SQL for statistics
│   │       └── optimizer_query.py   # Raw SQL for optimizer
│   │
│   ├── models/                      # Pydantic models
│   │   ├── schema/                  # Schema data models
│   │   ├── statistics/              # Statistics data models
│   │   ├── explain/                 # EXPLAIN plan models
│   │   ├── api/                     # API request/response models
│   │   ├── business_intelligence/   # BI data models
│   │   └── database_models.py       # Application DB ORM models
│   │
│   ├── services/
│   │   ├── health/
│   │   │   ├── health_summary.py    # Health scoring logic
│   │   │   └── fix_service.py       # Automated fix engine
│   │   ├── query_execution/         # Query execution service
│   │   ├── query/                   # Query generation service
│   │   └── sql_validation/          # SQL safety validation
│   │
│   └── visualization/
│       ├── chart_generator.py       # Automatic chart generation
│       └── model.py                 # Chart data models
│
├── tools/                           # CLI tools
│   ├── v1.py                        # Complete health/stats/schema report builder
│   ├── health.py                    # 20+ health check implementations
│   └── __init__.py
│
├── frontend/                        # React application
│   └── src/
│       ├── App.tsx                  # Router & auth guard
│       ├── lib/
│       │   ├── auth.ts              # Auth helpers (JWT, session)
│       │   ├── dashboardData.ts     # Dashboard data fetching
│       │   ├── dashboardCache.ts    # Dashboard caching
│       │   └── resourceCache.ts     # Resource-level caching
│       └── pages/
│           ├── LandingPage.tsx       # Marketing landing
│           ├── AuthPage.tsx          # Login / signup
│           ├── DashboardPage.tsx     # Mission control overview
│           ├── ConnectionsPage.tsx   # Connection management
│           ├── HealthChecksPage.tsx  # Health diagnostics
│           ├── OptimizerPage.tsx     # Query optimizer
│           ├── SchemaExplorerPage.tsx# Schema browser
│           ├── BiChatPage.tsx        # Natural language BI
│           ├── KpisPage.tsx          # KPI dashboard
│           └── QueryDetailsPage.tsx  # Individual query analysis
│
├── tests/                           # Pytest test suite (50+ tests)
├── plan/                            # Planning & design documentation
├── databases/                       # Demo database seed scripts
├── requirements.txt
├── pyproject.toml
└── LICENSE
```

---

## AI Agents

DBVoyager runs a team of specialized AI agents, each with a focused job:

### 1. 🏥 Health Check Agent
**File:** `tools/health.py` + `src/services/health/`

Runs 20+ PostgreSQL health checks — cache hit ratio, index bloat, replication lag, lock contention, connection saturation, dead tuple ratio, WAL checkpoints, long-running transactions, and more. Scores health numerically (0–100) and classifies each finding as critical, warning, or info.

### 2. 📋 Executive Summary Agent
**File:** `src/agent/health/executive_summary_agent.py`

Takes the raw health findings and generates a crisp, non-technical executive summary. Designed for managers and stakeholders who need to know what's wrong and what to do about it — not how PostgreSQL MVCC works.

### 3. 🧑‍💼 Manager Agent (Executive Alerts)
**File:** `src/agent/manager_agent_standalone.py`

The bridge between technical telemetry and business stakeholders. Translates health scores and findings into plain-English risk assessment and recommended actions. Saves notifications to a dedicated table so the UI can display them.

### 4. ⚡ Query Optimizer Agent
**File:** `src/agent/query_optimizer/optimizer_agent.py`

Analyzes slow queries from `pg_stat_statements`, fetches `EXPLAIN` plans, and uses DeepSeek to produce optimized SQL and index recommendations. Compares before/after costs so you can measure impact before making changes.

### 5. 🧠 Business Intelligence Agents (Pipeline)
**Files:** `src/agent/business_intelligence/*`

A multi-agent pipeline that takes natural language business questions and produces data-driven insights:

- **Planner Agent** — Decomposes a business question into an investigation plan
- **SQL Generation Agent** — Writes safe, read-only SQL based on the plan and schema
- **Analysis Agent** — Analyzes query results into structured business insights with evidence and recommendations
- **Chart Generator** — Automatically builds visualizations from result sets

### 6. 📈 KPI Discovery Agent
**File:** `src/agent/kpi/discovery.py`

Proposes chartable business KPIs from database schema metadata alone — never seeing customer rows. Filters out sensitive columns automatically, and suggests aggregations, time grains, and dimensions for each metric.

### 7. 🛠️ Health Fix Engine
**File:** `src/services/health/fix_service.py`

The proactive fixer. Runs automated health scans every hour, generates candidate AI fix suggestions for critical and warning issues, and logs executive summaries through the Manager Agent for human review.

---

## Roadmap

- [x] **Multi-agent AI architecture** — Specialized agents for health, optimization, BI, and KPIs
- [x] **Health monitoring** — 20+ automated PostgreSQL diagnostics with scoring
- [x] **Query optimization** — Explain plan analysis with AI-generated improvements
- [x] **Natural language BI** — Ask questions in English, get insights and charts
- [x] **Automatic KPI discovery** — Schema-driven metric proposals
- [x] **Executive reporting** — Plain-English summaries for non-technical stakeholders
- [x] **React dashboard** — Full SPA with real-time SSE streaming
- [x] **Neon Auth integration** — JWT-based authentication
- [x] **Encrypted credential storage** — AES-256-GCM for customer connections
- [ ] **PagerDuty / Slack integration** — Push notifications for critical alerts
- [ ] **Historical trend analysis** — Track health scores and query performance over time
- [ ] **Multi-database support** — MySQL, Snowflake, and other engines beyond PostgreSQL
- [ ] **Self-healing mode** — Automated execution of low-risk fixes (with human approval gates)
- [ ] **Schema diff & migration tracking** — Detect schema changes and their performance impact
- [ ] **Team collaboration** — Shared dashboards, comment threads on findings
- [ ] **On-premise deployment** — Fully air-gapped installation option
- [ ] **Cost optimization** — Right-sizing recommendations based on usage patterns

---

## Contributors

Built with care by [Ali Hassan](https://github.com/alihassancods) and [Shaheer Sajid](https://github.com/ShaheerS171). 
Contributions, issues, and feature requests are welcome.

---

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.

---

<p align="center">
  <strong>Observe · Investigate · Recommend</strong>
  <br>
  <em>Your database deserves a dedicated DBA. Now it has one.</em>
</p>
