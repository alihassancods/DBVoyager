# DBVoyager Frontend — AI Agent Planning Prompt

Paste this entire file as your first message to the AI coding agent (Codex, Cursor,
Claude Code, or any agentic IDE). Read every section before writing a single line of
code. This prompt is the single source of truth for how the frontend is built.

---

## WHO YOU ARE AND WHAT YOU ARE BUILDING

You are a senior frontend engineer building the DBVoyager web application — an
AI-powered autonomous database engineering and business intelligence platform.

The backend is a FastAPI Python application already running at `http://localhost:8000`.
All API endpoints are already built and documented. Your only job is to build the
React frontend that calls those endpoints and renders a production-grade UI.

You will build in this exact order — do not skip ahead:

1. Auth pages (Sign Up + Login) — wire to existing API
2. Landing page — use existing sample code as base
3. Dashboard — full feature set across all modules

---

## TECH STACK — FIXED, DO NOT DEVIATE

These choices optimise for: fastest development time, easiest maintenance,
production reliability, and zero configuration overhead.

| Layer | Choice | Why |
|---|---|---|
| Framework | React 18 + Vite | Fastest dev server, instant HMR, minimal config |
| Language | TypeScript (strict) | Catch bugs at compile time, not runtime |
| Routing | React Router v6 | Battle-tested, file-based mental model |
| Styling | Tailwind CSS v3 | No CSS files to maintain, consistent design tokens |
| Component lib | shadcn/ui | Copy-paste components, fully owned, Tailwind-native |
| State — server | TanStack Query v5 | Caching, loading states, error states — automatic |
| State — client | Zustand | Simple, tiny, no boilerplate |
| Forms | React Hook Form + Zod | Type-safe validation, zero re-renders |
| HTTP client | Axios with interceptors | Auth header injection, global error handling |
| Charts | Recharts | React-native, composable, works out of the box |
| WebSocket | native browser WebSocket in a custom hook | No extra library needed |
| Icons | Lucide React | Consistent, tree-shakeable |
| Toasts | Sonner | One line to show a toast anywhere |
| Date formatting | date-fns | Tiny, tree-shakeable |

**Do not add any library not in this list without a documented reason in a comment.**

---

## PROJECT STRUCTURE — CREATE THIS EXACTLY

```
frontend/
├── public/
│   └── favicon.svg           # Ship icon SVG (create a simple one)
├── src/
│   ├── main.tsx              # App entry point
│   ├── App.tsx               # Router setup + providers
│   ├── vite-env.d.ts
│   │
│   ├── lib/
│   │   ├── api.ts            # Axios instance + all API functions
│   │   ├── queryClient.ts    # TanStack Query client config
│   │   ├── tokens.ts         # Design tokens as JS constants (colors, etc.)
│   │   └── utils.ts          # cn() helper + shared utils
│   │
│   ├── store/
│   │   ├── authStore.ts      # Zustand: user, token, isAuthenticated
│   │   └── agentStore.ts     # Zustand: chat messages, pending fixes, ws state
│   │
│   ├── hooks/
│   │   ├── useAuth.ts        # Login, signup, logout mutations
│   │   ├── useAgentChat.ts   # WebSocket connection + message handling
│   │   ├── useHealthAudit.ts # Health audit query + polling
│   │   ├── useSchema.ts      # Schema inspection query
│   │   └── useBiQuery.ts     # BI query mutation + result state
│   │
│   ├── types/
│   │   ├── auth.ts           # User, LoginRequest, SignupRequest, AuthResponse
│   │   ├── health.ts         # HealthFinding, HealthAuditResult, HealthScore
│   │   ├── schema.ts         # DatabaseSchema, TableInfo, ColumnInfo
│   │   ├── fixes.ts          # FixProposal, FixStatus, BenchmarkResult
│   │   ├── bi.ts             # BiQueryResult, NarratorResult, ChartType
│   │   └── ws.ts             # WSMessage union type (all WebSocket message shapes)
│   │
│   ├── components/
│   │   ├── ui/               # shadcn/ui components (auto-generated, don't edit)
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── TopBar.tsx
│   │   │   └── DashboardLayout.tsx
│   │   ├── auth/
│   │   │   ├── LoginForm.tsx
│   │   │   └── SignupForm.tsx
│   │   ├── health/
│   │   │   ├── AlertCard.tsx       # Single proactive issue card
│   │   │   ├── AlertsGrid.tsx      # "Agent found N issues" section
│   │   │   ├── HealthScoreCard.tsx # Letter grade + breakdown
│   │   │   └── FixApprovalCard.tsx # Pending fix with approve/reject
│   │   ├── schema/
│   │   │   ├── SchemaTable.tsx     # Table list with stats
│   │   │   └── SchemaVisualizer.tsx # ER diagram (future — placeholder ok for now)
│   │   ├── bi/
│   │   │   ├── BiChat.tsx          # Chat interface for BI questions
│   │   │   ├── BiResult.tsx        # Auto-renders chart or table from result
│   │   │   ├── ChipSuggestions.tsx # Follow-up question pills
│   │   │   └── chartUtils.ts       # detectChartType() pure function
│   │   ├── kpi/
│   │   │   ├── KpiCard.tsx         # Single KPI with sparkline
│   │   │   └── KpiGrid.tsx         # Row of KPI cards
│   │   └── shared/
│   │       ├── SeverityBadge.tsx   # CRITICAL / WARNING / INFO badge
│   │       ├── CodeBlock.tsx       # SQL display with syntax highlight
│   │       ├── LoadingSpinner.tsx
│   │       └── EmptyState.tsx
│   │
│   └── pages/
│       ├── LandingPage.tsx
│       ├── LoginPage.tsx
│       ├── SignupPage.tsx
│       └── dashboard/
│           ├── DashboardHome.tsx     # Overview — alerts + chat + health score
│           ├── HealthMonitorPage.tsx # Full health audit details
│           ├── SchemaPage.tsx        # Schema inspector + visualizer
│           ├── QueryOptimizerPage.tsx
│           ├── BiChatPage.tsx        # Full-screen BI chat
│           ├── KpiDashboardPage.tsx  # KPI charts + agents
│           ├── AuditLogPage.tsx
│           └── SavedQueriesPage.tsx
│
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## DESIGN TOKENS — USE THESE EVERYWHERE, NEVER HARDCODE COLORS

Configure these in `tailwind.config.ts` as custom colors. Reference them as
`bg-voyager-navy`, `text-voyager-blue`, etc. throughout all components.

```typescript
// tailwind.config.ts — colors section
colors: {
  voyager: {
    navy:       '#050C1A',   // background primary
    navy2:      '#091629',   // background secondary
    surface:    '#0D1F38',   // card/panel background
    surface2:   '#112844',   // slightly lighter surface (hover states)
    blue:       '#0EA5E9',   // accent primary — CTAs, active states, highlights
    'blue-light': '#38BDF8', // accent secondary — hover
    'blue-glow': 'rgba(14, 165, 233, 0.15)', // border glow
    success:    '#10B981',   // healthy metrics
    warning:    '#F59E0B',   // warnings
    critical:   '#EF4444',   // critical issues
    'text-primary':   '#F1F5F9',
    'text-secondary': '#94A3B8',
    'text-muted':     '#475569',
    border:     'rgba(14, 165, 233, 0.15)',
    'border-strong': 'rgba(14, 165, 233, 0.3)',
  }
}
```

Also add this global CSS to `src/index.css`:
```css
body {
  background-color: #050C1A;
  color: #F1F5F9;
  font-family: 'Inter', system-ui, sans-serif;
}

/* Standard card style — apply this class everywhere */
.voyager-card {
  background: #0D1F38;
  border: 1px solid rgba(14, 165, 233, 0.15);
  border-radius: 12px;
  box-shadow: 0 0 20px rgba(14, 165, 233, 0.05);
}

/* Blue glow on focus/hover */
.voyager-glow:hover, .voyager-glow:focus {
  border-color: rgba(14, 165, 233, 0.4);
  box-shadow: 0 0 12px rgba(14, 165, 233, 0.15);
}

/* Monospace for SQL */
.sql-text {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
}
```

---

## STEP 1 — AUTH PAGES (BUILD THIS FIRST, GET IT WORKING BEFORE MOVING ON)

### 1A. API layer (`src/lib/api.ts`)

Create the Axios instance first. Everything else depends on it.

```typescript
// src/lib/api.ts
import axios from 'axios';
import { useAuthStore } from '@/store/authStore';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  headers: { 'Content-Type': 'application/json' },
});

// Inject auth token automatically on every request
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Handle 401 globally — clear auth and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ── AUTH ─────────────────────────────────────────────
export const authApi = {
  signup: (data: SignupRequest) =>
    api.post<AuthResponse>('/auth/signup', data).then(r => r.data),
  login: (data: LoginRequest) =>
    api.post<AuthResponse>('/auth/login', data).then(r => r.data),
  me: () =>
    api.get<User>('/auth/me').then(r => r.data),
};

// ── CONNECT ──────────────────────────────────────────
export const connectApi = {
  connect: (data: ConnectRequest) =>
    api.post<ConnectResponse>('/connect', data).then(r => r.data),
};

// ── HEALTH ───────────────────────────────────────────
export const healthApi = {
  getAudit: () =>
    api.get<HealthAuditResult>('/health').then(r => r.data),
};

// ── FIXES ────────────────────────────────────────────
export const fixesApi = {
  approve: (fixId: string) =>
    api.post<BenchmarkResult>(`/approve/${fixId}`).then(r => r.data),
  reject: (fixId: string) =>
    api.post(`/reject/${fixId}`).then(r => r.data),
};

// ── BI ───────────────────────────────────────────────
export const biApi = {
  savedQueries: () =>
    api.get<SavedQuery[]>('/bi/saved-queries').then(r => r.data),
  saveQuery: (data: SaveQueryRequest) =>
    api.post('/bi/save-query', data).then(r => r.data),
};
```

**IMPORTANT:** All type imports in api.ts come from `src/types/`. Define the types
there first, then import. Never define types inline in api.ts.

### 1B. Auth store (`src/store/authStore.ts`)

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      setAuth: (user, token) => set({ user, token, isAuthenticated: true }),
      logout: () => set({ user: null, token: null, isAuthenticated: false }),
    }),
    { name: 'dbvoyager-auth' }  // persists to localStorage
  )
);
```

### 1C. Auth hook (`src/hooks/useAuth.ts`)

```typescript
import { useMutation } from '@tanstack/react-query';
import { authApi } from '@/lib/api';
import { useAuthStore } from '@/store/authStore';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

export function useLogin() {
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  return useMutation({
    mutationFn: authApi.login,
    onSuccess: (data) => {
      setAuth(data.user, data.access_token);
      toast.success('Welcome back!');
      navigate('/dashboard');
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || 'Invalid credentials');
    },
  });
}

export function useSignup() {
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  return useMutation({
    mutationFn: authApi.signup,
    onSuccess: (data) => {
      setAuth(data.user, data.access_token);
      toast.success('Account created! Welcome to DBVoyager.');
      navigate('/dashboard');
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || 'Signup failed. Please try again.');
    },
  });
}

export function useLogout() {
  const { logout } = useAuthStore();
  const navigate = useNavigate();

  return () => {
    logout();
    navigate('/login');
  };
}
```

### 1D. Zod schemas for forms (`src/types/auth.ts`)

```typescript
import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

export const signupSchema = z.object({
  full_name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Enter a valid email address'),
  password: z.string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Must contain at least one uppercase letter')
    .regex(/[0-9]/, 'Must contain at least one number'),
  confirm_password: z.string(),
}).refine(d => d.password === d.confirm_password, {
  message: "Passwords don't match",
  path: ['confirm_password'],
});

export type LoginRequest = z.infer<typeof loginSchema>;
export type SignupRequest = Omit<z.infer<typeof signupSchema>, 'confirm_password'>;

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'analyst' | 'dba' | 'admin';
  created_at: string;
}

export interface AuthResponse {
  user: User;
  access_token: string;
  token_type: 'bearer';
}
```

### 1E. LoginForm component (`src/components/auth/LoginForm.tsx`)

Style guide for auth pages:
- Full viewport height, centered content
- Left panel (60%): deep navy background, logo top-left, large tagline centered,
  3 feature badges bottom-left. Hidden on mobile.
- Right panel (40%): slightly lighter surface (#0D1F38), form centered vertically
- Input fields: dark background (#091629), blue focus ring, rounded-lg
- Primary button: electric blue (#0EA5E9), full width, rounded-lg, bold text
- All error messages: red text below the field, small font
- On submit: button shows loading spinner, disabled state

Form fields for Login: Email, Password
Form fields for Signup: Full Name, Email, Password, Confirm Password

Link between pages: Login page has "Don't have an account? Sign up →" at bottom
Signup page has "Already have an account? Sign in →" at bottom

### 1F. Protected route wrapper

```typescript
// src/components/shared/ProtectedRoute.tsx
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';

export function ProtectedRoute() {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />;
}
```

### 1G. Router setup (`src/App.tsx`)

```typescript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { queryClient } from '@/lib/queryClient';
import { ProtectedRoute } from '@/components/shared/ProtectedRoute';

// Pages
import LandingPage from '@/pages/LandingPage';
import LoginPage from '@/pages/LoginPage';
import SignupPage from '@/pages/SignupPage';
import DashboardLayout from '@/components/layout/DashboardLayout';
import DashboardHome from '@/pages/dashboard/DashboardHome';
// ... other dashboard pages

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />

          {/* All dashboard routes are protected */}
          <Route element={<ProtectedRoute />}>
            <Route element={<DashboardLayout />}>
              <Route path="/dashboard" element={<DashboardHome />} />
              <Route path="/dashboard/health" element={<HealthMonitorPage />} />
              <Route path="/dashboard/schema" element={<SchemaPage />} />
              <Route path="/dashboard/optimizer" element={<QueryOptimizerPage />} />
              <Route path="/dashboard/bi" element={<BiChatPage />} />
              <Route path="/dashboard/kpi" element={<KpiDashboardPage />} />
              <Route path="/dashboard/audit" element={<AuditLogPage />} />
              <Route path="/dashboard/saved" element={<SavedQueriesPage />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster theme="dark" position="top-right" />
    </QueryClientProvider>
  );
}
```

### STEP 1 VERIFICATION CHECKLIST

Before moving to Step 2, verify all of these pass:

- [ ] `npm run dev` starts with zero TypeScript errors
- [ ] `/signup` renders the split-panel form
- [ ] Submitting signup with valid data hits `POST /api/auth/signup` (check Network tab)
- [ ] Successful signup stores token in localStorage and redirects to `/dashboard`
- [ ] `/login` renders correctly
- [ ] Submitting login with valid credentials redirects to `/dashboard`
- [ ] Submitting with wrong password shows toast error "Invalid credentials"
- [ ] Visiting `/dashboard` while logged out redirects to `/login`
- [ ] Visiting `/dashboard` while logged in shows the dashboard (even if empty)
- [ ] Refreshing the page keeps you logged in (token persisted in localStorage)
- [ ] Form validation shows inline errors (email format, password length, etc.)

**DO NOT START STEP 2 UNTIL ALL CHECKBOXES PASS.**

---

## STEP 2 — LANDING PAGE

Use the existing code in `sample/` as the structural and visual base. Do not discard
it — adapt it to use the DBVoyager design tokens defined above.

Landing page sections in order:
1. Sticky navbar: logo + nav links + "Sign In" + "Start for Free" CTA
2. Hero: headline + subheading + two CTA buttons + floating dashboard preview mockup
3. Feature strip: 6 feature pills (AI Health Audit, Schema Inspector, Query Optimizer,
   BI Chat, KPI Agents, Proactive Alerts)
4. Three alternating feature sections (text + mockup screenshot or illustration)
5. Social proof bar: 3 stats (< 38ms, 5M+ rows, 100% PostgreSQL)
6. Open Source section with GitHub link
7. Pricing section: 3 tiers
8. Footer: 5-column link grid

Nav links:
- "Sign In" → `/login`
- "Start for Free" → `/signup`
- "View Demo" in hero → `/signup`
- "Start Your Project" in hero → `/signup`

The landing page has no API calls. It is fully static. Focus entirely on visual
fidelity to the DBVoyager design system.

### STEP 2 VERIFICATION CHECKLIST

- [ ] All nav links work (Sign In → /login, Start for Free → /signup)
- [ ] Page is responsive (looks good at 375px mobile width)
- [ ] No layout breaks at any viewport width
- [ ] All 7 sections render correctly

---

## STEP 3 — DASHBOARD (MOST IMPORTANT — MOST TIME HERE)

### 3A. Layout components

**Sidebar (`src/components/layout/Sidebar.tsx`):**
- Fixed left, 240px wide, full height, `#091629` background
- Top: DBVoyager logo (ship icon + wordmark)
- Three nav groups with labels:
  - CORE: Overview, AI Agent Chat, Schema Visualizer, Table Browser
  - INTELLIGENCE: Health Monitor (with red badge for issue count), Query Optimizer,
    KPI Dashboard, Proactive Alerts
  - MANAGEMENT: Connections, Audit Log, SQL Editor, Saved Queries
- Bottom: Settings, Docs, user avatar + email + logout button
- Active item: electric blue left border (3px) + `#112844` background
- Icons from Lucide React

**TopBar (`src/components/layout/TopBar.tsx`):**
- Project name "DBVoyager" + "PRODUCTION" green badge + environment dropdown
- "Connect" button (outlined, green) — opens connection modal
- Right: Search (Ctrl+K placeholder), notification bell, user avatar

### 3B. Dashboard Home (`src/pages/dashboard/DashboardHome.tsx`)

Layout: Three sections stacked vertically.

**Section 1 — Stats row (6 tiles, horizontal):**

Fetch from `GET /api/health` on mount. Poll every 30 seconds.

```
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  POSTGRES   │ │ QUERY SPEED │ │ CONNECTIONS │ │ TABLE BLOAT │ │   HEALTH    │ │  BI QUERIES │
│ Warnings: 0 │ │  P95: 38ms  │ │   12/100    │ │  3 flagged  │ │   B+ / 82   │ │   14 today  │
│ Errors: 4   │ │  ↓ trending │ │             │ │             │ │             │ │             │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

Each tile: voyager-card class, icon top-left, metric name small grey text, value
large white text, sub-metric smaller grey text.

**Section 2 — Agent Alerts ("Agent found N issues"):**

Mirroring the Supabase advisor panel from the screenshot exactly:
- Section header: shield/alert icon + "Agent found {count} issues" + 
  "Ask AI Agent" button (right-aligned, with sparkle icon)
- 4-column card grid:
  - Each card: voyager-card, red left border for CRITICAL, amber for WARNING
  - Card content: severity badge (top-left) + "CRITICAL"/"WARNING" label (top-right)
  - Title: bold white, 14px
  - Description: grey text, 13px, 2 lines max
  - Bottom: action button ("Propose Fix", "Diagnose", "Fix Now", "Enable RLS")
- When a fix is pending approval: card shows SQL code block + "Approve & Execute" 
  button (green) + "Dismiss" button (grey)

Fetch: `GET /api/health` for findings. Filter to severity === 'critical' | 'warning'.
When "Propose Fix" is clicked: send message to AI agent via WebSocket.
When "Approve & Execute" is clicked: call `POST /api/approve/{fix_id}`.
After approval: show BenchmarkResult (before/after ms) in a green toast + update card.

**Section 3 — Two columns:**

Left (60%) — AI Agent Chat Panel:
- Header: "AI Agent" + green pulsing "Live" dot
- Message list: scrollable, agent messages left-aligned (robot avatar), user messages 
  right-aligned
- Message types to handle from WebSocket:
  - `type: "token"` → append to current streaming agent message
  - `type: "fix_proposal"` → render FixApprovalCard inline in chat
  - `type: "benchmark"` → render before/after timing card
  - `type: "error"` → render error message in chat
- Input: dark input field + send button + "Ask about your data or database..." placeholder
- WebSocket connects to `ws://localhost:8000/api/chat` on component mount
- On mount: send initial message to trigger the proactive greeting

```typescript
// useAgentChat hook behaviour:
// 1. On mount: connect to ws://localhost:8000/api/chat
// 2. Store in agentStore: messages[], isConnected, pendingFix
// 3. On incoming 'token': append text to last assistant message
// 4. On incoming 'fix_proposal': add FixProposalMessage to messages array
// 5. On incoming 'benchmark': add BenchmarkMessage to messages array
// 6. sendMessage(text): sends { type: 'message', content: text } over WS
// 7. On WS close: show reconnect banner, attempt reconnect after 3s
```

Right (40%) — Health Score + KPI Snapshot:
- HealthScoreCard: large letter grade (A–F) in electric blue, circular ring SVG,
  4 sub-scores (Query Speed, Index Coverage, Bloat, Connections) each with grade + 
  progress bar
- Below: 3 KpiCards (Revenue Today, New Orders, Active Users) each with:
  - Large number (bold white)
  - Trend arrow + percentage change
  - Sparkline chart (Recharts LineChart, small, 80px tall)

### 3C. Health Monitor Page (`/dashboard/health`)

Full-page detailed view of all health findings.

Layout:
- Top: "Database Health" heading + "Run Audit Now" button (triggers fresh health fetch)
- Health score overview card (same as dashboard but larger, with timestamp)
- Findings list: grouped by severity (CRITICAL first, then WARNING, then INFO)
- Each finding card: expanded version with full description, affected table, 
  suggested fix in a code block, "Propose Fix" button
- Fix History table at bottom: date, description, status, before/after timing

Fetch: `GET /api/health` — cache 30s, show stale while revalidating.

### 3D. Schema Inspector Page (`/dashboard/schema`)

Layout: Two panels side by side.

Left panel (40%) — Table list:
- Fetch: `GET /api/connect` (schema from last connection, stored in cache)
- Table of: Table Name | Rows | Size | Indexes | Health dot
- Click a row → right panel shows that table's details

Right panel (60%) — Table detail:
- Table name as heading
- Columns tab: Name | Type | Nullable | Default — clean table
- Indexes tab: Name | Columns | Unique | Size
- Schema Visualizer: placeholder card with "Schema diagram coming soon" if not yet
  built, otherwise a simple SVG node graph showing FK relationships

### 3E. Query Optimizer Page (`/dashboard/optimizer`)

Layout: Two panels stacked.

Top — Slow Query List:
- Fetch from health audit's slow query findings
- Table: Query (truncated) | Avg Time | Calls | Proposed Fix status
- Click a row to open the optimization detail below

Bottom — Optimization Detail:
- Original query in CodeBlock component
- EXPLAIN output rendered as tree or text
- Agent's proposed optimization in CodeBlock
- Before/after cost comparison (estimated)
- "Propose Fix" → "Approve" flow same as dashboard

### 3F. BI Chat Page (`/dashboard/bi`)

Full-screen two-panel layout:

Left panel (30%) — Saved Queries sidebar:
- "Saved Queries" heading + count
- List of saved questions — click to replay
- "Clear history" button at bottom

Right panel (70%) — Full BI chat:
- Same chat UI as dashboard but full-screen, more space
- BI results render inline as:
  - `detectChartType(columns, rows)` returns 'stat' | 'bar' | 'line' | 'table'
  - stat → large centered number, label below
  - bar → Recharts BarChart, voyager-blue fill, dark background
  - line → Recharts LineChart, electric blue line
  - table → clean dark table, alternating row backgrounds
- Below every chart: narrator text (2-sentence AI summary, italic, text-secondary)
- Below narrator: 3 follow-up chip pills (from API response)
- Star icon on every result → calls `POST /api/bi/save-query`

### 3G. KPI Dashboard Page (`/dashboard/kpi`)

Layout: Grid of KPI cards + one large chart.

Top row: 4 KpiCards (user-defined metrics — Revenue, Orders, Churn, Active Users)
Each card: metric name, current value, trend vs last period, sparkline

Main area: Large Recharts chart (line chart, last 30 days) for selected metric.
Metric selector tabs above the chart.

"Add KPI" button → modal: text input for natural language metric definition
("Monthly revenue from enterprise customers") → calls AI agent to generate SQL
→ shows preview result → on confirm, saves metric.

### 3H. Audit Log Page (`/dashboard/audit`)

Simple table fetched from `GET /api/audit-log` (if endpoint exists, else local SQLite
data via a dedicated endpoint):

Columns: Timestamp | Action | Table Affected | SQL (expandable) | Before ms | After ms | Status

Status badges: ✅ Applied | ⏳ Pending | ❌ Rejected

Sortable by timestamp (default: newest first). Search/filter bar at top.

### 3I. Saved Queries Page (`/dashboard/saved`)

Fetch from `GET /api/bi/saved-queries`.
Grid of query cards: question text, chart type badge, created date, "Run Again" button.
"Run Again" → navigates to `/dashboard/bi` with query pre-filled.

---

## WEBSOCKET STATE MANAGEMENT

```typescript
// src/store/agentStore.ts
import { create } from 'zustand';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  type: 'text' | 'fix_proposal' | 'benchmark' | 'bi_result';
  metadata?: FixProposalMessage | BenchmarkMessage | BiQueryResult;
  timestamp: Date;
  isStreaming?: boolean;
}

interface AgentState {
  messages: Message[];
  isConnected: boolean;
  isThinking: boolean;
  pendingFix: FixProposalMessage | null;
  addMessage: (msg: Message) => void;
  appendToken: (token: string) => void;  // appends to last streaming message
  setConnected: (v: boolean) => void;
  setThinking: (v: boolean) => void;
  setPendingFix: (fix: FixProposalMessage | null) => void;
  clearMessages: () => void;
}

export const useAgentStore = create<AgentState>()((set) => ({
  messages: [],
  isConnected: false,
  isThinking: false,
  pendingFix: null,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendToken: (token) => set((s) => {
    const msgs = [...s.messages];
    const last = msgs[msgs.length - 1];
    if (last?.role === 'assistant' && last.isStreaming) {
      msgs[msgs.length - 1] = { ...last, content: last.content + token };
    }
    return { messages: msgs };
  }),
  setConnected: (v) => set({ isConnected: v }),
  setThinking: (v) => set({ isThinking: v }),
  setPendingFix: (fix) => set({ pendingFix: fix }),
  clearMessages: () => set({ messages: [] }),
}));
```

---

## SHARED COMPONENT SPECS

### SeverityBadge
```typescript
// Props: severity: 'critical' | 'warning' | 'info'
// critical → red background, "CRITICAL" text
// warning → amber background, "WARNING" text  
// info → blue background, "INFO" text
// Size: text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wide
```

### CodeBlock
```typescript
// Props: code: string, language?: string, showCopy?: boolean
// Dark surface background (#091629), JetBrains Mono font
// Copy button top-right (Lucide Copy icon) → copies to clipboard → shows "Copied!"
// Scrollable horizontally for long SQL
```

### FixApprovalCard
```typescript
// Shown when agent proposes a DDL fix
// Props: fix: FixProposalMessage, onApprove, onReject, isLoading
// Layout:
// - Header: "Proposed Fix" label + fix_id in muted text
// - Description: agent's explanation in text-secondary
// - CodeBlock with the SQL
// - Estimated improvement: "4,200ms → 38ms" in green
// - Two buttons: "Approve & Execute" (green, filled) + "Dismiss" (grey, ghost)
// - When isLoading: spinner on approve button, both buttons disabled
// - After approval: shows BenchmarkResult with actual before/after
```

### EmptyState
```typescript
// Props: icon: LucideIcon, title: string, description: string, action?: ReactNode
// Centered in its container
// Icon: 48px, text-voyager-text-secondary
// Title: 18px bold, text-voyager-text-primary
// Description: 14px, text-voyager-text-secondary
// Action: optional button below
```

---

## ERROR HANDLING STANDARDS

Every data-fetching component must handle three states. Never skip loading or error.

```typescript
// Pattern to use in every page component:
const { data, isLoading, isError, error } = useQuery(...)

if (isLoading) return <LoadingSpinner label="Loading health data..." />
if (isError) return (
  <EmptyState
    icon={AlertCircle}
    title="Could not load data"
    description={error?.message || "Check your database connection and try again."}
    action={<Button onClick={() => refetch()}>Try again</Button>}
  />
)
```

---

## ENVIRONMENT VARIABLES

Create `.env` and `.env.example` in the frontend root:

```env
# .env
VITE_API_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/api

# .env.example (commit this)
VITE_API_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/api
```

Access in code: `import.meta.env.VITE_API_URL` — never hardcode localhost URLs.

---

## PACKAGE.JSON SCRIPTS

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "type-check": "tsc --noEmit",
    "lint": "eslint src --ext .ts,.tsx"
  }
}
```

Run `npm run type-check` after completing each step. Zero TypeScript errors is
the bar. Do not proceed to the next step with type errors unresolved.

---

## OVERALL RULES FOR THE AI AGENT

1. **Types first.** Before writing any component or hook, define its types in
   `src/types/`. This prevents type errors cascading through the codebase.

2. **One component, one job.** A component either fetches data OR renders it,
   not both. Use hooks for fetching, components for rendering.

3. **Never hardcode.** No inline hex colors, no hardcoded URLs, no magic numbers.
   Colors come from Tailwind config. URLs come from env variables. Numbers come
   from constants.

4. **Loading + error states are not optional.** Every page that fetches data must
   handle isLoading, isError, and the empty/zero-data case.

5. **Check before creating.** Before writing a new component, check if one already
   exists in `src/components/`. Extend existing components rather than duplicating.

6. **TypeScript strict mode.** No `any` types. No `@ts-ignore`. If you don't know
   the type, define it properly in `src/types/`.

7. **Run the verification checklist after each step.** Do not start the next step
   until all checkboxes in the current step's checklist pass.

8. **If an API endpoint doesn't exist yet**, add a `// TODO: wire to POST /api/xxx`
   comment and use a mock response so the UI still renders. Do not block UI
   development on missing backend endpoints.

---

## FINAL STEP VERIFICATION (after all three steps)

- [ ] Auth flow works end-to-end: signup → dashboard → logout → login → dashboard
- [ ] Token persists on browser refresh
- [ ] Landing page renders on `/` with all 7 sections
- [ ] All sidebar nav links navigate to the correct pages
- [ ] Dashboard home shows stats row, alerts grid, chat panel, health score
- [ ] WebSocket connects to `/api/chat` and receives tokens correctly
- [ ] Approve fix flow: alert card → approve button → loading → benchmark result shown
- [ ] BI chat: type a question → bar chart or table renders inline → narrator text below
- [ ] All pages handle loading and error states
- [ ] `npm run type-check` passes with zero errors
- [ ] `npm run build` produces a successful production build
```