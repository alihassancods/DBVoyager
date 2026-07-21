import { useRouteLoading } from '../lib/routeLoading';

export default function RouteLoadingOverlay() {
  const { active, label } = useRouteLoading();
  if (!active) return null;
  return <div className="fixed inset-0 z-[70] grid place-items-center bg-voyager-navy/75 p-6 backdrop-blur-sm" role="status" aria-live="polite" aria-busy="true"><section className="route-loading-card w-full max-w-md overflow-hidden rounded-2xl border border-voyager-blue/40 bg-voyager-surface p-8 text-center shadow-2xl shadow-voyager-blue/20"><div className="route-loading-orbit mx-auto grid size-24 place-items-center rounded-full border border-voyager-blue/30"><span className="material-symbols-outlined text-4xl text-voyager-blue" aria-hidden="true">database</span></div><p className="mt-7 font-mono text-xs tracking-[.22em] text-voyager-blue">MISSION CONTROL</p><h2 className="mt-3 font-display text-2xl font-semibold">Preparing your workspace</h2><p className="mt-3 text-sm text-voyager-text-secondary">{label}</p><div className="mt-7 flex justify-center gap-2" aria-hidden="true"><i className="route-loading-dot" /><i className="route-loading-dot" /><i className="route-loading-dot" /></div></section></div>;
}
