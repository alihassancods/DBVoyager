import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { authFetch } from '../lib/auth';

type Connection = {
  connection_id: string;
  display_name: string;
  status: string;
  host?: string | null;
  port?: number | null;
  database?: string | null;
  archived_at?: string | null;
  last_analyzed_at?: string | null;
  num_connections?: number | null;
  database_size_mb?: number | null;
  cache_hit_ratio?: number | null;
};

type User = { email?: string | null };
type ApiError = Error & { status?: number };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(path, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(String((body as { detail?: string }).detail || 'Request failed')) as ApiError;
    error.status = response.status;
    throw error;
  }
  return body as T;
}

function icon(name: string, className = '') {
  return <span aria-hidden="true" className={`material-symbols-outlined ${className}`}>{name}</span>;
}

function formatNumber(value: number | null | undefined, suffix = '') {
  return value === null || value === undefined ? '—' : `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)}${suffix}`;
}

function relativeTime(value: string | null | undefined) {
  if (!value) return '—';
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function statusStyle(connection: Connection) {
  if (connection.archived_at) return { label: 'Archived', className: 'border-slate-600 bg-slate-700/40 text-slate-300', dot: 'bg-slate-400' };
  if (connection.status === 'connection_error' || connection.status === 'disabled') return { label: 'Offline', className: 'border-red-400/30 bg-red-500/10 text-red-300', dot: 'bg-red-300' };
  if (connection.status === 'paused') return { label: 'Paused', className: 'border-amber-400/30 bg-amber-400/10 text-amber-300', dot: 'bg-amber-300' };
  return { label: 'Active', className: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300', dot: 'bg-emerald-300' };
}

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [query, setQuery] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Connection | null>(null);

  const loadConnections = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api<{ data: Connection[] }>('/connections');
      setConnections(result.data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load connections.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadConnections();
    void api<User>('/auth/me').then(user => setEmail(user.email || '')).catch(() => undefined);
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? connections.filter(item => [item.display_name, item.host, item.database, item.status].some(value => String(value || '').toLowerCase().includes(needle))) : connections;
  }, [connections, query]);
  const active = connections.filter(item => !item.archived_at).length;
  const latest = connections.reduce<string | null>((value, item) => !value || (item.last_analyzed_at && item.last_analyzed_at > value) ? item.last_analyzed_at || value : value, null);
  const cacheHits = connections.map(item => item.cache_hit_ratio).filter((item): item is number => item !== null && item !== undefined);
  const averageCacheHit = cacheHits.length ? cacheHits.reduce((sum, item) => sum + item, 0) / cacheHits.length : null;

  async function action(connection: Connection, path: string, method = 'POST') {
    setBusy(`${connection.connection_id}:${path}`);
    setError('');
    try {
      await api(path, { method });
      await loadConnections();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Connection action failed.');
    } finally {
      setBusy(null);
    }
  }

  return <div className="min-h-screen bg-[#0f1418] text-[#dee3e9] md:grid md:grid-cols-[240px_1fr]">
    <FleetSidebar onAdd={() => setCreateOpen(true)} />
    <main className="min-w-0">
      <FleetHeader email={email} query={query} onQuery={setQuery} />
      <section className="mx-auto max-w-[1600px] p-4 md:p-8">
        <header className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div><h1 className="font-display text-4xl font-semibold tracking-tight">Connections</h1><p className="mt-1 text-sm text-[#bec8d2]">Fleet Management <span className="mx-2">/</span> <strong className="font-medium text-[#dee3e9]">Database Nodes</strong></p></div>
          <div className="flex gap-3"><button type="button" onClick={() => void loadConnections()} disabled={loading} className="fleet-button border border-[#88929b] bg-transparent text-[#dee3e9]">{icon('refresh', 'text-lg')} Refresh</button><button type="button" onClick={() => setCreateOpen(true)} className="fleet-button border border-[#89ceff] bg-[#89ceff] font-semibold text-[#00344d]">{icon('add_link', 'text-lg')} Add Connection</button></div>
        </header>
        {error && <p role="alert" className="mb-5 border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p>}
        {loading ? <div className="grid min-h-72 place-items-center border border-[#3e4850] text-sm text-[#bec8d2]">Loading fleet…</div> : <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {visible.map(connection => <ConnectionCard key={connection.connection_id} connection={connection} busy={busy} onRename={setRenameTarget} onAction={action} />)}
          <button type="button" onClick={() => setCreateOpen(true)} className="flex min-h-72 flex-col items-center justify-center gap-4 border border-dashed border-[#3e4850] p-5 text-center text-[#bec8d2] transition hover:border-[#89ceff] hover:bg-[#89ceff]/5 hover:text-[#89ceff]"><span className="grid size-14 place-items-center rounded-full border border-dashed border-current">{icon('add', 'text-4xl')}</span><span><strong className="block font-display text-lg">Connect Remote Node</strong><small className="mt-1 block text-sm opacity-70">Provision a new instance in the fleet</small></span></button>
        </div>}
        {!loading && !visible.length && query && <p className="mt-5 text-sm text-[#bec8d2]">No systems match “{query}”.</p>}
        <footer className="mt-10 flex flex-col justify-between gap-4 border-t border-[#3e4850]/60 py-5 font-mono text-[11px] uppercase tracking-wider text-[#bec8d2] lg:flex-row lg:items-center"><div className="flex flex-wrap gap-x-7 gap-y-2"><span>Active clusters: <b className="ml-1 text-lg text-[#89ceff]">{String(active).padStart(2, '0')}</b></span><span>Cache hit: <b className="ml-1 text-lg text-emerald-300">{formatNumber(averageCacheHit, '%')}</b></span><span>Last collection: <b className="ml-1 text-lg text-[#dee3e9]">{relativeTime(latest)}</b></span></div><span>DBVoyager // Fleet Control</span></footer>
      </section>
    </main>
    {createOpen && <CreateConnection onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); void loadConnections(); }} />}
    {renameTarget && <RenameConnection connection={renameTarget} onClose={() => setRenameTarget(null)} onSaved={() => { setRenameTarget(null); void loadConnections(); }} />}
  </div>;
}

function FleetSidebar({ onAdd }: { onAdd: () => void }) {
  const nav = [['dashboard', 'Overview', '/dashboard'], ['dns', 'Connections', '/connections'], ['chat_bubble', 'BI Navigator', '/bi-chat'], ['table_chart', 'Schema Explorer', '/schema-explorer'], ['auto_fix_high', 'Optimizer', '/optimizer'], ['auto_graph', 'Health Checks', '/health-checks'], ['terminal', 'SQL Editor', '/dashboard?section=slow-queries'], ['query_stats', 'Metrics', '/dashboard?section=statistics'], ['settings', 'Settings', '/dashboard?section=settings']];
  return <aside className="hidden min-h-screen border-r border-[#3e4850] bg-[#0f1418] py-4 md:flex md:flex-col"><div className="mb-10 px-7"><h2 className="font-display text-xl font-bold text-[#89ceff]">DBVoyager</h2><p className="mt-1 font-mono text-[10px] tracking-[.17em] text-[#bec8d2]">MISSION CONTROL</p></div><nav className="space-y-1">{nav.map(([name, label, href]) => <Link key={label} to={href} className={`flex items-center gap-3 border-l-2 px-6 py-3 text-sm transition ${label === 'Connections' ? 'border-[#89ceff] bg-[#30353a]/50 text-[#89ceff]' : 'border-transparent text-[#bec8d2] hover:bg-[#252b2f] hover:text-[#dee3e9]'}`}>{icon(name)} {label}</Link>)}</nav><div className="mt-auto border-t border-[#3e4850]/60 px-5 pt-4"><button type="button" onClick={onAdd} className="fleet-button w-full bg-[#89ceff] font-semibold text-[#00344d]">{icon('add')} New Instance</button><a className="mt-5 flex items-center gap-3 text-sm text-[#bec8d2] hover:text-[#dee3e9]" href="/docs">{icon('description', 'text-lg')} Docs</a><span className="mt-3 flex items-center gap-3 text-sm text-[#bec8d2]">{icon('help_outline', 'text-lg')} Support</span></div></aside>;
}

function FleetHeader({ email, query, onQuery }: { email: string; query: string; onQuery: (value: string) => void }) {
  const initial = email.trim().charAt(0).toUpperCase() || 'D';
  return <header className="flex min-h-14 items-center justify-between border-b border-[#3e4850] bg-[#1b2024] px-4 md:px-7"><label className="relative hidden w-72 lg:block">{icon('search', 'absolute left-3 top-1/2 -translate-y-1/2 text-[#bec8d2]')}<input value={query} onChange={event => onQuery(event.target.value)} className="w-full rounded-full border-0 bg-[#0f1418] py-2 pl-10 pr-4 text-sm text-[#dee3e9] outline-none ring-[#89ceff] placeholder:text-[#88929b] focus:ring-1" placeholder="Search systems..." /></label><span className="font-mono text-[10px] tracking-[.16em] text-[#bec8d2] lg:hidden">FLEET CONTROL</span><div className="ml-auto flex items-center gap-3"><span className="hidden border border-amber-400 bg-amber-400/10 px-3 py-1 font-mono text-[10px] tracking-[.13em] text-amber-200 sm:block">PRODUCTION ENVIRONMENT</span><Link to="/dashboard" aria-label="Open notifications" className="text-[#bec8d2] hover:text-[#89ceff]">{icon('notifications')}</Link><Link to="/dashboard?section=slow-queries" aria-label="Open SQL observability" className="text-[#bec8d2] hover:text-[#89ceff]">{icon('terminal')}</Link><Link to="/dashboard?section=settings" aria-label="Open settings" className="text-[#bec8d2] hover:text-[#89ceff]">{icon('settings')}</Link><span aria-label={email || 'DBVoyager user'} className="grid size-8 place-items-center rounded-full border border-[#3e4850] bg-[#252b2f] text-xs font-semibold text-[#89ceff]">{initial}</span></div></header>;
}

function ConnectionCard({ connection, busy, onRename, onAction }: { connection: Connection; busy: string | null; onRename: (connection: Connection) => void; onAction: (connection: Connection, path: string) => Promise<void> }) {
  const state = statusStyle(connection);
  const actionBusy = (path: string) => busy === `${connection.connection_id}:${path}`;
  const host = connection.host ? `${connection.host}${connection.port ? `:${connection.port}` : ''}` : '—';
  const metric = connection.cache_hit_ratio === null || connection.cache_hit_ratio === undefined ? null : Math.max(0, Math.min(100, connection.cache_hit_ratio));
  return <article className={`fleet-card flex min-h-72 flex-col gap-5 p-5 ${connection.archived_at ? 'opacity-60 grayscale hover:opacity-100 hover:grayscale-0' : ''}`}><header className="flex items-start justify-between gap-3"><div className="flex min-w-0 gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-sm bg-[#30353a] text-[#89ceff]">{icon(connection.archived_at ? 'inventory_2' : 'database', 'text-3xl')}</span><div className="min-w-0"><h2 className="break-words font-display text-xl font-semibold">{connection.display_name}</h2><p className="mt-1 font-mono text-[11px] text-[#bec8d2]">PostgreSQL <span className="mx-1">•</span> {relativeTime(connection.last_analyzed_at)}</p></div></div><span className={`flex shrink-0 items-center gap-2 rounded-full border px-2 py-1 font-mono text-[10px] font-bold uppercase ${state.className}`}><i className={`size-1.5 rounded-full ${state.dot} ${connection.status === 'active' && !connection.archived_at ? 'fleet-pulse' : ''}`} />{state.label}</span></header><div className="space-y-3 border-y border-[#3e4850]/50 py-4 text-sm"><div className="flex items-center justify-between gap-4"><span className="text-[#bec8d2]">Host</span><code className="max-w-[65%] truncate rounded bg-[#30353a] px-2 py-1 font-mono text-[11px] text-[#dee3e9]" title={host}>{host}</code></div><div className="flex items-center justify-between gap-4"><span className="text-[#bec8d2]">Database</span><span className="max-w-[65%] truncate font-medium" title={connection.database || undefined}>{connection.database || '—'}</span></div><div className="flex items-center justify-between gap-4"><span className="text-[#bec8d2]">{connection.archived_at ? 'Snapshots' : 'Cache hit'}</span>{connection.archived_at ? <span>{connection.last_analyzed_at ? 'Collected' : '—'}</span> : metric === null ? <span>—</span> : <span className="flex items-center gap-3"><span className="h-1 w-24 overflow-hidden rounded-full bg-[#30353a]"><i className="block h-full bg-emerald-300" style={{ width: `${metric}%` }} /></span>{formatNumber(metric, '%')}</span>}</div></div><footer className="flex gap-2"><Link to={`/dashboard?connection=${encodeURIComponent(connection.connection_id)}`} className="fleet-action flex-1">{icon(connection.archived_at ? 'visibility' : 'speed', 'text-base')} {connection.archived_at ? 'View Only' : 'Dashboard'}</Link>{connection.archived_at ? <button type="button" disabled={actionBusy('/restore')} onClick={() => void onAction(connection, `/connections/${connection.connection_id}/restore`)} className="fleet-icon" aria-label={`Restore ${connection.display_name}`}>{icon('restore')}</button> : <><button type="button" onClick={() => onRename(connection)} className="fleet-icon" aria-label={`Rename ${connection.display_name}`}>{icon('settings')}</button><button type="button" disabled={actionBusy('/reconnect')} onClick={() => void onAction(connection, `/connections/${connection.connection_id}/reconnect`)} className="fleet-icon" aria-label={`Reconnect ${connection.display_name}`}>{icon('network_check')}</button><button type="button" disabled={actionBusy('/archive')} onClick={() => void onAction(connection, `/connections/${connection.connection_id}/archive`)} className="fleet-icon hover:text-red-300" aria-label={`Archive ${connection.display_name}`}>{icon('archive')}</button></>}</footer></article>;
}

function CreateConnection({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [displayName, setDisplayName] = useState('');
  const [connectionUrl, setConnectionUrl] = useState('');
  const [state, setState] = useState('');
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    try {
      setState('Testing connection…');
      await api('/connections/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName, connection_url: connectionUrl }) });
      setState('Saving connection…');
      await api('/connections', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName, connection_url: connectionUrl }) });
      onCreated();
    } catch (reason) { setState(''); setError(reason instanceof Error ? reason.message : 'Could not connect.'); }
  }
  return <Modal title="Add Connection" onClose={onClose}><form onSubmit={submit} className="space-y-4"><p className="text-sm text-[#bec8d2]">Credentials are tested before anything is saved.</p><label className="block text-sm">Connection name<input value={displayName} onChange={event => setDisplayName(event.target.value)} className="fleet-input" placeholder="Production" /></label><label className="block text-sm">PostgreSQL connection URL<input required type="text" value={connectionUrl} onChange={event => setConnectionUrl(event.target.value)} className="fleet-input" placeholder="postgresql://user:password@host:5432/database?sslmode=require" /></label>{error && <p role="alert" className="text-sm text-red-300">{error}</p>}{state && <p className="text-sm text-[#89ceff]">{state}</p>}<button className="fleet-button w-full bg-[#89ceff] font-semibold text-[#00344d]">Test & connect</button></form></Modal>;
}

function RenameConnection({ connection, onClose, onSaved }: { connection: Connection; onClose: () => void; onSaved: () => void }) {
  const [displayName, setDisplayName] = useState(connection.display_name);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); try { await api(`/connections/${connection.connection_id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName }) }); onSaved(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not rename connection.'); } }
  return <Modal title="Connection Settings" onClose={onClose}><form onSubmit={submit} className="space-y-4"><label className="block text-sm">Display name<input required value={displayName} onChange={event => setDisplayName(event.target.value)} className="fleet-input" /></label>{error && <p role="alert" className="text-sm text-red-300">{error}</p>}<button className="fleet-button w-full bg-[#89ceff] font-semibold text-[#00344d]">Save name</button></form></Modal>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 grid place-items-center bg-black/75 p-4 backdrop-blur"><section className="w-full max-w-lg border border-[#89ceff]/30 bg-[#1b2024] p-6 shadow-2xl"><header className="mb-5 flex items-center justify-between"><h2 className="font-display text-2xl font-semibold">{title}</h2><button type="button" onClick={onClose} aria-label="Close dialog" className="text-[#bec8d2] hover:text-[#dee3e9]">{icon('close')}</button></header>{children}</section></div>;
}
