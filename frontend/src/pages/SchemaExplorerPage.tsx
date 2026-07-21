import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { authFetch, authJson, requireOk } from '../lib/auth';
import { trackRouteRequest } from '../lib/routeLoading';
import { getSection } from '../lib/analysisStore';
import CollectingState from '../components/CollectingState';
import { DataTable, Modal, useToast } from '../components/ui';
import { useHeaderSearch } from '../AppShell';

type Connection = { connection_id: string; display_name: string; archived_at?: string | null };
type Column = { column_name: string; data_type: string; is_nullable: boolean; column_default: string | null; primary_key: boolean; foreign_key: boolean };
type Index = { index_name: string; index_definition: string; indexed_columns: string[]; is_unique: boolean };
type Table = { name: string; schema: string; table_type: string; estimated_rows: number | null; summary?: string | null; columns: Column[]; indexes: Index[] };
type Relationship = { source_table: string; source_column: string; target_table: string; target_column: string };
type Metrics = { total_size_bytes?: number | null; table_size_bytes?: number | null; index_size_bytes?: number | null; n_live_tup?: number | null; n_dead_tup?: number | null; seq_scan?: number | null; idx_scan?: number | null; bloat_risk_ratio?: number | null };
type Preview = { columns: string[]; rows: Record<string, unknown>[]; row_count: number };
type SchemaResponse = { data: { tables: Table[]; relationships: Relationship[] }; next_offset: number | null };

async function api<T>(path: string, track = false): Promise<T> { return authJson<T>(path, undefined, false, track); }

const icon = (name: string, className = '') => <span aria-hidden="true" className={`material-symbols-outlined ${className}`}>{name}</span>;
const number = (value: number | null | undefined) => value === null || value === undefined ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 1, notation: value > 999_999 ? 'compact' : 'standard' }).format(value);
const bytes = (value: number | null | undefined) => value === null || value === undefined ? '—' : value >= 1_073_741_824 ? `${(value / 1_073_741_824).toFixed(1)} GB` : `${(value / 1_048_576).toFixed(1)} MB`;
const tableKey = (table: Table) => `${table.schema}.${table.name}`;

export default function SchemaExplorerPage() {
  const { showToast } = useToast();
  const { query: search } = useHeaderSearch();
  const [params, setParams] = useSearchParams();
  const requestedConnection = params.get('connection');
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState('');
  const [tables, setTables] = useState<Table[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [selectedKey, setSelectedKey] = useState('');
  const [type, setType] = useState('all');
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);
  const [error, setError] = useState('');
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    void api<{ data: Connection[] }>('/connections', true).then(result => {
      const active = result.data.filter(item => !item.archived_at);
      setConnections(active); setConnectionId(active.some(item => item.connection_id === requestedConnection) ? requestedConnection || '' : active[0]?.connection_id || '');
    }).catch(reason => { setError(reason.message); setLoading(false); });
  }, [requestedConnection]);

  const loadTables = async (offset = 0) => {
    if (!connectionId) return;
    setLoading(true); setError(''); setCollecting(false);
    try {
      const response = await trackRouteRequest(authFetch(`/connections/${connectionId}/schema/visualizer?limit=200&offset=${offset}`, {}, false), 'Loading schema…');
      if (response.status === 202) { setCollecting(true); setLoading(false); return; }
      const result = await (await requireOk(response)).json() as SchemaResponse;
      setTables(current => offset ? [...current, ...result.data.tables] : result.data.tables);
      setRelationships(current => offset ? [...current, ...result.data.relationships] : result.data.relationships);
      setNextOffset(result.next_offset);
      const requested = params.get('table');
      const first = result.data.tables[0];
      setSelectedKey(current => current || requested || (first ? tableKey(first) : ''));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load schema.'); }
    finally { setLoading(false); }
  };

  useEffect(() => { void loadTables(); }, [connectionId]); // eslint-disable-line react-hooks/exhaustive-deps
  // Rehydrate from cached SSE section data when connection changes
  useEffect(() => { if (!connectionId) return; const cached = getSection(connectionId, 'schema'); const data = cached?.data as { tables: Table[]; relationships: Relationship[] } | undefined; if (data?.tables) { setTables(data.tables); if (data.relationships) setRelationships(data.relationships); } }, [connectionId]);
  const selected = tables.find(table => tableKey(table) === selectedKey);
  useEffect(() => {
    if (!selected || !connectionId) return;
    setMetrics(null);
    void api<Metrics>(`/connections/${connectionId}/schema/tables/${encodeURIComponent(selected.schema)}/${encodeURIComponent(selected.name)}/metrics`).then(setMetrics).catch(reason => setError(reason.message));
  }, [connectionId, selectedKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const visible = useMemo(() => tables.filter(table => (type === 'all' || table.table_type === type) && tableKey(table).toLowerCase().includes(search.trim().toLowerCase())), [tables, type, search]);
  const related = selected ? relationships.filter(item => item.source_table === selected.name || item.target_table === selected.name) : [];
  const bloat = metrics?.bloat_risk_ratio ?? null;
  function select(table: Table) { setSelectedKey(tableKey(table)); setParams({ connection: connectionId, table: tableKey(table) }); }
  async function copy(text: string) { try { await navigator.clipboard.writeText(text); showToast({ tone: 'success', message: 'SQL copied for review.' }); } catch { const message = 'Clipboard access was unavailable.'; setError(message); showToast({ tone: 'error', message }); } }
  async function queryData() { if (!selected) return; try { setPreview(await api<Preview>(`/connections/${connectionId}/schema/tables/${encodeURIComponent(selected.schema)}/${encodeURIComponent(selected.name)}/preview?limit=50`, true)); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not preview this table.'); } }

  return <div className="mx-auto grid max-w-[1600px] gap-6 p-6 md:grid-cols-[280px_minmax(0,1fr)] md:p-10">
    <aside className="voyager-card h-fit"><header className="border-b border-voyager-border p-4"><div className="flex items-center justify-between"><span className="font-mono text-xs uppercase tracking-widest text-voyager-text-secondary">Tables ({tables.length})</span><select aria-label="Filter table type" value={type} onChange={event => setType(event.target.value)} className="bg-transparent text-voyager-blue outline-none">{['all', 'BASE TABLE', 'VIEW', 'FOREIGN TABLE'].map(value => <option className="bg-voyager-surface" key={value} value={value}>{value === 'all' ? 'Filter' : value}</option>)}</select></div></header><div className="max-h-[60vh] overflow-y-auto p-2">{visible.map(table => <button type="button" key={tableKey(table)} onClick={() => select(table)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm ${selected && tableKey(selected) === tableKey(table) ? 'bg-voyager-blue/10 text-voyager-text-primary' : 'text-voyager-text-secondary hover:bg-voyager-surface2'}`}>{icon(table.table_type === 'VIEW' ? 'table_rows' : 'table_chart', tableKey(selected || table) === tableKey(table) ? 'text-voyager-blue' : '')}<span className="min-w-0 flex-1 truncate">{table.name}</span></button>)}{nextOffset !== null && <button type="button" onClick={() => void loadTables(nextOffset)} className="m-2 text-sm text-voyager-blue">Load more tables</button>}</div></aside>
    <main className="min-w-0"><header className="flex min-h-14 items-center justify-end border-b border-[#3e4850] bg-[#1b2024] px-4 md:px-7"><select value={connectionId} onChange={event => { setSelectedKey(''); setConnectionId(event.target.value); setParams({ connection: event.target.value }); }} className="bg-transparent text-sm outline-none">{connections.map(connection => <option className="bg-[#171c20]" key={connection.connection_id} value={connection.connection_id}>{connection.display_name}</option>)}</select></header>
      <section className="mx-auto max-w-[1200px] p-4 md:p-8">{error && <p role="alert" className="mb-5 border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</p>}{collecting && !tables.length ? <CollectingState connectionId={connectionId} message="Schema data is being collected. It will appear once analysis completes." /> : loading && !selected ? <p className="text-[#bec8d2]">Loading schema…</p> : !selected ? <p className="text-[#bec8d2]">No collected schema is available for this connection.</p> : <><header className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-[#3e4850] pb-4"><div><p className="text-sm text-[#bec8d2]">{selected.schema} {icon('chevron_right', 'align-middle text-base')} {connections.find(item => item.connection_id === connectionId)?.display_name || 'database'}</p><h1 className="mt-2 flex items-center gap-3 font-display text-3xl font-semibold">{icon('table_chart', 'text-4xl text-[#89ceff]')}{selected.name}</h1></div><div className="flex gap-3"><button type="button" onClick={() => void copy(`ALTER TABLE ${selected.schema}.${selected.name} -- describe reviewed change here;`)} className="fleet-button border border-[#88929b] bg-transparent text-[#dee3e9]">Edit Table</button><button type="button" onClick={() => void queryData()} className="fleet-button bg-[#89ceff] font-semibold text-[#00344d]">Query Data</button></div></header><div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]"><div className="space-y-6"><section className="fleet-card overflow-hidden"><header className="flex items-center justify-between border-b border-[#3e4850] px-5 py-4"><h2 className="font-display text-xl font-semibold">Columns</h2><span className="bg-[#30353a] px-2 py-1 font-mono text-[10px] text-[#bec8d2]">{selected.columns.length} rows</span></header><div className="overflow-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead className="bg-[#252b2f]/50 font-mono text-[10px] uppercase tracking-widest text-[#bec8d2]"><tr><th className="px-5 py-3">Name</th><th className="px-5 py-3">Type</th><th className="px-5 py-3">Null</th><th className="px-5 py-3">Default</th><th className="px-5 py-3">Extra</th></tr></thead><tbody>{selected.columns.map(column => <tr key={column.column_name} className="border-t border-[#3e4850]/60 hover:bg-[#89ceff]/5"><td className="px-5 py-4 font-mono font-medium">{column.primary_key && icon('key', 'mr-2 text-[#ffb86e] align-middle text-base')}{column.column_name}</td><td className="px-5 py-4 font-mono text-[#bec8d2]">{column.data_type}</td><td className={`px-5 py-4 font-mono ${column.is_nullable ? 'text-[#89ceff]' : 'text-red-300'}`}>{column.is_nullable ? 'YES' : 'NO'}</td><td className="max-w-xs truncate px-5 py-4 font-mono text-[#bec8d2]" title={column.column_default || undefined}>{column.column_default || 'NULL'}</td><td className="px-5 py-4 font-mono text-[10px] text-[#89ceff]">{[column.primary_key && 'PRIMARY KEY', column.foreign_key && 'FOREIGN KEY', selected.indexes.some(index => index.is_unique && index.indexed_columns.includes(column.column_name)) && 'UNIQUE'].filter(Boolean).join(' · ')}</td></tr>)}</tbody></table></div></section><section className="fleet-card p-5"><h2 className="font-display text-xl font-semibold">Entity Relationships</h2><div className="mt-5 grid gap-4 md:grid-cols-2">{related.length ? related.map((relation, index) => { const outgoing = relation.source_table === selected.name, other = outgoing ? relation.target_table : relation.source_table; return <article key={`${relation.source_table}-${relation.source_column}-${index}`} className="relative border border-[#3e4850] bg-[#0a0f13] p-4"><p className="font-mono text-[10px] uppercase tracking-widest text-[#89ceff]">{outgoing ? 'Target table' : 'Source table'} · 1 : N</p><p className="mt-3 font-semibold">{other}</p><p className="mt-3 border-t border-[#3e4850] pt-2 font-mono text-xs text-[#bec8d2]">{outgoing ? `FK: ${relation.source_column} → ${relation.target_column}` : `FK: ${relation.source_column} → ${relation.target_column}`}</p></article>; }) : <p className="text-sm text-[#bec8d2]">No foreign-key relationships were collected for this table.</p>}</div></section></div><aside className="space-y-6"><section className="fleet-card p-5"><h2 className="font-mono text-[11px] uppercase tracking-widest text-[#bec8d2]">Metrics Snapshot</h2><div className="mt-5 grid grid-cols-2 gap-5"><Metric label="Row count" value={number(metrics?.n_live_tup ?? selected.estimated_rows)} /><Metric label="Total size" value={bytes(metrics?.total_size_bytes)} color="text-[#89ceff]" /><Metric label="Index size" value={bytes(metrics?.index_size_bytes)} /><Metric label="Bloat risk" value={bloat === null ? '—' : `${(bloat * 100).toFixed(1)}%`} color="text-[#ffb86e]" /></div></section><section className="fleet-card overflow-hidden"><header className="flex items-center justify-between border-b border-[#3e4850] px-5 py-4"><h2 className="font-display text-xl font-semibold">Indexes</h2>{icon('add', 'text-[#89ceff]')}</header><div className="space-y-3 p-4">{selected.indexes.length ? selected.indexes.map(index => <article key={index.index_name} className="border border-[#3e4850] bg-[#252b2f]/30 p-3"><div className="flex justify-between gap-2"><code className="truncate text-xs text-[#89ceff]" title={index.index_name}>{index.index_name}</code><span className="bg-[#30353a] px-1.5 py-0.5 font-mono text-[9px] text-[#bec8d2]">{index.index_definition.match(/USING\s+(\w+)/i)?.[1]?.toUpperCase() || 'INDEX'}</span></div><p className="mt-3 text-sm">{index.indexed_columns.join(', ') || 'Expression index'}</p><p className="mt-3 text-[10px] text-[#bec8d2]">{index.is_unique ? '◉ Unique' : '◉ Active'}</p></article>) : <p className="text-sm text-[#bec8d2]">No indexes collected.</p>}</div></section>{bloat !== null && bloat >= .2 && <section className="border border-[#ffb86e]/30 bg-[#de8712]/10 p-4"><div className="flex gap-3"><span className="text-[#ffb86e]">{icon('info')}</span><div><h3 className="font-semibold text-[#ffb86e]">Optimization Suggested</h3><p className="mt-2 text-sm leading-6 text-[#bec8d2]">Dead tuples are {(bloat * 100).toFixed(1)}% of collected tuples. Review autovacuum and reclaim space with DBA approval.</p><button type="button" onClick={() => void copy(`VACUUM (ANALYZE) ${selected.schema}.${selected.name};`)} className="mt-3 text-xs font-bold uppercase tracking-widest text-[#ffb86e] underline">Copy maintenance SQL</button></div></div></section>}</aside></div></>}</section></main>
    <button type="button" onClick={() => setDrawer(value => !value)} className="fixed bottom-6 right-6 grid size-14 place-items-center rounded-full bg-[#89ceff] text-[#00344d] shadow-xl" aria-label="Toggle schema assistant">{icon(drawer ? 'close' : 'auto_awesome', 'text-2xl')}</button>{drawer && <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-md border-l border-[#3e4850] bg-[#171c20] p-6 shadow-2xl"><header className="flex items-center justify-between"><div><p className="font-mono text-[10px] tracking-widest text-[#89ceff]">AI VOYAGER</p><h2 className="font-display text-2xl font-semibold">Schema context</h2></div><button type="button" onClick={() => setDrawer(false)}>{icon('close')}</button></header><p className="mt-8 text-sm leading-7 text-[#bec8d2]">{selected?.summary || 'No business summary has been generated for this table yet.'}</p><p className="mt-5 border border-[#3e4850] bg-[#0f1418] p-4 text-sm text-[#bec8d2]">{selected ? `${selected.columns.length} columns · ${selected.indexes.length} indexes · ${related.length} relationships` : 'Select a table to inspect its schema.'}</p></aside>}{preview && <PreviewModal preview={preview} table={selected} onClose={() => setPreview(null)} />}
  </div>;
}

function Metric({ label, value, color = 'text-[#dee3e9]' }: { label: string; value: string; color?: string }) { return <div><p className="text-sm text-[#bec8d2]">{label}</p><p className={`mt-1 font-mono text-2xl ${color}`}>{value}</p></div>; }
function PreviewModal({ preview, table, onClose }: { preview: Preview; table?: Table; onClose: () => void }) { return <Modal title={table ? `${table.schema}.${table.name} preview` : 'Table preview'} onClose={onClose} className="max-w-6xl"><p className="-mt-3 mb-5 text-sm text-voyager-text-secondary">Read-only · {preview.row_count} rows · limit 50</p><DataTable<Record<string, unknown>> columns={preview.columns.map(column => ({ id: column, header: column, cell: row => typeof row[column] === 'object' ? JSON.stringify(row[column]) : String(row[column] ?? 'NULL'), sortValue: row => String(row[column] ?? '') }))} rows={preview.rows} rowKey={(_, index) => String(index)} /></Modal>; }
