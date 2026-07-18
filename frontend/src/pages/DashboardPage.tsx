import { useEffect, useState } from 'react';
import { authFetch } from '../lib/auth';
import { dashboardCacheKey, invalidateDashboardConnection, readDashboardCache, writeDashboardCache } from '../lib/dashboardCache';

type Connection = { connection_id: string; display_name: string; status?: string; last_analyzed_at?: string };
type Credentials = { display_name: string; connection_url: string };
type Section = 'overview' | 'bi-chat' | 'kpis' | 'health-checks' | 'schema' | 'slow-queries' | 'statistics/tables' | 'statistics/indexes' | 'statistics/locks' | 'audit-events' | 'settings';
const navigation: [string, Section][] = [['Overview', 'overview'], ['BI Chat', 'bi-chat'], ['KPI Agent', 'kpis'], ['Health checks', 'health-checks'], ['Schema visualizer', 'schema'], ['Slow queries', 'slow-queries'], ['Table statistics', 'statistics/tables'], ['Index statistics', 'statistics/indexes'], ['Lock statistics', 'statistics/locks'], ['Audit trail', 'audit-events'], ['Settings', 'settings']];

class ApiError extends Error { constructor(readonly status: number, message: string) { super(message); } }
const inFlight = new Map<string, Promise<Record<string, unknown>>>();

async function json(path: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const response = await authFetch(path, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, String(body.detail || 'Request failed'));
  return body;
}

async function cachedJson(connectionId: string, resource: string, path: string, ttlMs: number): Promise<{ payload: Record<string, unknown>; cached: boolean }> {
  const key = dashboardCacheKey(connectionId, resource); const cached = readDashboardCache(key);
  if (cached && Date.now() - cached.fetchedAt < ttlMs) return { payload: cached.payload, cached: true };
  const pending = inFlight.get(key);
  if (pending) return { payload: await pending, cached: false };
  const request = (async () => {
    const response = await authFetch(path, { headers: cached?.etag ? { 'If-None-Match': cached.etag } : {} });
    if (response.status === 304 && cached) return cached.payload;
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiError(response.status, String(body.detail || 'Request failed'));
    const payload = body as Record<string, unknown>;
    writeDashboardCache(key, { payload, fetchedAt: Date.now(), etag: response.headers.get('etag') || undefined });
    return payload;
  })();
  inFlight.set(key, request);
  try { return { payload: await request, cached: false }; } finally { inFlight.delete(key); }
}

function value(item: unknown, key: string): string {
  const data = item as Record<string, unknown>;
  const result = data[key];
  if (result === null || result === undefined) return '—';
  if (key === 'query') return String(result).replace(/\s+/g, ' ').trim().slice(0, 108) + (String(result).length > 108 ? '…' : '');
  return String(result);
}

function metric(number: unknown, suffix = ''): string {
  const parsed = Number(number);
  return Number.isFinite(parsed) ? `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(parsed)}${suffix}` : '—';
}

function rows(payload: Record<string, unknown>): Record<string, unknown>[] {
  const data = payload.data;
  return Array.isArray(data) ? data as Record<string, unknown>[] : [];
}

export default function DashboardPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState('');
  const [section, setSection] = useState<Section>('overview');
  const [data, setData] = useState<Record<string, unknown>>({});
  const [progress, setProgress] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showConnectionModal, setShowConnectionModal] = useState(false);

  const waitForRun = async (path: string, label: string) => {
    const response = await authFetch(path);
    if (!response.ok || !response.body) throw new Error(`Could not collect ${label}.`);
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    while (true) {
      const part = await reader.read(); if (part.done) return;
      buffer += decoder.decode(part.value, { stream: true });
      const messages = buffer.split('\n\n'); buffer = messages.pop() || '';
      for (const message of messages) {
        const event = message.match(/^event: (.+)$/m)?.[1]; const raw = message.match(/^data: (.+)$/m)?.[1];
        if (!raw) continue; const eventData = JSON.parse(raw) as Record<string, unknown>;
        if (event === 'error') throw new Error(String(eventData.error || `Could not collect ${label}.`));
        setProgress(event === 'complete' ? `Dashboard › ${label} › Ready` : `Dashboard › ${label} › Collecting ▰▰▱`);
      }
    }
  };

  const collectInitialData = async (id: string) => {
    const run = await json(`/connections/${id}/brief/refresh`, { method: 'POST' });
    await waitForRun(`/connections/${id}/collection-runs/${String(run.run_id)}/stream`, 'critical database signals');
    const overview = await json(`/connections/${id}/overview`);
    writeDashboardCache(dashboardCacheKey(id, 'overview'), { payload: overview, fetchedAt: Date.now() });
    setData(overview);
    setProgress('Initial database brief is ready.');
  };

  const load = async (nextSection = section, id = connectionId) => {
    if (!id) return;
    if (nextSection === 'kpis' || nextSection === 'bi-chat') return;
    setError('');
    const resource = nextSection === 'schema' ? 'schema/visualizer' : nextSection;
    const cached = readDashboardCache(dashboardCacheKey(id, resource));
    if (cached) setData(cached.payload);
    setLoading(!cached); setProgress(cached ? `Dashboard › ${resource.replaceAll('/', ' ')} › Refreshing ▰▰▱` : `Dashboard › ${resource.replaceAll('/', ' ')} › Loading ▰▱▱`);
    try {
      const ttl = nextSection === 'overview' ? 30_000 : nextSection === 'schema' ? 3_600_000 : 120_000;
      const result = await cachedJson(id, resource, `/connections/${id}/${resource}`, ttl);
      setData(result.payload); setProgress(result.cached ? 'Dashboard › Session data › Ready' : 'Dashboard › Data updated › Ready');
    } catch (reason) { if (nextSection === 'overview' && reason instanceof ApiError && reason.status === 404) { try { await collectInitialData(id); } catch (collectionError) { setError(collectionError instanceof Error ? collectionError.message : 'Could not collect initial data.'); } return; } setError(reason instanceof Error ? reason.message : 'Could not load this view.'); } finally { setLoading(false); }
  };

  useEffect(() => { void json('/connections').then(result => {
    const available = (result.data || []) as Connection[];
    setConnections(available);
    setConnectionId(available[0]?.connection_id || '');
    setShowConnectionModal(!available.length);
  }).catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load connections.')); }, []);
  useEffect(() => { void load(); }, [connectionId, section]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => {
    if (!connectionId) return;
    setProgress('Starting analysis…'); setError('');
    try {
      const response = await authFetch(`/connections/${connectionId}/dashboard/refresh/stream`, { method: 'POST' });
      if (!response.ok || !response.body) throw new Error('Could not start analysis.');
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
      while (true) {
        const part = await reader.read(); if (part.done) break;
        buffer += decoder.decode(part.value, { stream: true });
        const messages = buffer.split('\n\n'); buffer = messages.pop() || '';
        for (const message of messages) {
          const event = message.match(/^event: (.+)$/m)?.[1]; const raw = message.match(/^data: (.+)$/m)?.[1];
          if (!raw) continue; const eventData = JSON.parse(raw) as Record<string, unknown>;
          if (event === 'error') throw new Error(String(eventData.error || 'Analysis failed.'));
          setProgress(event === 'complete' ? 'Analysis complete.' : `${eventData.stage || 'Analysis'}: ${eventData.status || eventData.message || 'running'}`);
        }
      }
      invalidateDashboardConnection(connectionId); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Analysis failed.'); }
  };

  const overview = data as { health_summary?: Record<string, number>; database_stats?: Record<string, unknown>; table_count?: number; top_slow_queries?: Record<string, unknown>[]; insights?: Record<string, unknown>[] };
  const tableRows = loading ? [{ __loading: true }] : rows(data);

  return <div className="min-h-screen bg-voyager-navy text-voyager-text-primary md:grid md:grid-cols-[240px_1fr]">
    <aside className="border-r border-voyager-border/20 bg-voyager-navy2 p-4"><a href="/" className="font-display text-xl font-bold">DBVoyager</a><p className="mt-1 text-sm text-voyager-text-secondary">Database command center</p><nav className="mt-8 space-y-1">{navigation.map(([label, key]) => <button key={key} onClick={() => setSection(key)} className={`block w-full rounded-lg px-3 py-2 text-left text-sm ${section === key ? 'bg-voyager-blue/15 text-voyager-blue' : 'text-voyager-text-secondary hover:bg-voyager-surface'}`}>{label}</button>)}</nav><a href="/" className="mt-8 block text-sm text-voyager-text-secondary hover:text-voyager-text-primary">← Back to site</a></aside>
    <main className="min-w-0"><header className="flex flex-wrap items-center gap-3 border-b border-voyager-border/20 bg-voyager-navy/80 px-5 py-3 backdrop-blur"><span className="rounded border border-voyager-success/40 bg-voyager-success/10 px-2 py-1 font-mono text-xs text-voyager-success">● PRODUCTION</span><select value={connectionId} onChange={event => setConnectionId(event.target.value)} className="rounded border border-voyager-border/30 bg-voyager-surface px-3 py-2 text-sm">{connections.length ? connections.map(connection => <option key={connection.connection_id} value={connection.connection_id}>{connection.display_name}</option>) : <option value="">No connection</option>}</select><button onClick={() => setShowConnectionModal(true)} className="rounded border border-voyager-blue/50 px-3 py-2 text-sm font-semibold text-voyager-blue">Add database</button><button onClick={() => void refresh()} disabled={!connectionId} className="rounded border border-voyager-success/50 px-3 py-2 text-sm font-semibold text-voyager-success disabled:opacity-40">Run analysis</button>{progress && <span className="text-sm text-voyager-blue">{progress}</span>}</header>
      <div className="mx-auto max-w-7xl p-5"><div className="mb-6 flex items-end justify-between"><div><p className="font-mono text-xs uppercase tracking-[.16em] text-voyager-blue">{section.replace('-', ' ')}</p><h1 className="mt-2 font-display text-3xl font-bold">{navigation.find(([, key]) => key === section)?.[0]}</h1></div></div>{error && <p role="alert" className="mb-5 rounded-lg border border-voyager-critical/30 bg-voyager-critical/10 p-3 text-sm text-voyager-critical">{error}</p>}{!connectionId ? <div className="voyager-card p-8"><h2 className="font-display text-2xl font-bold">Connect a database to begin.</h2><p className="mt-3 text-voyager-text-secondary">Your authenticated connections will appear here after they are added through the API.</p></div> : section === 'bi-chat' ? <BusinessIntelligenceChat key={connectionId} connectionId={connectionId} /> : section === 'kpis' ? <BatchKpiAgent key={connectionId} connectionId={connectionId} /> : section === 'overview' ? <><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[['Critical risks', overview.health_summary?.critical || 0], ['Warnings', overview.health_summary?.warning || 0], ['Tables scanned', overview.table_count || 0], ['Cache hit ratio', value(overview.database_stats || {}, 'cache_hit_ratio')]].map(([label, metric]) => <div key={String(label)} className="voyager-card p-5"><p className="font-mono text-xs uppercase tracking-widest text-voyager-text-secondary">{label}</p><p className="mt-3 font-mono text-3xl text-voyager-blue">{metric}</p></div>)}</div><section className="mt-5 grid gap-3 md:grid-cols-2">{(overview.insights || []).map((insight, index) => <article key={index} className="voyager-card border-l-4 border-l-voyager-warning p-4"><p className="font-mono text-xs uppercase text-voyager-blue">{value(insight, 'severity')}</p><h2 className="mt-2 font-semibold">{value(insight, 'title')}</h2><p className="mt-2 text-sm text-voyager-text-secondary">{value(insight, 'action')}</p></article>)}</section><section className="voyager-card mt-5 p-5"><h2 className="font-display text-xl font-bold">Slow-query signals</h2><div className="mt-4 space-y-3">{(overview.top_slow_queries || []).length ? overview.top_slow_queries?.map((query, index) => <div key={index} className="rounded border border-voyager-border/15 p-3"><code className="sql-text break-all">{value(query, 'query')}</code><p className="mt-2 text-xs text-voyager-text-secondary">Mean execution time: {value(query, 'mean_exec_time')} ms · Calls: {value(query, 'calls')}</p></div>) : <p className="text-sm text-voyager-text-secondary">Query telemetry is unavailable or no slow queries were found.</p>}</div></section></> : <section className="voyager-card overflow-hidden"><div className="border-b border-voyager-border/15 p-5"><h2 className="font-display text-xl font-bold">{section === 'schema' ? 'Schema explorer' : 'Collected data'}</h2><p className="mt-1 text-sm text-voyager-text-secondary">{section === 'schema' ? 'Supabase-inspired table explorer: choose a table, then inspect its structure.' : 'Live data from the selected database connection.'}</p></div>{section === 'schema' ? <SchemaExplorer data={data} /> : <DataTable data={tableRows} />}</section>}</div>
    </main>{showConnectionModal && <ConnectionModal onClose={() => setShowConnectionModal(false)} onCreated={connection => { setConnections(current => [...current, connection]); setConnectionId(connection.connection_id); setSection('overview'); setProgress('Connection created. Initial analysis is queued.'); setShowConnectionModal(false); }} />}
  </div>;
}

function DataTable({ data }: { data: Record<string, unknown>[] }) {
  if (data[0]?.__loading) return <div className="space-y-3 p-5" aria-busy="true">{Array.from({ length: 5 }, (_, index) => <div key={index} className="animate-pulse rounded-lg border border-voyager-border/15 bg-voyager-navy2 p-4"><div className="h-3 w-1/4 rounded bg-voyager-blue/15" /><div className="mt-3 h-3 w-3/4 rounded bg-voyager-blue/15" /></div>)}</div>;
  if (!data.length) return <p className="p-5 text-sm text-voyager-text-secondary">No collected data yet. Run an analysis to populate this section.</p>;
  if (Object.hasOwn(data[0], 'query')) return <SlowQueryList data={data} />;
  const columns = [...new Set(data.flatMap(row => Object.keys(row)))].slice(0, 6);
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-voyager-navy2 text-xs uppercase tracking-wider text-voyager-text-secondary"><tr>{columns.map(column => <th key={column} className="px-5 py-3 font-mono">{column.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{data.map((row, index) => <tr key={index} className="border-t border-voyager-border/10 transition hover:bg-voyager-blue/5">{columns.map(column => <td key={column} className="max-w-xs px-5 py-3 align-top text-voyager-text-secondary">{typeof row[column] === 'number' ? metric(row[column]) : value(row, column)}</td>)}</tr>)}</tbody></table></div>;
}

function SlowQueryList({ data }: { data: Record<string, unknown>[] }) {
  return <div className="divide-y divide-voyager-border/15">{data.map((query, index) => <article key={index} className="grid gap-4 p-5 transition hover:bg-voyager-blue/5 md:grid-cols-[1fr_auto]"><div className="min-w-0"><p className="font-mono text-xs uppercase tracking-widest text-voyager-warning">Query fingerprint #{index + 1}</p><p className="mt-2 truncate font-mono text-sm text-voyager-text-primary" title={value(query, 'query')}>{value(query, 'query')}</p><p className="mt-2 text-xs text-voyager-text-secondary">Sanitized preview · full SQL remains protected in the API.</p></div><div className="grid grid-cols-2 gap-x-6 gap-y-2 text-right"><div><p className="font-mono text-xs uppercase text-voyager-text-secondary">Mean</p><p className="mt-1 font-mono text-lg text-voyager-warning">{metric(query.mean_exec_time, ' ms')}</p></div><div><p className="font-mono text-xs uppercase text-voyager-text-secondary">Calls</p><p className="mt-1 font-mono text-lg text-voyager-blue">{metric(query.calls)}</p></div><div><p className="font-mono text-xs uppercase text-voyager-text-secondary">Total</p><p className="mt-1 font-mono text-sm text-voyager-text-primary">{metric(query.total_exec_time, ' ms')}</p></div><div><p className="font-mono text-xs uppercase text-voyager-text-secondary">Rows</p><p className="mt-1 font-mono text-sm text-voyager-text-primary">{metric(query.rows_returned)}</p></div></div></article>)}</div>;
}

function BusinessIntelligenceChat({ connectionId }: { connectionId: string }) {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const ask = async (event: React.FormEvent) => {
    event.preventDefault();
    const prompt = question.trim();
    if (!prompt || loading) return;
    setLoading(true); setError('');
    try {
      const response = await json(`/connections/${connectionId}/bi/investigations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: prompt }) });
      setMessages(current => [...current, response]); setQuestion('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not investigate that question.'); }
    finally { setLoading(false); }
  };
  return <section className="voyager-card mx-auto max-w-4xl overflow-hidden"><header className="border-b border-voyager-border/15 p-5"><p className="font-mono text-xs uppercase tracking-widest text-voyager-blue">Read-only Business Intelligence Agent</p><h2 className="mt-2 font-display text-2xl font-bold">Ask your database a business question.</h2><p className="mt-2 text-sm text-voyager-text-secondary">The agent plans, validates, and runs one bounded SELECT query against this connection.</p></header><div className="min-h-72 space-y-4 p-5">{!messages.length && <div className="rounded-lg border border-dashed border-voyager-border/30 p-5 text-sm text-voyager-text-secondary">Try: “Which products drive the most revenue?” or “How many new customers joined by month?”</div>}{messages.map((message, index) => { const insight = message.insight as Record<string, unknown> || {}; const result = message.result as Record<string, unknown> || {}; const evidence = Array.isArray(insight.evidence) ? insight.evidence : []; const recommendations = Array.isArray(insight.recommendations) ? insight.recommendations : []; return <article key={index} className="space-y-3"><div className="ml-auto max-w-[85%] rounded-lg bg-voyager-blue/15 px-4 py-3 text-sm">{value(message, 'question')}</div><div className="max-w-[92%] rounded-lg border border-voyager-border/20 bg-voyager-navy2 p-4"><p className="font-semibold">{value(insight, 'summary')}</p>{evidence.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-voyager-text-secondary">{evidence.map((item, itemIndex) => <li key={itemIndex}>{String(item)}</li>)}</ul>}{recommendations.length > 0 && <div className="mt-3 border-t border-voyager-border/15 pt-3 text-sm text-voyager-blue">Recommended: {recommendations.map(String).join(' · ')}</div>}<p className="mt-3 font-mono text-xs text-voyager-text-secondary">{value(result, 'row_count')} rows analyzed</p><details className="mt-3 text-xs text-voyager-text-secondary"><summary className="cursor-pointer">Show validated SQL</summary><code className="mt-2 block whitespace-pre-wrap break-all text-voyager-text-primary">{value(message, 'generated_sql')}</code></details></div></article>; })}{loading && <div className="animate-pulse rounded-lg border border-voyager-blue/25 bg-voyager-blue/5 p-4 text-sm text-voyager-blue">Planning investigation › validating query › analyzing evidence…</div>}{error && <p role="alert" className="rounded-lg border border-voyager-critical/30 bg-voyager-critical/10 p-3 text-sm text-voyager-critical">{error}</p>}</div><form onSubmit={ask} className="flex gap-3 border-t border-voyager-border/15 p-4"><label className="sr-only" htmlFor="bi-question">Business question</label><input id="bi-question" value={question} onChange={event => setQuestion(event.target.value)} disabled={loading} maxLength={2000} className="auth-input m-0 flex-1" placeholder="Ask a question about this database…" /><button disabled={loading || !question.trim()} className="rounded-lg bg-voyager-blue px-4 py-2 font-semibold text-voyager-navy disabled:opacity-40">{loading ? 'Investigating…' : 'Ask agent'}</button></form></section>;
}

function BatchKpiAgent({ connectionId }: { connectionId: string }) {
  return <AutoKpiDashboard connectionId={connectionId} />;
}

function AutoKpiDashboard({ connectionId }: { connectionId: string }) {
  const [definitions, setDefinitions] = useState<Record<string, unknown>[]>([]);
  const [charts, setCharts] = useState<Record<string, Record<string, unknown>>>({});
  const [waiting, setWaiting] = useState(true);
  const [generation, setGeneration] = useState<'running' | 'succeeded' | 'failed' | 'unavailable' | 'pending'>('pending');
  const [requested, setRequested] = useState(false);
  const [error, setError] = useState('');
  const [emptyMessage, setEmptyMessage] = useState('');
  const retry = async () => {
    setError(''); setGeneration('running'); setWaiting(true); setRequested(true);
    try { await json(`/connections/${connectionId}/kpis/generate`, { method: 'POST' }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not start KPI generation.'); }
  };
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await cachedJson(
          connectionId,
          'kpis/dashboard',
          `/connections/${connectionId}/kpis/dashboard`,
          generation === 'running' || generation === 'pending' ? 0 : 60_000,
        );
        const result = rows(response.payload);
        const status = (response.payload.generation as Record<string, unknown> | null)?.status;
        const errorMessage = String((response.payload.generation as Record<string, unknown> | null)?.error_message || '');
        const nextGeneration = status === 'running' || status === 'succeeded' || status === 'failed' || status === 'unavailable' ? status : 'pending';
        if (!active) return;
        if ((!status && !result.length || status === 'failed' && errorMessage === 'ValueError') && !requested) {
          setRequested(true); setGeneration('running'); setWaiting(true);
          await json(`/connections/${connectionId}/kpis/generate`, { method: 'POST' });
          return;
        }
        setDefinitions(result); setGeneration(nextGeneration); setWaiting(nextGeneration === 'running' || nextGeneration === 'pending');
        setCharts(Object.fromEntries(result.filter(definition => definition.chart).map(definition => [value(definition, 'id'), definition.chart as Record<string, unknown>])));
        if (nextGeneration === 'failed' || nextGeneration === 'unavailable') { setError(String((response.payload.generation as Record<string, unknown> | null)?.error_message || 'KPI generation is temporarily unavailable. Please try again later.')); setEmptyMessage(''); }
        else if (nextGeneration === 'succeeded' && !result.length) { setError(''); setEmptyMessage('No safe aggregate KPIs were found for this schema.'); }
        else { setError(''); setEmptyMessage(''); }
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : 'Could not load KPIs.'); }
    };
    void load();
    const timer = generation === 'running' || generation === 'pending' ? window.setInterval(() => void load(), 10_000) : undefined;
    return () => { active = false; if (timer) window.clearInterval(timer); };
  }, [connectionId, generation, requested]);
  return <div className="space-y-5">{error && <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-voyager-critical/30 bg-voyager-critical/10 p-3 text-sm text-voyager-critical"><span>{error}</span><button onClick={() => void retry()} className="shrink-0 rounded border border-voyager-critical/50 px-3 py-1.5 text-xs font-semibold">Retry</button></div>}<section className="voyager-card p-5"><p className="font-mono text-xs uppercase tracking-widest text-voyager-blue">Autonomous KPI Agent</p><h2 className="mt-2 font-display text-2xl font-bold">Live business signals</h2><p className="mt-2 text-sm text-voyager-text-secondary">DBVoyager discovers safe aggregate KPIs from schema metadata and calculates them automatically after connection analysis.</p><div className="mt-5 grid gap-4 lg:grid-cols-3">{definitions.map(definition => { const chart = charts[value(definition, 'id')]; const series = chart?.series as Record<string, unknown>[] | undefined; const points = Array.isArray(series?.[0]?.points) ? series[0].points as Record<string, unknown>[] : []; const latest = points.at(-1); return <article key={value(definition, 'id')} className="rounded-lg border border-voyager-border/20 bg-voyager-navy2 p-4"><p className="font-mono text-xs uppercase text-voyager-blue">{value(definition, 'aggregation')} · {value(definition, 'table_name')}</p><h3 className="mt-2 font-semibold">{value(definition, 'title')}</h3>{latest ? <><p className="mt-5 font-mono text-3xl text-voyager-success">{value(latest, 'y')}</p><p className="mt-1 text-xs text-voyager-text-secondary">Latest period: {value(latest, 'x')} · {points.length} points</p><p className="mt-1 text-xs text-voyager-text-secondary">Last generated: {value(chart?.source, 'generated_at')}</p></> : chart ? <p className="mt-5 text-sm text-voyager-text-secondary">No rows returned by the last KPI run.</p> : <div className="mt-5 animate-pulse"><div className="h-8 w-2/3 rounded bg-voyager-blue/15" /><p className="mt-3 text-sm text-voyager-blue">Calculating aggregate…</p></div>}</article>; })}{waiting && Array.from({ length: 3 }, (_, index) => <article key={index} className="animate-pulse rounded-lg border border-voyager-blue/25 bg-voyager-navy2 p-4"><div className="h-3 w-24 rounded bg-voyager-blue/15" /><div className="mt-4 h-5 w-2/3 rounded bg-voyager-blue/15" /><div className="mt-8 h-9 w-1/2 rounded bg-voyager-blue/15" /><p className="mt-4 text-sm text-voyager-blue">Generating KPI insights…</p></article>)}{!waiting && !definitions.length && !error && <article className="rounded-lg border border-voyager-border/20 bg-voyager-navy2 p-5 text-sm text-voyager-text-secondary">{emptyMessage || 'KPI generation is waiting for dashboard analysis.'}</article>}</div></section></div>;
}

function LegacyKpiReview({ connectionId }: { connectionId: string }) {
  const [candidates, setCandidates] = useState<Record<string, unknown>[]>([]); const [definitions, setDefinitions] = useState<Record<string, unknown>[]>([]); const [choices, setChoices] = useState<Record<string, 'approve' | 'reject'>>({}); const [charts, setCharts] = useState<Record<string, Record<string, unknown>>>({}); const [running, setRunning] = useState<string[]>([]); const [status, setStatus] = useState(''); const [error, setError] = useState('');
  const reload = async () => { const [proposalResult, definitionResult] = await Promise.all([json(`/connections/${connectionId}/kpis/candidates`), json(`/connections/${connectionId}/kpis/definitions`)]); setCandidates(rows(proposalResult)); setDefinitions(rows(definitionResult)); };
  const choose = (id: string, decision: 'approve' | 'reject') => setChoices(current => { const next = { ...current }; if (next[id] === decision) delete next[id]; else next[id] = decision; return next; });
  useEffect(() => { void reload().catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load KPI Agent.')); }, [connectionId]); // eslint-disable-line react-hooks/exhaustive-deps
  const discover = async () => { try { await json(`/connections/${connectionId}/kpis/discover`, { method: 'POST' }); await reload(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not discover KPI proposals.'); } };
  const submit = async () => { const approved_ids = Object.entries(choices).filter(([, decision]) => decision === 'approve').map(([id]) => id); const rejected_ids = Object.entries(choices).filter(([, decision]) => decision === 'reject').map(([id]) => id); if (!approved_ids.length && !rejected_ids.length) return; setError(''); setRunning(approved_ids); setStatus('Submitting KPI review…'); try { const response = await authFetch(`/connections/${connectionId}/kpis/review/stream`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved_ids, rejected_ids }) }); if (!response.ok || !response.body) throw new Error((await response.json().catch(() => ({})) as { detail?: string }).detail || 'Could not start KPI review.'); const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; while (true) { const part = await reader.read(); if (part.done) break; buffer += decoder.decode(part.value, { stream: true }); const messages = buffer.split('\n\n'); buffer = messages.pop() || ''; for (const message of messages) { const event = message.match(/^event: (.+)$/m)?.[1]; const raw = message.match(/^data: (.+)$/m)?.[1]; if (!event || !raw) continue; const payload = JSON.parse(raw) as Record<string, unknown>; if (event === 'kpi_started') { setStatus(`Calculating ${value(payload, 'candidate_id')}…`); } else if (event === 'kpi_ready') { const definition = payload.definition as Record<string, unknown>; const chart = payload.chart as Record<string, unknown>; setDefinitions(current => current.some(item => value(item, 'id') === value(definition, 'id')) ? current : [...current, definition]); setCharts(current => ({ ...current, [value(definition, 'id')]: chart })); setRunning(current => current.filter(id => id !== value(payload, 'candidate_id'))); } else if (event === 'candidate_error') { setError(value(payload, 'error')); setRunning(current => current.filter(id => id !== value(payload, 'candidate_id'))); } else if (event === 'complete') { setStatus('KPI review complete.'); } } } await reload(); setChoices({}); } catch (reason) { setError(reason instanceof Error ? reason.message : 'KPI review failed.'); } finally { setRunning([]); } };
  return <div className="space-y-5">{error && <p role="alert" className="rounded-lg border border-voyager-critical/30 bg-voyager-critical/10 p-3 text-sm text-voyager-critical">{error}</p>}<section className="voyager-card p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-display text-xl font-bold">Review KPI proposals</h2><p className="mt-1 text-sm text-voyager-text-secondary">Choose proposals, then submit one review. Calculations stream back into the cards.</p></div><button onClick={() => void discover()} className="rounded border border-voyager-blue/50 px-3 py-2 text-sm text-voyager-blue">Discover proposals</button></div><div className="mt-4 grid gap-3 lg:grid-cols-2">{candidates.map(candidate => { const id = value(candidate, 'id'); const decision = choices[id]; return <article key={id} className={`rounded-lg border bg-voyager-navy2 p-4 transition ${decision === 'approve' ? 'border-voyager-success/60 shadow-[0_0_24px_rgb(var(--voyager-success)_/_0.08)]' : decision === 'reject' ? 'border-voyager-critical/60' : 'border-voyager-border/20'}`}><div className="flex items-start justify-between gap-3"><h3 className="font-semibold">{value(candidate, 'title')}</h3><span className="font-mono text-xs text-voyager-success">{Math.round(Number(value(candidate, 'confidence')) * 100)}%</span></div><p className="mt-2 text-sm text-voyager-text-secondary">{value(candidate, 'rationale')}</p><p className="mt-3 font-mono text-xs text-voyager-blue">{value(candidate, 'aggregation')}({value(candidate, 'measure_column')}) · {value(candidate, 'table_name')}</p>{running.includes(id) ? <div className="mt-4 animate-pulse rounded bg-voyager-blue/10 px-3 py-2 text-sm text-voyager-blue">Preparing aggregate and chart…</div> : <fieldset className="mt-4"><legend className="mb-2 font-mono text-[10px] uppercase tracking-widest text-voyager-text-secondary">Review decision</legend><div className="grid grid-cols-2 gap-2"><label className={`cursor-pointer rounded-md border px-3 py-2 text-center text-sm font-medium transition ${decision === 'approve' ? 'border-voyager-success bg-voyager-success/15 text-voyager-success' : 'border-voyager-border/30 text-voyager-text-secondary hover:border-voyager-success/60'}`}><input className="sr-only" type="checkbox" checked={decision === 'approve'} onChange={() => choose(id, 'approve')} />✓ Approve</label><label className={`cursor-pointer rounded-md border px-3 py-2 text-center text-sm font-medium transition ${decision === 'reject' ? 'border-voyager-critical bg-voyager-critical/15 text-voyager-critical' : 'border-voyager-border/30 text-voyager-text-secondary hover:border-voyager-critical/60'}`}><input className="sr-only" type="checkbox" checked={decision === 'reject'} onChange={() => choose(id, 'reject')} />× Reject</label></div></fieldset>}</article>; })}{!candidates.length && <p className="text-sm text-voyager-text-secondary">No proposals yet. Discover metadata-backed KPI candidates after schema analysis.</p>}</div><button onClick={() => void submit()} disabled={!Object.keys(choices).length || !!running.length} className="mt-5 rounded bg-voyager-blue px-4 py-3 font-semibold text-voyager-navy disabled:opacity-40">Submit selected KPI review</button>{status && <p className="mt-3 text-sm text-voyager-blue">{status}</p>}</section><section className="voyager-card p-5"><h2 className="font-display text-xl font-bold">KPI results</h2><div className="mt-4 grid gap-3 lg:grid-cols-2">{running.map(id => <article key={id} className="animate-pulse rounded-lg border border-voyager-blue/30 bg-voyager-navy2 p-4"><p className="font-semibold">KPI aggregate</p><div className="mt-4 h-8 rounded bg-voyager-blue/15" /><p className="mt-3 text-sm text-voyager-blue">Receiving calculation progress…</p></article>)}{definitions.map(definition => { const chart = charts[value(definition, 'id')]; const series = chart?.series as Record<string, unknown>[] | undefined; const points = Array.isArray(series?.[0]?.points) ? series[0].points as Record<string, unknown>[] : []; const latest = points.at(-1); return <article key={value(definition, 'id')} className="rounded-lg border border-voyager-border/20 bg-voyager-navy2 p-4"><h3 className="font-semibold">{value(definition, 'title')}</h3>{latest ? <div className="mt-4"><p className="font-mono text-3xl text-voyager-blue">{value(latest, 'y')}</p><p className="mt-1 text-xs text-voyager-text-secondary">Latest period: {value(latest, 'x')} · {points.length} points</p></div> : <div className="mt-4 animate-pulse rounded bg-voyager-blue/10 px-3 py-3 text-sm text-voyager-blue">Chart available after the next KPI refresh.</div>}</article>; })}</div></section></div>;
}
function KpiAgent({ connectionId }: { connectionId: string }) {
  const [candidates, setCandidates] = useState<Record<string, unknown>[]>([]); const [definitions, setDefinitions] = useState<Record<string, unknown>[]>([]); const [charts, setCharts] = useState<Record<string, Record<string, unknown>>>({}); const [status, setStatus] = useState(''); const [error, setError] = useState('');
  const reload = async () => { const [candidateResult, definitionResult] = await Promise.all([json(`/connections/${connectionId}/kpis/candidates`), json(`/connections/${connectionId}/kpis/definitions`)]); setCandidates(rows(candidateResult)); setDefinitions(rows(definitionResult)); };
  useEffect(() => { void reload().catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load KPI Agent.')); }, [connectionId]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (path: string, success: string) => { setError(''); setStatus('Working…'); try { const result = await json(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); const chart = result.chart as Record<string, unknown> | undefined; if (chart) setCharts(current => ({ ...current, [value(chart, 'kpi_id')]: chart })); await reload(); setStatus(success); } catch (reason) { setStatus(''); setError(reason instanceof Error ? reason.message : 'KPI action failed.'); } };
  return <div className="space-y-5">{error && <p role="alert" className="rounded-lg border border-voyager-critical/30 bg-voyager-critical/10 p-3 text-sm text-voyager-critical">{error}</p>}{status && <p className="text-sm text-voyager-blue">{status}</p>}<section className="voyager-card p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-display text-xl font-bold">KPI proposals</h2><p className="mt-1 text-sm text-voyager-text-secondary">Approve a grounded metric to execute it against this connection.</p></div><div className="flex gap-2"><button onClick={() => void act(`/connections/${connectionId}/kpis/discover`, 'KPI proposals generated.')} className="rounded bg-voyager-blue px-3 py-2 text-sm font-semibold text-voyager-navy">Discover proposals</button><button onClick={() => void reload()} className="rounded border border-voyager-blue/50 px-3 py-2 text-sm text-voyager-blue">Reload</button></div></div><div className="mt-4 grid gap-3 lg:grid-cols-2">{candidates.map(candidate => <article key={value(candidate, 'id')} className="rounded-lg border border-voyager-border/20 bg-voyager-navy2 p-4"><div className="flex items-start justify-between gap-3"><h3 className="font-semibold">{value(candidate, 'title')}</h3><span className="font-mono text-xs text-voyager-success">{Math.round(Number(value(candidate, 'confidence')) * 100)}%</span></div><p className="mt-2 text-sm text-voyager-text-secondary">{value(candidate, 'rationale')}</p><p className="mt-3 font-mono text-xs text-voyager-blue">{value(candidate, 'aggregation')}({value(candidate, 'measure_column')}) · {value(candidate, 'table_name')}</p><div className="mt-4 flex gap-2"><button onClick={() => void act(`/connections/${connectionId}/kpis/candidates/${value(candidate, 'id')}/approve`, 'KPI approved and calculated.')} className="rounded bg-voyager-blue px-3 py-2 text-sm font-semibold text-voyager-navy">Approve & calculate</button><button onClick={() => void act(`/connections/${connectionId}/kpis/candidates/${value(candidate, 'id')}/reject`, 'KPI proposal rejected.')} className="rounded border border-voyager-border/30 px-3 py-2 text-sm text-voyager-text-secondary">Reject</button></div></article>)}{!candidates.length && <p className="text-sm text-voyager-text-secondary">No proposals yet. Discover metadata-backed KPI candidates after schema analysis.</p>}</div></section><section className="voyager-card p-5"><h2 className="font-display text-xl font-bold">Active KPIs</h2><div className="mt-4 grid gap-3 lg:grid-cols-2">{definitions.map(definition => { const chart = charts[value(definition, 'id')]; const series = chart?.series as Record<string, unknown>[] | undefined; const points = Array.isArray(series?.[0]?.points) ? series[0].points as Record<string, unknown>[] : []; const latest = points.at(-1); return <article key={value(definition, 'id')} className="rounded-lg border border-voyager-border/20 bg-voyager-navy2 p-4"><div className="flex items-center justify-between gap-3"><h3 className="font-semibold">{value(definition, 'title')}</h3><button onClick={() => void act(`/connections/${connectionId}/kpis/definitions/${value(definition, 'id')}/refresh`, 'KPI refreshed.')} className="rounded border border-voyager-success/50 px-3 py-2 text-sm text-voyager-success">Refresh</button></div>{latest ? <div className="mt-4"><p className="font-mono text-3xl text-voyager-blue">{value(latest, 'y')}</p><p className="mt-1 text-xs text-voyager-text-secondary">Latest period: {value(latest, 'x')} · {points.length} points</p></div> : <p className="mt-3 text-sm text-voyager-text-secondary">Refresh to calculate the latest value.</p>}</article>; })}{!definitions.length && <p className="text-sm text-voyager-text-secondary">Approved KPI definitions will appear here.</p>}</div></section></div>;
}
function SchemaExplorer({ data }: { data: Record<string, unknown> }) { const graph = (data.data || {}) as Record<string, unknown>; const tables = Array.isArray(graph.tables) ? graph.tables as Record<string, unknown>[] : []; const [search, setSearch] = useState(''); const visible = tables.filter(table => value(table, 'name').toLowerCase().includes(search.toLowerCase())); return <div className="min-h-[620px] overflow-auto bg-[radial-gradient(rgb(var(--voyager-blue)_/_0.22)_1px,transparent_1px)] bg-[size:28px_28px]"><div className="sticky left-0 top-0 z-10 flex gap-3 border-b border-voyager-border/15 bg-voyager-navy/90 p-3 backdrop-blur"><span className="rounded border border-voyager-border/25 px-3 py-2 text-sm text-voyager-blue">schema public</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Find table…" className="auth-input m-0 max-w-xs" /></div><div className="grid min-w-[900px] grid-cols-3 gap-12 p-12">{visible.map(table => <article key={value(table, 'name')} title={value(table, 'summary') === '—' ? `No generated summary yet for ${value(table, 'name')}.` : value(table, 'summary')} className="group relative overflow-visible rounded-lg border border-voyager-border/30 bg-voyager-navy2 shadow-xl transition hover:border-voyager-blue hover:shadow-voyager-blue/20"><header className="flex items-center justify-between border-b border-voyager-border/15 px-4 py-3"><h3 className="font-display font-semibold text-voyager-blue">▦ {value(table, 'name')}</h3><span className="text-voyager-text-secondary">⋮</span></header><div>{(Array.isArray(table.columns) ? table.columns as Record<string, unknown>[] : []).slice(0, 8).map(column => <div key={value(column, 'column_name')} className="flex items-center justify-between border-b border-voyager-border/10 px-4 py-2 text-sm"><span>{value(column, 'primary_key') === 'true' ? '◆ ' : value(column, 'foreign_key') === 'true' ? '◇ ' : '· '}{value(column, 'column_name')}</span><code className="text-xs text-voyager-text-secondary">{value(column, 'data_type')}</code></div>)}</div><div className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-3 hidden w-72 -translate-x-1/2 rounded-lg border border-voyager-blue/30 bg-voyager-surface p-3 text-sm leading-6 text-voyager-text-secondary shadow-2xl group-hover:block">{value(table, 'summary') === '—' ? `No generated summary yet for ${value(table, 'name')}.` : value(table, 'summary')}</div></article>)}</div></div>; }
function ConnectionModal({ onClose, onCreated }: { onClose: () => void; onCreated: (connection: Connection) => void }) {
  const [credentials, setCredentials] = useState<Credentials>({ display_name: '', connection_url: '' });
  const [status, setStatus] = useState(''); const [error, setError] = useState('');
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setError(''); try { const url = new URL(credentials.connection_url); if (!['postgres:', 'postgresql:'].includes(url.protocol) || !url.username || !url.password || !url.hostname || !url.pathname || url.pathname === '/') throw new Error('Enter a complete postgresql://user:password@host:port/database URL.'); setStatus('Testing credentials…'); await json('/connections/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) }); setStatus('Credentials verified. Saving connection…'); const created = await json('/connections', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) }); onCreated({ connection_id: String(created.connection_id), display_name: credentials.display_name || url.pathname.slice(1), status: 'connected' }); } catch (reason) { setStatus(''); setError(reason instanceof Error ? reason.message : 'Could not connect.'); } };
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"><form onSubmit={submit} className="voyager-card w-full max-w-lg p-6"><div className="flex justify-between gap-4"><div><p className="font-mono text-xs uppercase tracking-widest text-voyager-blue">New connection</p><h2 className="mt-2 font-display text-2xl font-bold">Connect PostgreSQL</h2><p className="mt-2 text-sm text-voyager-text-secondary">Credentials are tested before anything is saved.</p></div><button type="button" onClick={onClose} className="text-voyager-text-secondary">×</button></div><div className="mt-5 grid gap-4"><label className="text-sm font-medium">Connection name (optional)<input value={credentials.display_name} onChange={event => setCredentials(current => ({ ...current, display_name: event.target.value }))} className="auth-input" placeholder="Production" /></label><label className="text-sm font-medium">PostgreSQL connection URL<input required type="url" value={credentials.connection_url} onChange={event => setCredentials(current => ({ ...current, connection_url: event.target.value }))} className="auth-input" placeholder="postgresql://user:password@host:5432/database?sslmode=require" /></label></div>{error && <p role="alert" className="mt-4 text-sm text-voyager-critical">{error}</p>}{status && <p className="mt-4 text-sm text-voyager-blue">{status}</p>}<button className="mt-6 w-full rounded-lg bg-voyager-blue px-4 py-3 font-semibold text-voyager-navy">Test & connect</button></form></div>;
}
