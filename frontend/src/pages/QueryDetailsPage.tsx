import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { authJson } from '../lib/auth';
import { Skeleton, useToast } from '../components/ui';
import { useHeaderSearch } from '../AppShell';

type QueryDetail = {
  query_id: string; query: string; calls: number | null; total_exec_time: number | null;
  mean_exec_time: number | null; rows_returned: number | null; collected_at: string | null;
  cache_hit_ratio: number | null;
};
type Optimization = { optimization_id: string; original_query: string; optimized_query: string; explanation: string; index_recommendations: string[] };
type Comparison = { original_cost?: number; optimized_cost?: number; improvement_percent?: number };
type PlanResponse = { costs: { startup_cost: number; total_cost: number; plan_rows: number }; raw_plan: unknown };
type AuditEvent = { event_id: string; event_type: string; created_at: string; metadata?: Record<string, unknown> };
type PlanNode = { operation: string; cost: number | null; rows: number | null; detail: string };

async function api<T>(path: string, init?: RequestInit): Promise<T> { return authJson<T>(path, init); }

const icon = (name: string, className = '') => <span aria-hidden="true" className={`material-symbols-outlined ${className}`}>{name}</span>;
const number = (value: number | null | undefined, suffix = '') => value === null || value === undefined ? '—' : `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)}${suffix}`;
const queryLabel = (id: string) => `QX-${id.slice(-8).toUpperCase()}`;

function nodes(value: unknown): PlanNode[] {
  const root = Array.isArray(value) ? value[0] : value;
  const found: PlanNode[] = [];
  const visit = (item: unknown) => {
    if (!item || typeof item !== 'object') return;
    const record = item as Record<string, unknown>;
    const plan = record.Plan && typeof record.Plan === 'object' ? record.Plan as Record<string, unknown> : record;
    if (typeof plan['Node Type'] === 'string') {
      found.push({ operation: plan['Node Type'], cost: typeof plan['Total Cost'] === 'number' ? plan['Total Cost'] : null, rows: typeof plan['Plan Rows'] === 'number' ? plan['Plan Rows'] : null, detail: [plan['Relation Name'], plan.Alias].filter(Boolean).join(' · ') || '—' });
    }
    const children = plan.Plans;
    if (Array.isArray(children)) children.forEach(visit);
  };
  visit(root);
  return found;
}

export default function QueryDetailsPage() {
  const { showToast } = useToast();
  const { query } = useHeaderSearch();
  const { connectionId = '', queryId = '' } = useParams();
  const [detail, setDetail] = useState<QueryDetail | null>(null);
  const [optimization, setOptimization] = useState<Optimization | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [drawer, setDrawer] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const planNodes = useMemo(() => (plan ? nodes(plan.raw_plan) : []).filter(node => !query || `${node.operation} ${node.detail}`.toLowerCase().includes(query.toLowerCase())), [plan, query]);
  const visibleAudit = useMemo(() => audit.filter(event => !query || event.event_type.toLowerCase().includes(query.toLowerCase())), [audit, query]);

  useEffect(() => {
    if (!connectionId || !queryId) return;
    setLoading(true); setError('');
    void Promise.all([
      api<QueryDetail>(`/connections/${connectionId}/optimizer/queries/${queryId}`),
      api<{ data: AuditEvent[] }>(`/connections/${connectionId}/audit-events?limit=10`),
    ]).then(([query, events]) => { setDetail(query); setAudit(events.data); }).catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load query details.')).finally(() => setLoading(false));
  }, [connectionId, queryId]);

  async function optimize() {
    if (!detail) return;
    setBusy('optimize'); setError(''); setDismissed(false);
    try {
      const result = await api<Optimization>(`/connections/${connectionId}/optimizer/optimizations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query_id: queryId }) });
      setOptimization(result);
      try { setComparison(await api<Comparison>(`/connections/${connectionId}/optimizer/optimizations/compare`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ original_query: result.original_query, optimized_query: result.optimized_query }) })); } catch { setComparison(null); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Optimization could not be produced.'); } finally { setBusy(''); }
  }

  async function explain() {
    setBusy('plan'); setError('');
    try { setPlan(await api<PlanResponse>(`/connections/${connectionId}/optimizer/queries/${queryId}/plan`, { method: 'POST' })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Explain plan could not be generated.'); }
    finally { setBusy(''); }
  }

  async function copy(text: string, feedback?: 'useful' | 'not_useful', note?: string) {
    try {
      await navigator.clipboard.writeText(text);
      if (feedback && optimization) await api(`/connections/${connectionId}/optimizer/optimizations/${optimization.optimization_id}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ feedback, note }) });
      showToast({ tone: 'success', message: 'Copied for review.' });
    } catch { const message = 'Clipboard access was unavailable.'; setError(message); showToast({ tone: 'error', message }); }
  }

  async function dismiss() {
    setDismissed(true);
    if (optimization) await api(`/connections/${connectionId}/optimizer/optimizations/${optimization.optimization_id}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ feedback: 'not_useful', note: 'Dismissed in query detail' }) }).catch(() => undefined);
  }

  if (loading) return <main className="grid min-h-screen place-items-center bg-voyager-navy p-6"><Skeleton className="h-72 w-full max-w-5xl" /></main>;
  if (!detail) return <main className="grid min-h-screen place-items-center bg-[#0f1418] p-6 text-red-200">{error || 'Query detail was not found.'}</main>;
  const recommendation = optimization && !dismissed;
  const recommendedText = optimization ? [optimization.optimized_query, ...optimization.index_recommendations.map(index => `-- Suggested index (review before running):\n${index}`)].join('\n\n') : '';

  return <div className="min-h-screen bg-[#0f1418] text-[#dee3e9]">
    <main className="min-w-0">
      <section className="mx-auto max-w-[1600px] p-4 md:p-8"><div className="mb-6 flex flex-wrap items-center gap-2 text-sm text-[#bec8d2]"><Link to={`/dashboard?connection=${connectionId}&section=optimizer`} className="hover:text-[#89ceff]">Optimizer</Link>{icon('chevron_right', 'text-base')}<span>Query Detail</span></div><header className="mb-7 flex flex-col justify-between gap-4 lg:flex-row lg:items-end"><div><p className="font-mono text-[11px] tracking-[.15em] text-[#89ceff]">SLOW QUERY ANALYSIS</p><h1 className="mt-2 font-display text-3xl font-semibold">Optimizer <span className="text-[#89ceff]">{queryLabel(detail.query_id)}</span></h1><p className="mt-2 text-sm text-[#bec8d2]">Collected {detail.collected_at ? new Date(detail.collected_at).toLocaleString() : '—'} · {number(detail.calls)} calls</p></div><div className="flex gap-3"><button type="button" onClick={() => setAuditOpen(value => !value)} className="fleet-button border border-[#88929b] bg-transparent text-[#dee3e9]">{icon('history', 'text-lg')} Audit Logs</button><button type="button" disabled={busy === 'optimize'} onClick={() => void optimize()} className="fleet-button bg-[#89ceff] font-semibold text-[#00344d]">{icon('auto_fix_high', 'text-lg')}{busy === 'optimize' ? 'Optimizing…' : 'Optimize Now'}</button></div></header>
        {error && <p role="alert" className="mb-5 border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p>}
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[['Mean exec. time', number(detail.mean_exec_time, ' ms'), 'Per recorded call', 'timer'], ['Total time', number(detail.total_exec_time, ' ms'), 'Latest collection', 'query_stats'], ['Rows returned', number(detail.rows_returned), 'Recorded snapshot', 'table_rows'], ['Cache hit', number(detail.cache_hit_ratio, '%'), 'Database buffer cache', 'memory']].map(([label, metric, note, glyph]) => <article key={label} className="fleet-card p-5"><div className="flex justify-between text-[#bec8d2]"><span className="font-mono text-[10px] uppercase tracking-widest">{label}</span>{icon(glyph, 'text-[#89ceff]')}</div><p className="mt-5 font-mono text-3xl text-[#dee3e9]">{metric}</p><p className="mt-2 text-xs text-[#bec8d2]">{note}</p></article>)}</div>
        <section className="fleet-card mb-6 overflow-hidden"><header className="flex items-center justify-between border-b border-[#3e4850] px-5 py-4"><div><h2 className="font-display text-xl font-semibold">SQL statement</h2><span className="font-mono text-[10px] tracking-widest text-[#89ceff]">POSTGRESQL · READ ONLY</span></div><button type="button" onClick={() => void copy(detail.query)} className="fleet-icon" aria-label="Copy SQL">{icon('content_copy')}</button></header><pre className="overflow-auto bg-[#080c0f] p-5 font-mono text-sm leading-7 text-[#b8e5ff]"><code>{detail.query}</code></pre></section>
        {recommendation && <section className="fleet-card mb-6 overflow-hidden border-[#89ceff]/50"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#3e4850] bg-[#89ceff]/5 px-5 py-4"><div><p className="font-mono text-[10px] tracking-widest text-[#89ceff]">AI OPTIMIZATION SUGGESTION</p><h2 className="mt-1 font-display text-xl font-semibold">Safe recommendation ready for review</h2></div><span className="border border-emerald-400/40 px-2 py-1 font-mono text-[10px] text-emerald-300">NO DDL EXECUTED</span></header><div className="grid gap-5 p-5 xl:grid-cols-[1.4fr_.8fr]"><div><p className="text-sm leading-6 text-[#bec8d2]">{optimization.explanation}</p><h3 className="mt-5 font-mono text-[11px] tracking-widest text-[#89ceff]">PROPOSED QUERY</h3><pre className="mt-2 overflow-auto border border-[#3e4850] bg-[#080c0f] p-4 text-xs text-[#b8e5ff]"><code>{optimization.optimized_query}</code></pre></div><div className="border border-[#3e4850] bg-[#171c20] p-4"><h3 className="font-mono text-[11px] tracking-widest text-[#89ceff]">PROPOSED INDEXES</h3>{optimization.index_recommendations.length ? <ul className="mt-4 space-y-3 text-sm text-[#bec8d2]">{optimization.index_recommendations.map((item, index) => <li key={index} className="border-l-2 border-[#89ceff] pl-3"><code className="break-words text-xs">{item}</code></li>)}</ul> : <p className="mt-4 text-sm text-[#bec8d2]">No index change was recommended.</p>}<div className="mt-6 border-t border-[#3e4850] pt-4"><p className="font-mono text-[10px] tracking-widest text-[#bec8d2]">ESTIMATED COST IMPACT</p><p className="mt-2 font-mono text-2xl text-emerald-300">{comparison?.improvement_percent === undefined ? '—' : `${number(comparison.improvement_percent, '%')} lower`}</p><div className="mt-3 h-2 overflow-hidden bg-[#30353a]"><i className="block h-full bg-emerald-300" style={{ width: `${Math.max(0, Math.min(100, comparison?.improvement_percent || 0))}%` }} /></div></div></div></div><footer className="flex flex-wrap gap-3 border-t border-[#3e4850] px-5 py-4"><button type="button" disabled={busy === 'plan'} onClick={() => void explain()} className="fleet-button border border-[#88929b] bg-transparent text-[#dee3e9]">{icon('account_tree', 'text-lg')}{busy === 'plan' ? 'Loading plan…' : 'Explain Plan'}</button><button type="button" onClick={() => void copy(recommendedText, 'useful', 'Copied for review')} className="fleet-button bg-[#89ceff] font-semibold text-[#00344d]">{icon('content_copy', 'text-lg')} Copy for Review</button><button type="button" onClick={() => void dismiss()} className="fleet-button border border-[#88929b] bg-transparent text-[#bec8d2]">Dismiss</button></footer></section>}
        <section className="fleet-card overflow-hidden"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#3e4850] px-5 py-4"><div><h2 className="font-display text-xl font-semibold">Node Breakdown</h2><p className="mt-1 text-sm text-[#bec8d2]">Plain EXPLAIN estimates only; this never runs the query.</p></div><button type="button" disabled={busy === 'plan'} onClick={() => void explain()} className="text-sm text-[#89ceff]">{plan ? 'Refresh plan' : 'Load explain plan'} ›</button></header>{plan ? <div className="overflow-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead className="bg-[#171c20] font-mono text-[10px] tracking-widest text-[#bec8d2]"><tr><th className="px-5 py-3">OPERATION</th><th className="px-5 py-3">DETAIL</th><th className="px-5 py-3">EST. COST</th><th className="px-5 py-3">PLAN ROWS</th><th className="px-5 py-3">ACTUAL TIME</th></tr></thead><tbody>{planNodes.map((node, index) => <tr key={`${node.operation}-${index}`} className="border-t border-[#3e4850]"><td className="px-5 py-4 font-medium">{node.operation}</td><td className="px-5 py-4 text-[#bec8d2]">{node.detail}</td><td className="px-5 py-4 font-mono">{number(node.cost)}</td><td className="px-5 py-4 font-mono">{number(node.rows)}</td><td className="px-5 py-4 text-[#bec8d2]">—</td></tr>)}</tbody></table><footer className="border-t border-[#3e4850] px-5 py-3 font-mono text-[10px] tracking-widest text-[#bec8d2]">ROOT ESTIMATE · STARTUP {number(plan.costs.startup_cost)} · TOTAL {number(plan.costs.total_cost)} · ROWS {number(plan.costs.plan_rows)}</footer></div> : <p className="p-6 text-sm text-[#bec8d2]">Load a plain EXPLAIN to inspect planner estimates.</p>}</section>
        {auditOpen && <section className="fleet-card mt-6"><header className="flex items-center justify-between border-b border-[#3e4850] px-5 py-4"><h2 className="font-display text-lg font-semibold">Connection audit log</h2><button type="button" onClick={() => setAuditOpen(false)} className="fleet-icon">{icon('close')}</button></header><div className="divide-y divide-[#3e4850]">{visibleAudit.length ? visibleAudit.map(event => <div key={event.event_id} className="flex justify-between gap-5 p-4 text-sm"><span>{event.event_type.replaceAll('_', ' ')}</span><time className="shrink-0 text-[#bec8d2]">{new Date(event.created_at).toLocaleString()}</time></div>) : <p className="p-4 text-sm text-[#bec8d2]">No audit events match this search.</p>}</div></section>}
      </section></main>
    <button type="button" onClick={() => setDrawer(value => !value)} className="fixed bottom-6 right-6 grid size-14 place-items-center rounded-full bg-[#89ceff] text-[#00344d] shadow-xl" aria-label="Toggle recommendation context">{icon(drawer ? 'close' : 'smart_toy')}</button>
    {drawer && <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-md border-l border-[#3e4850] bg-[#171c20] p-6 shadow-2xl"><header className="flex items-center justify-between"><div><p className="font-mono text-[10px] tracking-widest text-[#89ceff]">AI VOYAGER</p><h2 className="font-display text-2xl font-semibold">Recommendation context</h2></div><button type="button" onClick={() => setDrawer(false)} className="fleet-icon">{icon('close')}</button></header><div className="mt-8 space-y-5 text-sm leading-6 text-[#bec8d2]">{optimization ? <><p>{optimization.explanation}</p><div className="border border-[#3e4850] bg-[#0f1418] p-4"><p className="font-mono text-[10px] tracking-widest text-[#89ceff]">REVIEW BOUNDARY</p><p className="mt-2">DBVoyager can copy the recommendation, but it will not execute an index or change this database.</p></div></> : <p>Run Optimize Now to request a read-only recommendation for this stored query.</p>}<input disabled value="Recommendation context only" className="w-full border border-[#3e4850] bg-[#0f1418] px-3 py-3 text-[#88929b]" /></div></aside>}
  </div>;
}
