import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { NotificationBell, NotificationProvider } from './components/notifications';

const nav = [
  ['dashboard', 'Dashboard', '/dashboard'],
  ['dns', 'Connections', '/connections'],
  ['chat_bubble', 'BI Navigator', '/bi-chat'],
  ['query_stats', 'Query Optimizer', '/optimizer'],
  ['table_chart', 'Schema Explorer', '/schema-explorer'],
  ['auto_graph', 'Health Checks', '/health-checks'],
  ['analytics', 'KPI Control Center', '/kpis'],
] as const;

const icon = (name: string) => <span aria-hidden="true" className="material-symbols-outlined">{name}</span>;
const HeaderSearchContext = createContext<{ query: string; setQuery: (query: string) => void } | null>(null);

export function useHeaderSearch() {
  const value = useContext(HeaderSearchContext);
  if (!value) throw new Error('useHeaderSearch must be used within AppShell');
  return value;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [query, setQuery] = useState('');
  useEffect(() => setQuery(''), [location.pathname]);
  const connection = new URLSearchParams(location.search).get('connection') || location.pathname.match(/^\/connections\/([^/]+)\/optimizer\//)?.[1] || '';
  const href = (path: string) => path === '/connections' || !connection ? path : `${path}?connection=${encodeURIComponent(connection)}`;
  const active = (path: string) => path === '/optimizer' ? location.pathname === path || /\/connections\/[^/]+\/optimizer\//.test(location.pathname) : location.pathname === path;
  const links = <nav className="space-y-1" aria-label="Primary navigation">{nav.map(([glyph, label, path]) => <Link key={path} to={href(path)} className={`flex items-center gap-3 border-l-2 px-5 py-3 text-sm transition ${active(path) ? 'border-voyager-blue bg-voyager-blue/10 text-voyager-text-primary' : 'border-transparent text-voyager-text-secondary hover:bg-voyager-surface2 hover:text-voyager-text-primary'}`}>{icon(glyph)}{label}</Link>)}</nav>;

  return <NotificationProvider><HeaderSearchContext.Provider value={{ query, setQuery }}><div className="min-h-screen bg-voyager-navy text-voyager-text-primary md:grid md:grid-cols-[240px_minmax(0,1fr)]">
    <aside className="hidden min-h-screen border-r border-voyager-border bg-voyager-navy py-4 md:flex md:flex-col"><div className="mb-10 px-5"><h1 className="font-display text-xl font-bold text-voyager-text-primary">DBVoyager</h1><p className="mt-1 font-mono text-xs tracking-[.17em] text-voyager-text-secondary">MISSION CONTROL</p></div>{links}<Link to="/connections" className="ui-button ui-button-primary mx-5 mt-auto">{icon('add')} New connection</Link></aside>
    <main className="min-w-0"><header className="sticky top-0 z-30 flex min-h-14 flex-wrap items-center gap-3 border-b border-voyager-border bg-voyager-surface/95 px-4 py-2 backdrop-blur md:px-7"><Link to="/dashboard" className="font-display font-bold md:hidden">DBVoyager</Link><div className="relative order-3 basis-full sm:order-none sm:w-80"><span className="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-voyager-text-muted transition-colors duration-200" aria-hidden="true">search</span><input value={query} onChange={event => setQuery(event.target.value)} className="w-full rounded-full border border-voyager-border bg-voyager-navy2 py-2 pl-10 pr-9 text-sm text-voyager-text-primary placeholder-voyager-text-muted caret-voyager-blue transition-all duration-200 focus:border-voyager-blue focus:shadow-glow focus:outline-none" placeholder="Search this page..." aria-label="Search this page" />{query && <button onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-voyager-text-muted transition-colors duration-150 hover:bg-voyager-surface2 hover:text-voyager-text-primary focus:outline-none focus:ring-1 focus:ring-voyager-blue" aria-label="Clear search"><span className="material-symbols-outlined text-base" aria-hidden="true">close</span></button>}</div><span className="ml-auto hidden border border-amber-400 bg-amber-400/10 px-3 py-1 font-mono text-[10px] tracking-[.13em] text-amber-200 sm:block">PRODUCTION ENVIRONMENT</span><NotificationBell /><details className="relative md:hidden"><summary className="cursor-pointer list-none text-voyager-text-secondary" aria-label="Open navigation">{icon('menu')}</summary><div className="absolute right-0 top-8 z-50 w-64 border border-voyager-border bg-voyager-surface py-2 shadow-lg">{links}</div></details></header>{children}</main>
  </div></HeaderSearchContext.Provider></NotificationProvider>;
}
