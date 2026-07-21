import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { authFetch, authJson } from '../lib/auth';
import { fetchDashboardResource, overviewFromReport, type JsonRecord } from '../lib/dashboardData';
import { useHeaderSearch } from '../AppShell';

type Connection = { connection_id: string; display_name: string };
type Overview = JsonRecord & { health_summary?: JsonRecord; database_stats?: JsonRecord; insights?: JsonRecord[]; top_slow_queries?: JsonRecord[] };

const number = (value: unknown, suffix = '') => Number.isFinite(Number(value)) ? `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(Number(value))}${suffix}` : '—';
const icon = (name: string, className = '') => <span aria-hidden="true" className={`material-symbols-outlined ${className}`}>{name}</span>;
const value = (row: JsonRecord | undefined, key: string) => row?.[key] === null || row?.[key] === undefined ? '—' : String(row[key]);

async function consumeSse(response: Response, onEvent: (event: string, data: JsonRecord) => Promise<boolean> | boolean) {
  if (!response.body) throw new Error('Streaming is unavailable.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const part = await reader.read();
    if (part.done) return;
    buffer += decoder.decode(part.value, { stream: true });
    const messages = buffer.split('\n\n');
    buffer = messages.pop() || '';
    for (const message of messages) {
      const event = message.match(/^event: (.+)$/m)?.[1];
      const raw = message.match(/^data: (.+)$/m)?.[1];
      if (event && raw && await onEvent(event, JSON.parse(raw) as JsonRecord)) { await reader.cancel(); return; }
    }
  }
}

export default function DashboardPage() {
  const { query } = useHeaderSearch();
  const [params, setParams] = useSearchParams();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState('');
  const [overview, setOverview] = useState<Overview>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');

  const load = async (id = connectionId) => {
    if (!id) { setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const result = await fetchDashboardResource(id, 'overview');
      if (result.collecting) setProgress('Analysis is still collecting. Refresh analysis to stream its progress.');
      else { setOverview(result.payload as Overview); setProgress(''); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load the dashboard.'); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    void authJson<{ data: Connection[] }>('/connections').then(result => {
      const requested = params.get('connection');
      const selected = result.data.some(item => item.connection_id === requested) ? requested || '' : result.data[0]?.connection_id || '';
      setConnections(result.data); setConnectionId(selected);
    }).catch(reason => { setError(reason.message); setLoading(false); });
  }, [params]);
  useEffect(() => { void load(connectionId); }, [connectionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => {
    if (!connectionId) return;
    setRefreshing(true); setError(''); setProgress('Starting database analysis…');
    try {
      const response = await authFetch(`/connections/${connectionId}/dashboard/refresh/stream`, { method: 'POST' });
      if (!response.ok) throw new Error('Could not start analysis.');
      await consumeSse(response, async (event, data) => {
        if (event === 'error') throw new Error(String(data.error || data.message || 'Analysis failed.'));
        if (event === 'data_ready') {
          const report = await authJson<JsonRecord>(String(data.preview));
          setOverview(overviewFromReport(report.report as JsonRecord) as Overview);
          setProgress('');
          return true;
        }
        setProgress(String(data.status || data.message || data.stage || 'Collecting database signals…'));
        return false;
      });
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not refresh analysis.'); setProgress(''); }
    finally { setRefreshing(false); }
  };

  const health = overview.health_summary || {};
  const critical = Number(health.critical || 0);
  const warning = Number(health.warning || 0);
  const healthLabel = critical ? 'Critical' : warning ? 'Needs attention' : 'Healthy';
  const slowest = overview.top_slow_queries?.[0];
  const queryTime = number(slowest?.mean_exec_time, ' ms');
  const selectedName = connections.find(item => item.connection_id === connectionId)?.display_name || 'database';
  const findings = (overview.insights || []).filter(finding => !query || `${value(finding, 'title')} ${value(finding, 'action')} ${value(finding, 'severity')}`.toLowerCase().includes(query.toLowerCase()));
  const contextual = (path: string) => `${path}?connection=${encodeURIComponent(connectionId)}`;

  return <section className="mx-auto max-w-[1400px] p-6 md:p-10">
    <header className="mb-8 flex flex-col justify-between gap-4 lg:flex-row lg:items-end"><div><p className="font-mono text-xs tracking-[.16em] text-voyager-blue">MISSION CONTROL</p><h1 className="mt-2 font-display text-3xl font-semibold">Database overview</h1><p className="mt-2 text-base text-voyager-text-secondary">The signals that need attention for {selectedName}.</p></div><div className="flex flex-wrap gap-3"><select value={connectionId} onChange={event => { setConnectionId(event.target.value); setParams({ connection: event.target.value }); }} className="ui-input m-0 w-auto" aria-label="Selected database">{connections.map(item => <option key={item.connection_id} value={item.connection_id}>{item.display_name}</option>)}</select><button type="button" onClick={() => void refresh()} disabled={!connectionId || refreshing} className="ui-button ui-button-primary">{refreshing && icon('progress_activity', 'animate-spin')}Refresh analysis</button></div></header>
    {error && <p role="alert" className="mb-5 border border-red-400/40 bg-red-500/10 p-4 text-sm text-red-200">{error}</p>}
    {progress && <p aria-live="polite" className="mb-5 border border-voyager-blue/30 bg-voyager-blue/10 p-4 text-sm text-voyager-text-secondary">{progress}</p>}
    {!connectionId && !loading ? <EmptyState /> : loading ? <DashboardSkeleton /> : <><div className="grid gap-5 md:grid-cols-3"><Metric label="Database health" value={healthLabel} detail={critical ? `${critical} critical finding${critical === 1 ? '' : 's'}` : warning ? `${warning} warning${warning === 1 ? '' : 's'}` : 'No critical findings'} tone={critical ? 'text-red-300' : warning ? 'text-amber-300' : 'text-emerald-300'} /><Metric label="Active alerts" value={number(critical + warning)} detail="Open critical and warning findings" tone="text-voyager-blue-light" /><Metric label="Slowest query" value={queryTime} detail="Highest observed mean execution time" tone="text-voyager-text-primary" /></div><section className="mt-8 voyager-card overflow-hidden"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-voyager-border px-5 py-4"><div><h2 className="font-display text-xl font-semibold">Recent findings</h2><p className="mt-1 text-sm text-voyager-text-secondary">Latest collected database signals.</p></div><Link to={contextual('/health-checks')} className="ui-button ui-button-ghost">Open health checks {icon('arrow_forward')}</Link></header>{findings.length ? <div className="divide-y divide-voyager-border">{findings.slice(0, 5).map((finding, index) => <article key={`${value(finding, 'title')}-${index}`} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center"><span className={`ui-badge w-fit ${value(finding, 'severity') === 'critical' ? 'border-red-400/40 text-red-300' : value(finding, 'severity') === 'warning' ? 'border-amber-400/40 text-amber-300' : 'text-voyager-blue-light'}`}>{value(finding, 'severity').toUpperCase()}</span><div className="min-w-0 flex-1"><h3 className="font-medium">{value(finding, 'title')}</h3><p className="mt-1 text-sm text-voyager-text-secondary">{value(finding, 'action')}</p></div></article>)}</div> : <p className="p-6 text-sm text-voyager-text-secondary">No recent findings match this search.</p>}</section><nav className="mt-8 grid gap-4 md:grid-cols-3" aria-label="Database tools"><ModuleLink to={contextual('/health-checks')} iconName="auto_graph" title="Health checks" description="Review and acknowledge database findings." /><ModuleLink to={contextual('/optimizer')} iconName="query_stats" title="Query optimizer" description="Investigate persisted slow-query snapshots." /><ModuleLink to={contextual('/schema-explorer')} iconName="table_chart" title="Schema explorer" description="Inspect tables, indexes, and relationships." /></nav></>}
  </section>;
}

function Metric({ label, value: metric, detail, tone }: { label: string; value: string; detail: string; tone: string }) { return <article className="voyager-card p-5"><p className="font-mono text-xs tracking-widest text-voyager-text-secondary">{label.toUpperCase()}</p><p className={`mt-4 font-display text-3xl font-semibold ${tone}`}>{metric}</p><p className="mt-2 text-sm text-voyager-text-secondary">{detail}</p></article>; }
function ModuleLink({ to, iconName, title, description }: { to: string; iconName: string; title: string; description: string }) { return <Link to={to} className="voyager-card voyager-glow p-5"><span className="text-voyager-blue">{icon(iconName)}</span><h2 className="mt-4 font-display text-lg font-semibold">{title}</h2><p className="mt-2 text-sm text-voyager-text-secondary">{description}</p></Link>; }
function EmptyState() { return <div className="grid min-h-[50vh] place-items-center text-center"><div><p className="font-mono text-xs tracking-[.16em] text-voyager-blue">MISSION CONTROL</p><h2 className="mt-3 font-display text-3xl">Connect a database to begin.</h2><Link to="/connections" className="ui-button ui-button-primary mt-6">New connection</Link></div></div>; }
function DashboardSkeleton() { return <div aria-label="Loading dashboard" className="grid gap-5 md:grid-cols-3">{[0, 1, 2].map(item => <div key={item} className="h-36 animate-pulse rounded-lg bg-voyager-surface" />)}</div>; }
