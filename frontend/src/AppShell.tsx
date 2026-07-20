import { Link, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

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

export default function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const connection = new URLSearchParams(location.search).get('connection') || location.pathname.match(/^\/connections\/([^/]+)\/optimizer\//)?.[1] || '';
  const href = (path: string) => path === '/connections' || !connection ? path : `${path}?connection=${encodeURIComponent(connection)}`;
  const active = (path: string) => path === '/optimizer' ? location.pathname === path || /\/connections\/[^/]+\/optimizer\//.test(location.pathname) : location.pathname === path;
  const links = <nav className="space-y-1">{nav.map(([glyph, label, path]) => <Link key={path} to={href(path)} className={`flex items-center gap-3 border-l-2 px-5 py-3 text-sm transition ${active(path) ? 'border-[#89ceff] bg-[#30353a]/50 text-[#89ceff]' : 'border-transparent text-[#bec8d2] hover:bg-[#252b2f] hover:text-[#dee3e9]'}`}>{icon(glyph)}{label}</Link>)}</nav>;

  return <div className="min-h-screen bg-[#0f1418] text-[#dee3e9] md:grid md:grid-cols-[240px_minmax(0,1fr)]">
    <aside className="hidden min-h-screen border-r border-[#3e4850] bg-[#0f1418] py-4 md:flex md:flex-col"><div className="mb-10 px-7"><h1 className="font-display text-xl font-bold text-[#89ceff]">DBVoyager</h1><p className="mt-1 font-mono text-[10px] tracking-[.17em] text-[#bec8d2]">MISSION CONTROL</p></div>{links}<Link to="/connections" className="mx-5 mt-auto bg-[#89ceff] px-3 py-2 text-center text-sm font-semibold text-[#00344d]">{icon('add')} New Connection</Link></aside>
    <main className="min-w-0"><header className="flex min-h-14 items-center border-b border-[#3e4850] bg-[#1b2024] px-4 md:hidden"><Link to="/dashboard" className="font-display font-bold text-[#89ceff]">DBVoyager</Link><details className="ml-auto relative"><summary className="cursor-pointer list-none text-[#bec8d2]" aria-label="Open navigation">{icon('menu')}</summary><div className="absolute right-0 top-8 z-50 w-64 border border-[#3e4850] bg-[#171c20] py-2 shadow-2xl">{links}</div></details></header>{children}</main>
  </div>;
}
