# DBVoyager

### AI-Powered Database Intelligence Platform for the companies

DBVoyager is created to help the companies and the developers to manage their database in a more optimized way using the Agentic AI approach

Instead of manually inspecting tables, queries, indexes, metrics, logs, and dashboards, users can simply ask questions in natural language and receive accurate business insights, performance recommendations, health reports, KPI analytics, and optimization guidance.

Built during OpenAI Build Week using **GPT-5.6** and **Codex**.

---

# The Problem

Modern databases contain thousands of tables, millions of rows, complex relationships, and constantly changing workloads.

Organizations struggle to answer questions such as:

- Why is revenue declining?
- Which customers are churning?
- What are our fastest growing product categories?
- Which queries are slowing down the database?
- Which indexes are missing?
- What risks require immediate attention?
- What KPIs should leadership monitor?

Answering these questions typically requires database administrators, analysts, and engineers and it also takes alot of the time and the resources to do it.

DBVoyager automates the entire process using the Agentic AI approach.

---

# The Solution

DBVoyager is an AI-powered Database Intelligence Platform that combines:

- Database Monitoring
- Business Intelligence
- Query Optimization
- KPI Discovery
- Schema Analysis
- Statistical Analysis
- Risk Detection
- Executive Reporting

into a single intelligent system.

The platform connects directly to PostgreSQL databases and automatically generates actionable insights from live production data.

---

# Key Features

## Business Intelligence Module

Ask questions in plain English:

> "How many customers joined last week?"

> "Which product category has the highest churn?"

> "What is our month-over-month retention rate?"

Workflow:

→ Question
→ Planning Agent
→ SQL Generation Agent
→ Schema Validation
→ Query Execution
→ Analysis Agent
→ Executive Insight

The model will answer the question in the well structured way and make it easy for the developer and the manager to decide what to do and how to manage the problem and also helps them to plan for the future work.
---

## Query Generator

Converts business questions into SQL automatically.

Features:

- Natural language to SQL
- Context aware generation
- Schema aware planning
- SQL validation
- Safe execution

The user will tell the model in the plain English what he wants to do and the model will see the whole structure and will give the most optimal solution if the user likes the solution then the model will execute the query and the work is done.
---

## Query Optimizer

Automatically analyzes slow queries.

Provides:

- Performance bottleneck detection
- Optimization recommendations
- Index recommendations
- Query comparisons
- Execution plan 

This will automatically analyze the database and then find the slowest queries in the system. Then it will suggest the optimal solution of the problem for the system and give it to the developer. It also compares both of the approach and will tell why the suggested solution is better then the previous one.
---

## Database Health Module

Provides a complete health assessment of the database.

Features:

- Health Score (0–100)
- Critical Findings
- Warning Detection
- Executive Health Summary
- Recommended Actions

Example:

Health Score: 87/100

Top Findings:

- Missing indexes on customer lookup queries
- High sequential scans on orders table
- Elevated lock contention during peak traffic

This one will work on the health of the database. It will analyze tell the warning sign like the database is about to be full and things like these and hten it will tell the user the optimal solution for this problem. It will give the top warning and after one is sovled it wil display the other one.
---

## KPI Engine

Automatically discovers and generates KPIs.

Examples:

- Revenue
- Active Customers
- New Customers
- Churn Rate
- Conversion Rate
- Order Volume

No manual KPI definitions required.

---

## Data Insights Engine

Analyzes collected database statistics and business metrics.

Provides:

- Trend detection
- Growth analysis
- Revenue insights
- Usage patterns
- Business summaries

It will analyze the whole database find all the insight the number of the columns the relation the stast and all the things that will also be used in the other system. 
---

## Risk Warning System

Detects database risks before they become production incidents.

Examples:

- Query performance degradation
- Missing indexes
- Lock contention
- Resource saturation
- Unusual workload patterns

It will try to find the potential risks in the system before they became the major backlash.
---

## Schema Intelligence

Automatically maps and explains database structure.

Features:

- Table analysis
- Relationship discovery
- Schema visualization
- Foreign key mapping
- Data model understanding

Like the insight this one is use to find the table name, columns, the relationship between the tables e.t.c.
---

## Statistics Analysis

Collects and analyzes:

- Database statistics
- Table statistics
- Index statistics
- Query statistics
- Lock statistics

---

## Visualization Engine

Generates charts automatically.

Supports:

- KPI Charts
- Trend Analysis
- Growth Curves
- Business Dashboards
- Health Monitoring Visualizations

This is to give the visual insights of the system to the user.
---

## Manager Notification Module

Transforms technical findings into business-friendly reports.

Examples:

- Executive summaries
- Risk notifications
- Health reports
- Recommended actions

Designed for managers and decision makers rather than database engineers. It wil give the answer in the simple and the plain language rather than the complex queries form.

---

## Intelligent Resource Cache

Reduces repeated database and AI workload through resource caching.

Benefits:

- Faster dashboard loading
- Reduced database overhead
- Lower AI token consumption
- Improved responsiveness

---

## Authentication & User Management

Includes:

- User Registration
- Login
- Access Tokens
- Protected Routes
- Connection Ownership Controls

Each user can securely manage their own database connections. The user have to sign up before entering our database the system is different for the manager as well for the developer

---

## Modern Frontend

Built with:

- React
- TypeScript
- Vite

Provides:

- Dashboard Interface
- Health Monitoring
- KPI Analytics
- Business Intelligence Chat
- Schema Explorer
- Query Optimization Interface

---

# System Architecture

```text
User
 │
 ▼
Frontend (React)
 │
 ▼
FastAPI Backend
 │
 ├── Authentication
 │
 ├── Business Intelligence Agent
 │
 ├── Query Optimizer Agent
 │
 ├── KPI Engine
 │
 ├── Health Monitoring
 │
 ├── Risk Detection
 │
 └── Statistics Analysis
 │
 ▼
PostgreSQL Database
```

---

# AI Workflow

## Business Intelligence Pipeline

```text
Business Question
        │
        ▼
Planner Agent
        │
        ▼
SQL Generation Agent
        │
        ▼
Schema Validator
        │
        ▼
SQL Validator
        │
        ▼
Query Execution
        │
        ▼
Analysis Agent
        │
        ▼
Charts + Insights
        │
        ▼
Final Executive Answer
```

---

# Tech Stack

## Frontend

- React
- TypeScript
- Vite
- TailwindCSS

## Backend

- FastAPI
- Python

## AI

- GPT-5.6
- Codex
- DeepSeek(API)

## Database

- PostgreSQL

## Visualization

- Custom Chart Engine

---

# Running Locally

Backend:

```bash
uvicorn src.api.main:app --reload
```

Frontend:

```bash
cd frontend

npm install

npm run dev
```

---

# Deployment

Deployed on the oracle machine.


# Future Work

- Multi-Agent Collaboration
- Incident Investigation Memory
- Predictive Failure Detection
- Autonomous Database Tuning
- Cross-Database Analytics
- Vector Memory for Historical Investigations
- Working with other databases as well

---

#  OpenAI Build Week 2026

DBVoyager was built using:

- GPT-5.6

- Codex

to create an intelligent platform that bridges the gap between database engineering and business decision making.

# Final Statement

Instead of requiring non-techinical users like the CEO, Managers to understand SQL, indexes, execution plans, and database internals, DBVoyager allows them to interact with their data through natural language while still delivering professional grade analysis and recommendations.
