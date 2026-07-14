![Checklist](image.png)
The checklist tracks your progress — click any item to mark it done. Here's how to approach each phase strategically:

---

**Phase 0 is the most skipped and most painful.** Spending 30 minutes here properly — especially seeding the database correctly and enabling `pg_stat_statements` — saves you 3 hours of debugging later. The seed script is critical: use `COPY` or batch inserts of 10,000 rows at a time rather than individual `INSERT` calls, or 5M rows will take 2 hours to insert. Faker generates realistic names and amounts but use integer `user_id` values from 1–10,000 so your slow query demo reliably hits a specific user.

**Phase 1 and 2 before any UI.** The most common hackathon mistake is building the frontend first. You have nothing to show if the backend tools don't work. Test each tool in isolation with a Python script before wiring the agent. The health auditor is the trickiest — parsing `EXPLAIN (FORMAT JSON)` output to detect seq scans requires pulling `plan.Node Type` from the nested JSON structure PostgreSQL returns.

**The agent system prompt is your most important design decision.** Two things that must be in it: first, the injected schema JSON (so the model knows your table names without asking); second, the rule "never execute DDL directly — always call `propose_fix` with the SQL and estimated impact." Without that second rule, the model will sometimes try to write fix queries inline in its text response instead of using the tool, and your approval gate breaks.

**FastAPI + WebSocket over REST for chat.** Don't use polling — a WebSocket connection lets you stream OpenAI tokens as they arrive, which makes the agent feel fast and alive. The special message types (`fix_proposal`, `benchmark`) sent over the same WebSocket are what drive the right panel without any extra HTTP calls.

**For the frontend**, the only thing that really matters for the hackathon demo is: the approval card looks great, the before/after timing is visually dramatic, and the bar chart renders cleanly. Everything else can be rough. Recharts is your best bet in Next.js — it works without any configuration and the default styling is clean enough for a demo.