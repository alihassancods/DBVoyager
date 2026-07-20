import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { authJson } from '../lib/auth';

type Connection = { connection_id: string; display_name: string; archived_at?: string | null };
type SlowQuery = { query_id: string; query: string; calls: number | null; total_exec_time: number | null; mean_exec_time: number | null; rows_returned: number | null; collected_at: string | null };

async function api<T>(path: string, force = false): Promise<T> { return authJson<T>(path, undefined, force); }

const metric = (value: number | null, unit = '') => value === null ? '—' : `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)}${unit}`;

export default function OptimizerPage() {
  const [params] = useSearchParams();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState('');
  const [queries, setQueries] = useState<SlowQuery[]>([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    void api<{ data: Connection[] }>('/connections').then(result => {
      const active = result.data.filter(item => !item.archived_at);
      const selected = params.get('connection');
      setConnections(active);
      setConnectionId(active.some(item => item.connection_id === selected) ? selected || '' : active[0]?.connection_id || '');
    }).catch(reason => { setError(reason.message); setLoading(false); });
  }, [params]);

  const loadQueries = (force = false) => {
    if (!connectionId) { setLoading(false); return; }
    setLoading(true); setError('');
    void api<{ data: SlowQuery[] }>(`/connections/${connectionId}/optimizer/slow-queries?limit=50`, force).then(result => setQueries(result.data)).catch(reason => setError(reason.message)).finally(() => setLoading(false));
  };
  useEffect(() => { loadQueries(); }, [connectionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return needle ? queries.filter(item => item.query.toLowerCase().includes(needle)) : queries;
  }, [filter, queries]);
  const totalTime = queries.reduce((total, query) => total + (query.total_exec_time || 0), 0);

  return <div className="min-h-screen bg-[#0f1418] text-[#dee3e9]"><header className="flex min-h-14 items-center justify-between border-b border-[#3e4850] bg-[#1b2024] px-4 md:px-7"><Link to="/connections" className="text-sm text-[#bec8d2] hover:text-[#89ceff]">← Connections</Link><span className="border border-amber-400 bg-amber-400/10 px-3 py-1 font-mono text-[10px] tracking-[.13em] text-amber-200">PRODUCTION ENVIRONMENT</span></header><section className="mx-auto max-w-[1600px] p-4 md:p-8"><header className="mb-8 flex flex-col justify-between gap-4 lg:flex-row lg:items-end"><div><p className="font-mono text-[11px] tracking-[.15em] text-[#89ceff]">READ-ONLY QUERY ANALYSIS</p><h1 className="mt-2 font-display text-4xl font-semibold">Query Optimizer</h1><p className="mt-2 text-sm text-[#bec8d2]">Persisted slow-query snapshots only. Recommendations never execute database changes.</p></div><div className="flex flex-wrap gap-3"><select value={connectionId} onChange={event => setConnectionId(event.target.value)} className="border border-[#3e4850] bg-[#171c20] px-3 py-2 text-sm outline-none"><option value="">Select a connection</option>{connections.map(connection => <option key={connection.connection_id} value={connection.connection_id}>{connection.display_name}</option>)}</select><input value={filter} onChange={event => setFilter(event.target.value)} className="border border-[#3e4850] bg-[#171c20] px-3 py-2 text-sm outline-none placeholder:text-[#88929b]" placeholder="Filter SQL…" /><button type="button" onClick={() => loadQueries(true)} className="fleet-button border border-[#88929b] bg-[#252b2f] text-[#dee3e9]">Refresh</button></div></header>
      <div className="mb-6 grid gap-4 sm:grid-cols-3"><article className="fleet-card p-5"><p className="font-mono text-[10px] tracking-widest text-[#bec8d2]">SLOW QUERIES</p><p className="mt-3 font-mono text-3xl text-[#89ceff]">{queries.length}</p></article><article className="fleet-card p-5"><p className="font-mono text-[10px] tracking-widest text-[#bec8d2]">RECORDED TOTAL TIME</p><p className="mt-3 font-mono text-3xl">{metric(totalTime, ' ms')}</p></article><article className="fleet-card p-5"><p className="font-mono text-[10px] tracking-widest text-[#bec8d2]">DATA SOURCE</p><p className="mt-3 text-lg text-emerald-300">● Persisted snapshots</p></article></div>
      {error && <p role="alert" className="mb-5 border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p>}
      <section className="fleet-card overflow-hidden"><header className="border-b border-[#3e4850] px-5 py-4"><h2 className="font-display text-xl font-semibold">Prioritized queries</h2></header>{loading ? <p className="p-6 text-sm text-[#bec8d2]">Loading persisted slow queries…</p> : !connectionId ? <p className="p-6 text-sm text-[#bec8d2]">Connect a database to inspect query snapshots.</p> : !visible.length ? <p className="p-6 text-sm text-[#bec8d2]">No stored slow queries match this view.</p> : <div className="divide-y divide-[#3e4850]">{visible.map(query => <article key={query.query_id} className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center"><div className="min-w-0"><code className="block truncate font-mono text-sm text-[#b8e5ff]" title={query.query}>{query.query}</code><div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-[#bec8d2]"><span>MEAN {metric(query.mean_exec_time, ' ms')}</span><span>TOTAL {metric(query.total_exec_time, ' ms')}</span><span>CALLS {metric(query.calls)}</span><span>ROWS {metric(query.rows_returned)}</span></div></div><Link to={`/connections/${encodeURIComponent(connectionId)}/optimizer/queries/${encodeURIComponent(query.query_id)}`} className="fleet-button border border-[#89ceff] bg-[#89ceff] text-center font-semibold text-[#00344d]">Analyze safely</Link></article>)}</div>}</section>
    </section>
  </div>;
}
