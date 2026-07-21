# DBVoyager — Complete Copy & Language Guide

This file is the single source of truth for every word that appears in the
DBVoyager frontend. The coding agent must use these exact strings — do not
paraphrase, shorten, or rewrite them. Each section maps directly to a
component or page in the frontend.

---

## Brand voice

DBVoyager speaks like a senior engineer who is also a calm, confident co-pilot.
Never corporate. Never hype. Never vague. Every sentence earns its place.

- Short sentences over long ones
- Active voice always ("The agent fixed it" not "It was fixed")
- Numbers over adjectives ("4,200ms → 38ms" not "dramatically faster")
- Confidence without arrogance ("Your database has a guardian" not "Revolutionary AI")
- When something goes wrong, be direct and helpful — never apologetic

---

## 1. LANDING PAGE

### Navbar

```
Logo wordmark:        DBVoyager
Nav links:            Features   Pricing   Docs   Blog   GitHub ★ 312
CTA ghost button:     Sign in
CTA filled button:    Start for free
```

### Hero section

```
Eyebrow label:        AI Database Engineer

Main headline:        Your database has
                      a guardian now.

Subheading:           DBVoyager connects to your PostgreSQL, watches it around
                      the clock, diagnoses problems before they escalate, and
                      fixes them — with your approval.

Primary CTA:          Start your project
Secondary CTA:        Watch the demo

Below CTAs fine print: Free plan available · No credit card required · PostgreSQL-native
```

### Hero social proof strip (below CTA buttons, small text row)

```
Joined by engineers from → [logo] [logo] [logo] [logo] [logo]
```

### Feature pill strip (6 pills, icon + label)

```
Pill 1:   AI Health Audit
Pill 2:   Schema Inspector
Pill 3:   Query Optimizer
Pill 4:   Business Intelligence
Pill 5:   KPI Agents
Pill 6:   Proactive Alerts
```

---

### Feature section 1 — Autonomous guardian (left text, right mockup)

```
Section eyebrow:    Database Health

Headline:           It finds the problem.
                    You approve the fix.

Body copy:          Most teams discover database issues when users start
                    complaining. DBVoyager finds them first.

                    The moment it detects a slow query, a missing index,
                    or table bloat — it wakes up, explains the problem in
                    plain English, and drafts a fix. You review it. One
                    click. Done.

Stat callout:       4,200ms → 38ms
Stat label:         average query improvement after index fix

Secondary stat:     < 60 seconds
Secondary label:    from problem detected to fix proposed
```

### Feature section 2 — Business intelligence (right text, left mockup)

```
Section eyebrow:    Business Intelligence

Headline:           Ask your data anything.
                    In plain English.

Body copy:          No SQL. No analyst. No waiting.

                    Type a question — "Who are our top customers this
                    month?" — and DBVoyager writes the query, runs it
                    safely on a read-only connection, and returns the
                    answer as a chart, a number, or a table. Then it
                    tells you what it means in two sentences.

Feature list:
  →  Natural language to SQL, schema-aware
  →  Auto-detects chart type from result shape
  →  2-sentence AI analyst summary on every result
  →  Follow-up question suggestions after each answer
  →  Save any result to your BI library
```

### Feature section 3 — Schema visualizer (left text, right mockup)

```
Section eyebrow:    Schema & Visibility

Headline:           Your entire database,
                    understood in seconds.

Body copy:          Connect and DBVoyager maps everything — tables,
                    columns, indexes, row counts, foreign keys, and
                    health scores — before you ask a single question.

                    Browse your schema like a map. Click any table to
                    inspect its columns, indexes, and health. See which
                    tables are bloated, which are missing indexes, and
                    which queries are hammering them.

Feature list:
  →  Interactive ER diagram with FK relationships
  →  Health score per table (A–F grade)
  →  Index coverage map
  →  Real-time row counts and size estimates
```

### Feature section 4 — Proactive monitoring (right text, left mockup)

```
Section eyebrow:    Proactive Monitoring

Headline:           Problems fixed before
                    you notice them.

Body copy:          DBVoyager doesn't wait for you to ask. It runs
                    health audits every 10 minutes, watches for new slow
                    queries, and alerts you the moment something changes.

                    Every morning it delivers a digest: what happened
                    overnight, what it fixed, what needs your attention.
                    Your database has a shift that never ends.

Feature list:
  →  Continuous health monitoring every 10 minutes
  →  Overnight digest delivered to your dashboard
  →  Slack and email alerts on critical findings
  →  Full audit trail of every action ever taken
```

---

### Stats / social proof bar

```
Stat 1 number:    < 38ms
Stat 1 label:     average query time after optimization

Stat 2 number:    5M+
Stat 2 label:     rows tested at scale

Stat 3 number:    100%
Stat 3 label:     PostgreSQL native — no vendor lock-in

Stat 4 number:    0
Stat 4 label:     DDL executed without your approval
```

### Open source section

```
Eyebrow:      Open Source

Headline:     Built in the open.
              Yours to inspect.

Body:         DBVoyager is open source. Read the code, audit the
              agent's decisions, self-host it, or contribute. We
              believe the tool watching your database should be one
              you can trust completely.

CTA button:   View on GitHub
Sub-CTA:      Star us if you find it useful ★
```

---

### Pricing section

```
Section headline:     One platform. Every database need.
Section subheading:   Start free. Upgrade when you need more.
```

**Tier 1 — Hobbyist (Free)**
```
Plan name:        Hobbyist
Price:            $0 / month
Tagline:          For solo engineers and side projects.

Features:
  ✓  1 database connection
  ✓  Automated health audit
  ✓  Schema inspector
  ✓  10 BI queries per day
  ✓  Community support

CTA:              Get started free
```

**Tier 2 — Team ($29/month) — RECOMMENDED**
```
Plan name:        Team
Price:            $29 / month
Tagline:          For engineering teams that move fast.
Badge:            Most popular

Features:
  ✓  Unlimited database connections
  ✓  Proactive monitoring every 10 minutes
  ✓  Unlimited BI queries
  ✓  KPI agents and dashboard
  ✓  Slack and email alerts
  ✓  Fix audit log
  ✓  Priority support

CTA:              Start 14-day free trial
Fine print:       No credit card required for trial
```

**Tier 3 — Mission Control (Custom)**
```
Plan name:        Mission Control
Price:            Custom pricing
Tagline:          For companies running critical infrastructure.

Features:
  ✓  Everything in Team
  ✓  SSO and SAML
  ✓  Role-based access (analyst / DBA / admin)
  ✓  SLA guarantee
  ✓  Dedicated support engineer
  ✓  On-premise deployment option
  ✓  Migration review assistant

CTA:              Talk to us
```

---

### Footer

```
Tagline under logo:   Navigate your data. Autonomously.

Column 1 — Product:
  Overview
  Features
  Pricing
  Changelog
  Roadmap

Column 2 — Features:
  Health Monitor
  Schema Inspector
  Query Optimizer
  BI Chat
  KPI Dashboard
  Proactive Alerts

Column 3 — Resources:
  Documentation
  API Reference
  Sample Databases
  Status

Column 4 — Developers:
  GitHub
  Open Source
  Self-hosting Guide
  Contributing

Column 5 — Company:
  About
  Blog
  Privacy Policy
  Terms of Service

Bottom bar left:    © 2025 DBVoyager. Built for engineers, by engineers.
Bottom bar right:   We protect your data. SOC 2 in progress.
```

---

## 2. AUTH PAGES

### Sign Up page

```
Left panel headline:    Your database never sleeps.
                        Neither does DBVoyager.

Left panel features:
  ✓  Proactive monitoring — 24/7
  ✓  One-click fix approvals
  ✓  Business intelligence, plain English

Right panel headline:   Create your account
Right panel subheading: Join engineers who stopped babysitting their databases.

Form labels:
  Full name             Full name
  Email                 Work email
  Password              Password
  Confirm password      Confirm password

Password hint:          8+ characters, one uppercase, one number

Primary button:         Create account

Toggle to login:        Already have an account? Sign in →

Fine print:             By creating an account you agree to our
                        Terms of Service and Privacy Policy.
```

### Login page

```
Left panel headline:    Welcome back.
                        Your database missed you.

Right panel headline:   Sign in to DBVoyager
Right panel subheading: Your databases are waiting.

Form labels:
  Email                 Email address
  Password              Password
  Forgot link:          Forgot password?

Primary button:         Sign in

Toggle to signup:       Don't have an account? Start for free →

Error — wrong password:       Incorrect email or password. Try again.
Error — account not found:    No account found with that email.
Error — too many attempts:    Too many attempts. Wait 60 seconds and try again.
```

---

## 3. DASHBOARD — TOP BAR

```
Project label:          DBVoyager
Environment badge:      PRODUCTION
Environment dropdown:   main ▾
Connect button:         Connect

Search placeholder:     Search or jump to... (⌘K)
Notification tooltip:   Alerts
Avatar tooltip:         Account settings
```

---

## 4. DASHBOARD — SIDEBAR

```
Section label 1:        CORE
Nav item 1:             Overview
Nav item 2:             AI Agent
Nav item 3:             Schema Visualizer
Nav item 4:             Table Browser

Section label 2:        INTELLIGENCE
Nav item 5:             Health Monitor
Nav item 6:             Query Optimizer
Nav item 7:             KPI Dashboard
Nav item 8:             Proactive Alerts

Section label 3:        MANAGEMENT
Nav item 9:             Connections
Nav item 10:            Audit Log
Nav item 11:            SQL Editor
Nav item 12:            Saved Queries

Bottom items:
  Settings
  Docs
  Sign out
```

---

## 5. DASHBOARD HOME

### Stats row (6 tile labels + sub-labels)

```
Tile 1:
  Label:      POSTGRES
  Sub:        Warnings · Errors

Tile 2:
  Label:      QUERY SPEED
  Sub:        P95 response time

Tile 3:
  Label:      CONNECTIONS
  Sub:        Active / max

Tile 4:
  Label:      TABLE BLOAT
  Sub:        Tables flagged

Tile 5:
  Label:      HEALTH SCORE
  Sub:        Overall grade

Tile 6:
  Label:      BI QUERIES
  Sub:        Queries today
```

### Agent alerts section

```
Section header:         Agent found {n} issues
Header sub:             Last checked {time} ago
Ask AI button:          Ask AI Agent

Zero state header:      All clear
Zero state body:        No issues detected. Your database is healthy.
                        DBVoyager checks again in 10 minutes.

Alert card — CRITICAL label:    CRITICAL
Alert card — WARNING label:     WARNING
Alert card — INFO label:        INFO

Alert category labels:
  missing_index   →   Missing Index
  slow_query      →   Slow Query
  bloat           →   Table Bloat
  lock            →   Lock Contention
  security        →   Security

Alert actions:
  Primary:    Propose Fix
  Secondary:  Diagnose
  Tertiary:   Dismiss
```

### Fix approval card (appears in right panel when fix is pending)

```
Card label:             Proposed Fix
Card sub:               Review before executing

SQL block label:        SQL to execute

Impact label:           Estimated improvement
Impact value format:    {before}ms → {after}ms

Approve button:         Approve & execute
Reject button:          Dismiss

Approving state:        Executing fix...
Success state:          Fix applied
Success sub:            Query time dropped from {before}ms to {after}ms

Error state:            Fix failed
Error sub:              The DDL did not execute. Check your database permissions.
```

### AI Agent chat panel

```
Panel header:           AI Agent
Live badge:             Live

Initial agent greeting: Good morning. I've completed my overnight audit.

                        I found {n} issue(s) that need attention. The most
                        critical: a missing index on {table}.{column} is
                        causing full sequential scans on {row_count} rows —
                        average query time is {ms}ms.

                        I've drafted a fix. Want me to walk you through it?

Thinking indicator:     Agent is thinking...

Input placeholder:      Ask about your data or database health...
Send button:            Send

Empty state:            Start a conversation
Empty sub:              Ask a question about your data, or let the agent
                        run an audit and tell you what it finds.

Reconnecting banner:    Connection lost. Reconnecting...
```

### Health score card (right panel)

```
Card header:            Health Score
Timestamp:              Last audited {time} ago

Grade labels:
  A   →   Excellent
  B   →   Good
  C   →   Fair
  D   →   Poor
  F   →   Critical

Sub-score labels:
  Query Speed
  Index Coverage
  Table Bloat
  Connections

Run audit button:       Run audit now
Running state:          Auditing...
```

### KPI mini cards (right panel, below health score)

```
Card 1 label:           Revenue today
Card 2 label:           New orders
Card 3 label:           Active users

Trend up label:         ↑ {pct}% vs yesterday
Trend down label:       ↓ {pct}% vs yesterday
Trend flat label:       — same as yesterday
```

### Schema table (bottom left)

```
Section header:         Schema overview

Column headers:
  Table       Rows        Size        Indexes     Health

Health dot tooltips:
  Green dot:    Healthy — no issues detected
  Amber dot:    Warning — {n} issue(s) found
  Red dot:      Critical — immediate attention needed

Empty state:    No schema loaded.
Empty sub:      Connect a database to inspect its schema.
```

### Fix history (bottom right)

```
Section header:         Fix history

Status labels:
  ✅  Applied
  ⏳  Pending approval
  ❌  Rejected

Entry format:
  {time} — "{description}"
  Before: {before}ms / After: {after}ms

Empty state:    No fixes applied yet.
Empty sub:      When the agent proposes and you approve a fix,
                it appears here with before and after metrics.
```

---

## 6. HEALTH MONITOR PAGE

```
Page title:             Database Health
Page subtitle:          Real-time health audit for {database_name}

Run audit button:       Run audit now
Running state:          Auditing your database...
Last run:               Last run {time} ago

Severity group headers:
  Critical issues ({n})
  Warnings ({n})
  Info ({n})

Finding detail labels:
  Affected table:       Affected table
  Affected query:       Slow query
  Suggested fix:        Suggested fix
  Fix button:           Propose this fix

Zero state:
  Header:   All clear
  Body:     Your database passed all health checks. DBVoyager
            will check again in 10 minutes and alert you if
            anything changes.
```

---

## 7. SCHEMA INSPECTOR PAGE

```
Page title:             Schema Inspector
Page subtitle:          {n} tables · {total_rows} total rows · last updated {time}

Table list header:      Tables
Search placeholder:     Search tables...

Column detail tab:      Columns
Index detail tab:       Indexes
Visualizer tab:         Diagram

Column table headers:   Name   Type   Nullable   Default
Index table headers:    Name   Columns   Unique   Size

Schema visualizer placeholder:
  Header:   Schema diagram
  Body:     Visual ER diagram coming in the next release.
            For now, inspect tables and indexes in the list.

Zero state:
  Header:   No schema loaded
  Body:     Connect a database to start inspecting its schema.
  Button:   Add connection
```

---

## 8. QUERY OPTIMIZER PAGE

```
Page title:             Query Optimizer
Page subtitle:          Identify and fix slow queries with AI assistance

Slow query list header: Slowest queries
Column headers:         Query   Avg time   Calls   Status

Status labels:
  Not analysed    →   —
  Analysed        →   Diagnosed
  Fix proposed    →   Fix ready
  Fix applied     →   Optimized ✓

Detail panel header:    Query analysis
Original query label:   Original query
Optimized label:        Optimized version
Cost comparison:        Estimated cost: {original} → {optimized} ({pct}% improvement)

Propose button:         Propose this optimization
Zero queries state:
  Header:   No slow queries detected
  Body:     Your queries are performing well. DBVoyager will
            flag any query that starts degrading automatically.
```

---

## 9. BUSINESS INTELLIGENCE CHAT PAGE

```
Page title:             BI Chat
Page subtitle:          Ask questions about your data in plain English

Saved sidebar header:   Saved queries
Save button tooltip:    Save this result
Re-run button:          Run again
Clear button:           Clear history

Result type labels:
  stat    →   (no label — just the number)
  bar     →   Bar chart
  line    →   Trend
  table   →   Table

Narrator label:         Insight
Follow-up label:        You might also ask

Export button:          Export CSV

Error — unsafe SQL:     Only SELECT queries are allowed in BI chat.
                        The agent generates safe, read-only SQL automatically.

Error — timeout:        This query took too long to run. Try narrowing
                        your question — for example, add a date range.

Zero state:
  Header:   Ask your first question
  Body:     Try: "Who are our top 10 customers by revenue this month?"
            or "Show me daily orders for the last 30 days."
```

---

## 10. KPI DASHBOARD PAGE

```
Page title:             KPI Dashboard
Page subtitle:          Track the metrics that matter to your business

Add KPI button:         Add metric
Edit button:            Edit
Remove button:          Remove

Add metric modal:
  Header:       Add a KPI metric
  Input label:  Describe your metric in plain English
  Placeholder:  e.g. Monthly revenue from enterprise customers
  Sub:          The agent will write the SQL and preview the result.
  Preview btn:  Preview
  Save btn:     Save metric
  Cancel:       Cancel

Metric card labels:
  Current value    (large number)
  vs last period   (trend line below)

Chart period selector:
  7 days   30 days   90 days   12 months

Zero state:
  Header:   No KPIs defined yet
  Body:     Add your first metric to start tracking the numbers
            that matter to your business.
  Button:   Add your first metric
```

---

## 11. AUDIT LOG PAGE

```
Page title:             Audit Log
Page subtitle:          Every action the agent has ever taken, in order

Search placeholder:     Search fixes, tables, or dates...

Column headers:         Time   Action   Table   Status   Impact

Status labels:
  Applied     →   ✅ Applied
  Pending     →   ⏳ Pending
  Rejected    →   ❌ Rejected

Impact format:          {before}ms → {after}ms
No impact label:        —

Zero state:
  Header:   No actions yet
  Body:     When you approve a fix, it's logged here permanently
            with its before and after performance metrics.
```

---

## 12. SAVED QUERIES PAGE

```
Page title:             Saved Queries
Page subtitle:          BI questions you've bookmarked for quick access

Search placeholder:     Search saved queries...

Card actions:
  Run again   →   Run again
  Delete      →   Delete

Date label:             Saved {date}
Chart type badge:       Bar   Line   Table   Stat

Zero state:
  Header:   No saved queries yet
  Body:     Star any BI result to save it here. Saved queries
            can be re-run with fresh data at any time.
  Button:   Go to BI Chat
```

---

## 13. CONNECTION MODAL

```
Modal title:            Add database connection
Modal subtitle:         Connect a PostgreSQL database to get started

Input label:            Connection string
Input placeholder:      postgresql://user:password@host:5432/database
Input hint:             Your connection is encrypted and never stored in plain text.

Label field:            Nickname (optional)
Label placeholder:      e.g. Production DB, Staging

Test button:            Test connection
Connect button:         Connect

Testing state:          Testing connection...
Success state:          Connection successful
Error state:            Could not connect. Check your credentials and try again.

SSL note:               We require SSL. Add ?sslmode=require to your connection string
                        if your host requires it.
```

---

## 14. EMPTY AND LOADING STATES

### Loading states (shown while data fetches)

```
Schema loading:         Inspecting schema...
Health audit loading:   Running health audit...
Agent thinking:         Agent is thinking...
Fix executing:          Executing fix...
BI query loading:       Running your query...
Connecting:             Connecting to database...
```

### Generic empty states

```
No connection:
  Header:   No database connected
  Body:     Add a connection to get started. DBVoyager will
            inspect the schema and run a health audit automatically.
  Button:   Add connection

No data returned:
  Header:   No results
  Body:     Your query ran successfully but returned no rows.
            Try adjusting your question or date range.

Feature not available:
  Header:   Not available on your plan
  Body:     Upgrade to Team to unlock {feature}.
  Button:   Upgrade to Team
```

---

## 15. TOAST NOTIFICATIONS

```
Signup success:         Welcome to DBVoyager.
Login success:          Welcome back.
Logout:                 Signed out.

Connection success:     Connected to {database_name}.
Connection failed:      Could not connect. Check your credentials.

Fix approved:           Fix applied. Query time: {before}ms → {after}ms.
Fix rejected:           Fix dismissed. Logged to audit trail.
Fix failed:             Fix failed. Check your database permissions.

Query saved:            Query saved to your library.
Query deleted:          Saved query removed.

Metric added:           KPI metric added to your dashboard.
Metric removed:         Metric removed.

Audit copied:           Connection string copied.

Generic error:          Something went wrong. Try again.
Generic success:        Done.
```

---

## 16. ERROR PAGES

### 404

```
Headline:       Lost in space.
Body:           This page doesn't exist. It may have been moved,
                deleted, or you may have followed a broken link.
Button:         Back to dashboard
```

### 500

```
Headline:       The engine room has a problem.
Body:           Something went wrong on our end. The team has been
                notified. Try refreshing — it usually fixes itself.
Button:         Refresh page
Secondary:      Check our status page →
```

### Connection lost

```
Banner:         Connection lost. Trying to reconnect...
Reconnected:    Back online.
```

---

## 17. ONBOARDING FLOW (first login)

```
Step 1 of 3:
  Headline:     Connect your first database.
  Body:         Paste a PostgreSQL connection string and DBVoyager
                will do the rest — schema inspection, health audit,
                and your first set of findings, automatically.
  Button:       Add connection

Step 2 of 3:
  Headline:     Your first audit is running.
  Body:         DBVoyager is inspecting your schema and checking for
                slow queries, missing indexes, and table bloat.
                This takes about 30 seconds.
  Status:       Auditing...

Step 3 of 3:
  Headline:     Your database, understood.
  Body:         Here's what we found. Review any issues the agent
                flagged, or start asking questions in BI Chat.
  Button:       Go to dashboard
  Skip:         Skip for now
```

---

## 18. META / SEO COPY

```
Page title (home):      DBVoyager — Your Autonomous Database Engineer
Meta description:       DBVoyager connects to your PostgreSQL database, runs
                        continuous health audits, proposes and executes fixes with
                        your approval, and answers business questions in plain English.

OG title:               DBVoyager — Your Autonomous Database Engineer
OG description:         The AI that watches your database so you don't have to.

Twitter card title:     DBVoyager
Twitter card desc:      AI-powered database health, query optimization, and business
                        intelligence — in one platform.

Favicon alt:            DBVoyager ship icon
```

---

## 19. LANGUAGE RULES FOR THE CODING AGENT

When rendering any dynamic copy, follow these rules exactly:

**Pluralization**
```
1 issue       →   Agent found 1 issue
2+ issues     →   Agent found {n} issues

1 table       →   1 table
2+ tables     →   {n} tables

1 query       →   1 query
2+ queries    →   {n} queries
```

**Timestamps — use relative time, not absolute, for anything under 24h**
```
< 1 min ago   →   just now
1–59 min      →   {n} minute(s) ago
1–23 hours    →   {n} hour(s) ago
1+ days       →   {date} at {time}  (e.g. Jul 14 at 3:27 PM)
```

**Numbers — always format large numbers with commas**
```
1000          →   1,000
4200          →   4,200
1000000       →   1,000,000
```

**Query time display**
```
< 1ms         →   < 1ms
1–999ms       →   {n}ms
1000ms+       →   {n}s  (e.g. 4.2s)
```

**Health grades — always show letter + descriptor together on first render**
```
A   →   A — Excellent
B   →   B — Good
C   →   C — Fair
D   →   D — Poor
F   →   F — Critical
```

**Severity badge text — always uppercase**
```
CRITICAL
WARNING
INFO
```

**Empty number display**
```
null or undefined value   →   —
zero queries/rows         →   0   (never hide zero, never show "None")
```

**Button loading states — always show action verb + ellipsis**
```
Connecting...
Auditing...
Running...
Executing...
Saving...
```

**Never use these words anywhere in the UI:**
```
✗  successfully   (the action IS the success)
✗  please         (UI doesn't ask favors)
✗  click here     (describe the destination)
✗  leverage
✗  seamless
✗  unlock
✗  empower
✗  revolutionary
✗  game-changing
✗  cutting-edge
✗  simply
✗  just
✗  easy
```