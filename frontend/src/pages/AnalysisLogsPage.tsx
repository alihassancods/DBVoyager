import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { authFetch, authJson } from '../lib/auth';
import { getRunEvents, getRunList, setRunEvents, setRunList, type AnalysisEvent, type AnalysisRunSummary } from '../lib/analysisStore';

type Connection = { connection_id: string; display_name: string; archived_at?: string | null };

const api = <T,>(path: string) => authJson<T>(path);
const icon = (name: string, className = '') => <span aria-hidden="true" className={`material-symbols-outlined ${className}`}>{name}</span>;
const ts = (iso: string | null) => iso ? new Date(iso).toLocaleTimeString() : '—';
const running = (s: string) => s === 'queued' || s === 'running';

export default function AnalysisLogsPage() {
  const [params, setParams] = useSearchParams();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState('');
  const [runs, setRuns] = useState<AnalysisRunSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const sseRef = useRef<AbortController | null>(null);
  const [streamRetry, setStreamRetry] = useState(0);

  // Load connections list
  useEffect(() => {
    void api<{ data: Connection[] }>('/connections').then(result => {
      const active = result.data.filter((item: Connection) => !item.archived_at);
      const requested = params.get('connection');
      setConnections(active);
      setConnectionId(active.some((item: Connection) => item.connection_id === requested) ? requested || '' : active[0]?.connection_id || '');
    }).catch(reason => { setError(reason.message); setLoading(false); });
  }, [params]);

  // Load run list when connection changes
  useEffect(() => {
    if (!connectionId) { setLoading(false); return; }
    const cached = getRunList(connectionId);
    if (cached) setRuns(cached);
    setLoading(true); setError(''); setSelectedId(null); setEvents([]);
    void api<{ data: AnalysisRunSummary[] }>(`/connections/${connectionId}/analysis/logs`).then(result => {
      setRuns(result.data);
      setRunList(connectionId, result.data);
      // Select the first active run, or the latest
      const active = result.data.find(r => running(r.status));
      setSelectedId(active ? active.id : result.data[0]?.id || null);
    }).catch(reason => setError(reason.message)).finally(() => setLoading(false));
  }, [connectionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load events when selected run changes
  useEffect(() => {
    if (!connectionId || !selectedId) { setEvents([]); return; }
    const cached = getRunEvents(connectionId, selectedId);
    if (cached) setEvents(cached);
    setError('');
    void api<{ data: AnalysisEvent[] }>(`/connections/${connectionId}/analysis/logs/${selectedId}/events`).then(result => {
      setEvents(result.data);
      setRunEvents(connectionId, selectedId, result.data);
    }).catch(reason => setError(reason.message));
  }, [connectionId, selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  // SSE live updates when selected run is active
  useEffect(() => {
    if (!connectionId || !selectedId) return;
    // Close previous SSE
    if (sseRef.current) { sseRef.current.abort(); sseRef.current = null; }
    const run = runs.find(r => r.id === selectedId);
    if (!run || !running(run.status)) return;
    const controller = new AbortController();
    sseRef.current = controller;
    let retryTimer: number | undefined;

    void authFetch(`/connections/${connectionId}/analysis-runs/${selectedId}/stream`, { signal: controller.signal }, false)
      .then(async response => {
        if (!response.ok || !response.body) return;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          buffer += decoder.decode(part.value, { stream: true });
          const messages = buffer.split('\n\n');
          buffer = messages.pop() || '';
          for (const msg of messages) {
            const raw = msg.match(/^data: (.+)$/m)?.[1];
            if (!raw) continue;
            const event = msg.match(/^event: (.+)$/m)?.[1];
            if (event === 'progress') {
              // Parse progress event and add to live events
              try {
                const parsed = JSON.parse(raw) as { stage?: string; message?: string };
                if (parsed.stage && parsed.message) {
                  const newEv: AnalysisEvent = { id: Date.now(), stage: parsed.stage, message: parsed.message, created_at: new Date().toISOString() };
                  setEvents(prev => [...prev, newEv]);
                  if (connectionId && selectedId) appendLiveEvents(connectionId, selectedId, [newEv]);
                }
              } catch { /* ignore */ }
            } else if (event === 'data_ready' || event === 'complete') {
              // Refresh run list when analysis completes
              void api<{ data: AnalysisRunSummary[] }>(`/connections/${connectionId}/analysis/logs`).then(result => {
                setRuns(result.data);
                setRunList(connectionId, result.data);
              });
            } else if (event === 'error') {
              setError('Analysis encountered an error.');
            }
          }
        }
      })
      .catch(() => undefined)
      .finally(() => { if (!controller.signal.aborted) retryTimer = window.setTimeout(() => setStreamRetry(value => value + 1), 1_000); });

    return () => { controller.abort(); if (retryTimer) window.clearTimeout(retryTimer); };
  }, [connectionId, selectedId, runs, streamRetry]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedRun = runs.find(r => r.id === selectedId);
  const badge = (status: string) => {
    const m: Record<string, string> = { running: 'bg-voyager-blue text-white', succeeded: 'bg-emerald-600 text-white', failed: 'bg-red-500 text-white', queued: 'bg-amber-500 text-black', cancelled: 'bg-voyager-text-muted text-white' };
    return `px-2 py-0.5 rounded text-[10px] font-mono font-bold ${m[status] || 'bg-voyager-surface2 text-voyager-text-secondary'}`;
  };

  return <section className="mx-auto max-w-[1400px] p-6 md:p-10">
    <header className="mb-8 flex flex-col justify-between gap-4 lg:flex-row lg:items-end"><div><p className="font-mono text-xs tracking-[.16em] text-voyager-blue">ANALYSIS ENGINE</p><h1 className="mt-2 font-display text-3xl font-semibold">Analysis Logs</h1><p className="mt-2 text-base text-voyager-text-secondary">Real-time transparency into database analysis runs.</p></div><select value={connectionId} onChange={event => { setConnectionId(event.target.value); setParams({ connection: event.target.value }); }} className="ui-input m-0 w-auto" aria-label="Selected database">{connections.map(item => <option key={item.connection_id} value={item.connection_id}>{item.display_name}</option>)}</select></header>
    {error && <p role="alert" className="mb-5 border border-red-400/40 bg-red-500/10 p-4 text-sm text-red-200">{error}</p>}
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      {/* Run list */}
      <aside className="voyager-card h-fit max-h-[70vh] overflow-y-auto">
        <header className="border-b border-voyager-border px-4 py-3"><p className="font-mono text-xs tracking-wider text-voyager-text-secondary">ANALYSIS RUNS ({runs.length})</p></header>
        {loading ? <p className="p-4 text-sm text-voyager-text-secondary">Loading runs…</p> : !runs.length ? <p className="p-4 text-sm text-voyager-text-secondary">No analysis runs yet.</p> : <div className="divide-y divide-voyager-border">{runs.map(run => <button key={run.id} type="button" onClick={() => setSelectedId(run.id)} className={`flex w-full items-center gap-3 px-4 py-3 text-left text-sm transition ${selectedId === run.id ? 'bg-voyager-blue/10 text-voyager-text-primary' : 'text-voyager-text-secondary hover:bg-voyager-surface2'}`}><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="truncate font-medium">{run.collection_kind}</span><span className={badge(run.status)}>{run.status}</span></div><p className="mt-0.5 truncate text-[11px] text-voyager-text-muted">{run.trigger} · {ts(run.created_at)}{running(run.status) ? icon('sync', 'ml-1 animate-spin text-[11px] align-middle') : null}</p></div><span className="text-[10px] text-voyager-text-muted">{run.event_count} events</span></button>)}</div>}
      </aside>
      {/* Event timeline */}
      <main className="min-w-0">
        {!selectedRun ? <div className="voyager-card grid min-h-[40vh] place-items-center p-6 text-center"><p className="text-voyager-text-secondary">Select an analysis run to view its event log.</p></div> : <div className="voyager-card overflow-hidden">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-voyager-border bg-voyager-surface px-5 py-4"><div><h2 className="font-display text-lg font-semibold">{selectedRun.collection_kind} <span className="font-mono text-xs text-voyager-text-muted">({selectedRun.trigger})</span></h2><p className="mt-1 text-sm text-voyager-text-secondary">{selectedRun.started_at ? `Started ${ts(selectedRun.started_at)}` : 'Not started'} {selectedRun.finished_at ? `· Finished ${ts(selectedRun.finished_at)}` : ''}</p></div><div className="flex gap-2"><span className={badge(selectedRun.status)}>{selectedRun.status}</span>{running(selectedRun.status) && <span className="flex items-center gap-1 text-xs text-voyager-blue">{icon('sync', 'animate-spin text-sm')}Live</span>}</div></header>
          {selectedRun.error_message && <div className="border-b border-red-400/40 bg-red-500/10 px-5 py-3 text-sm text-red-200">{selectedRun.error_message}</div>}
          {!events.length ? <p className="p-6 text-sm text-voyager-text-secondary">No events recorded for this run.</p> : <div className="max-h-[50vh] overflow-y-auto"><table className="w-full text-left text-sm"><thead><tr className="sticky top-0 bg-voyager-navy text-[10px] font-mono uppercase tracking-wider text-voyager-text-secondary"><th className="px-5 py-3">Time</th><th className="px-5 py-3">Stage</th><th className="px-5 py-3">Message</th></tr></thead><tbody>{events.map(ev => <tr key={ev.id} className="border-t border-voyager-border/40 hover:bg-voyager-surface2/50"><td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-voyager-text-muted">{ts(ev.created_at)}</td><td className="px-5 py-3"><span className="rounded bg-voyager-surface2 px-2 py-0.5 font-mono text-[10px] text-voyager-blue">{ev.stage}</span></td><td className="px-5 py-3 text-voyager-text-secondary">{ev.message}</td></tr>)}</tbody></table></div>}
          <footer className="border-t border-voyager-border px-5 py-3 text-right"><Link to={`/dashboard?connection=${encodeURIComponent(connectionId)}`} className="text-xs text-voyager-blue underline">Go to dashboard</Link></footer>
        </div>}
      </main>
    </div>
  </section>;
}

function appendLiveEvents(connectionId: string, runId: string, events: AnalysisEvent[]): void {
  try {
    const existing = getRunEvents(connectionId, runId) || [];
    existing.push(...events);
    setRunEvents(connectionId, runId, existing);
  } catch { /* best-effort */ }
}
