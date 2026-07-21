import { useEffect, useRef, useState } from 'react';
import officialLogo from '../../../../sample/stitch/stitch_dbvoyager_platform_ui/dbvoyager_logo_icon/screen.png';
import { isAuthenticated, logout } from '../lib/auth';

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const demoUrl = import.meta.env.VITE_DEMO_URL || 'https://www.youtube.com/results?search_query=DBVoyager+demo';
const pages = [
  ['Autonomous DBA', '/autonomous-dba', 'Always-on database intelligence that surfaces what needs attention first.'],
  ['Query Investigation', '/query-investigation', 'Turn slow-query symptoms into evidence and a reviewable next action.'],
  ['Schema Intelligence', '/schema-intelligence', 'See the tables, indexes, and relationships behind every decision.'],
] as const;

function Logo() {
  return <a href="/" className="flex items-center gap-2 font-display text-lg font-bold"><img src={officialLogo} alt="DBVoyager logo" className="size-9 rounded-lg" />DBVoyager</a>;
}

function InteractiveDots() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const section = canvas?.parentElement;
    const context = canvas?.getContext('2d');
    if (!canvas || !section || !context) return;
    let frame = 0;
    const draw = () => {
      const rect = section.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      canvas.width = rect.width * scale;
      canvas.height = rect.height * scale;
      context.setTransform(scale, 0, 0, scale, 0, 0);
      for (let y = 12; y < rect.height; y += 20) for (let x = 12; x < rect.width; x += 20) {
        context.fillStyle = 'rgba(148, 163, 184, .3)';
        context.beginPath();
        context.arc(x, y, 1, 0, Math.PI * 2);
        context.fill();
      }
    };
    const resize = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(draw); };
    const observer = new ResizeObserver(resize);
    observer.observe(section);
    draw();
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);

  return <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 size-full" />;
}

function SignalPreview() {
  return <div className="relative z-10 mx-auto mt-14 max-w-5xl overflow-hidden rounded-2xl border border-voyager-border/30 bg-voyager-surface text-left shadow-2xl shadow-voyager-blue/10">
    <div className="flex items-center justify-between border-b border-voyager-border/15 px-5 py-3 text-xs text-voyager-text-secondary"><span className="font-mono">production / postgres-primary</span><span className="rounded-full bg-voyager-success/15 px-2 py-1 font-mono text-voyager-success">● OBSERVING</span></div>
    <div className="grid gap-4 p-5 md:grid-cols-[1.15fr_.85fr]"><section className="rounded-xl border border-voyager-border/15 bg-voyager-navy2 p-5"><p className="font-mono text-[11px] uppercase tracking-[.16em] text-voyager-blue">DBA AI investigation</p><h2 className="mt-4 font-display text-2xl font-bold">A slow query has an explanation.</h2><p className="mt-3 max-w-lg leading-7 text-voyager-text-secondary">Sequential scans on <code className="rounded bg-voyager-surface px-1.5 py-0.5 text-voyager-text-primary">public.orders</code> are increasing query latency during peak traffic.</p><div className="mt-5 rounded-lg border border-voyager-blue/20 bg-voyager-blue/5 p-4"><p className="text-sm font-semibold">Recommendation ready</p><p className="mt-1 text-sm text-voyager-text-secondary">Review an index recommendation with the affected scope and supporting evidence.</p></div></section><aside className="grid gap-3"><div className="voyager-card p-4"><p className="text-xs text-voyager-text-secondary">Database health</p><p className="mt-2 font-mono text-3xl text-voyager-blue">B+</p><p className="mt-1 text-xs text-voyager-text-secondary">No critical risks found</p></div><div className="voyager-card p-4"><p className="text-xs text-voyager-text-secondary">Change control</p><p className="mt-2 text-sm font-semibold">Human approval required</p><p className="mt-1 text-xs text-voyager-text-secondary">Recommendations never change production alone.</p></div></aside></div>
  </div>;
}

export default function LandingPage() {
  const [light, setLight] = useState(false);
  const authenticated = isAuthenticated();

  return <div className={`min-h-screen overflow-hidden bg-voyager-navy text-voyager-text-primary ${light ? 'light' : ''}`}>
    <div className="border-b border-voyager-border/15 bg-voyager-surface py-2 text-center text-xs text-voyager-text-secondary">Autonomous database operations for PostgreSQL <span className="mx-2 text-voyager-blue">•</span> Read-only by default</div>
    <header className="sticky top-0 z-20 border-b border-voyager-border bg-voyager-navy/85 backdrop-blur"><div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5"><Logo /><nav className="hidden gap-5 text-sm text-voyager-text-secondary md:flex">{pages.map(([name, href]) => <a key={href} href={href} className="hover:text-voyager-text-primary">{name}</a>)}<a href={`${apiUrl}/docs`} className="hover:text-voyager-text-primary">Documentation</a></nav><div className="flex items-center gap-3"><button type="button" onClick={() => setLight(value => !value)} className="rounded-lg border border-voyager-border px-3 py-2 text-sm text-voyager-text-secondary hover:bg-voyager-surface2" aria-label={`Switch to ${light ? 'dark' : 'light'} mode`}>{light ? '☾ Dark' : '☀ Light'}</button>{authenticated ? <><a href="/dashboard" className="rounded-lg bg-voyager-blue px-4 py-2 text-sm font-semibold text-voyager-navy">Dashboard</a><button type="button" onClick={() => void logout().then(() => window.location.reload())} className="text-sm text-voyager-text-secondary hover:text-voyager-text-primary">Sign out</button></> : <><a href="/login" className="text-sm font-medium text-voyager-text-secondary hover:text-voyager-text-primary">Sign in</a><a href="/signup" className="rounded-lg bg-voyager-blue px-4 py-2 text-sm font-semibold text-voyager-navy">Deploy your DBA AI</a></>}</div></div></header>
    <main>
      <section className="stitch-grid relative isolate overflow-hidden px-5 pb-20 pt-20 text-center sm:pt-28"><InteractiveDots /><div className="relative z-10 mx-auto max-w-4xl"><p className="mx-auto inline-flex items-center gap-2 rounded-full border border-voyager-blue/30 bg-voyager-blue/10 px-3 py-1 font-mono text-[10px] tracking-widest text-voyager-blue"><span className="size-2 animate-pulse rounded-full bg-voyager-blue" />AUTONOMOUS AGENTIC DBA AI</p><h1 className="mt-7 font-display text-5xl font-bold leading-[1.05] sm:text-7xl">Your PostgreSQL database.<br /><i className="text-voyager-blue">Autonomously administered.</i></h1><p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-voyager-text-secondary sm:text-lg">DBVoyager watches your database, investigates what changed, and prepares safe recommendations for your approval.</p><div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row"><a href="/signup" className="rounded-lg bg-voyager-blue px-5 py-3 font-semibold text-voyager-navy hover:bg-voyager-blue-light">Deploy your DBA AI →</a><a href={demoUrl} target="_blank" rel="noreferrer" className="rounded-lg border border-voyager-border px-5 py-3 font-semibold hover:bg-voyager-surface2">Watch the demo ↗</a></div><p className="mt-4 text-xs text-voyager-text-secondary">PostgreSQL-native · Read-only by default · Human approval for changes</p></div><SignalPreview /></section>
      <section className="border-y border-voyager-border bg-voyager-navy2/50 px-5 py-20"><div className="mx-auto max-w-6xl"><p className="text-center font-mono text-xs uppercase tracking-[.2em] text-voyager-blue">Explore DBVoyager</p><div className="mt-8 grid gap-5 md:grid-cols-3">{pages.map(([name, href, description], index) => <a key={href} href={href} className="voyager-card group p-6 transition hover:border-voyager-blue"><span className="font-mono text-xs text-voyager-blue">0{index + 1}</span><h2 className="mt-5 font-display text-2xl font-bold">{name}</h2><p className="mt-3 leading-7 text-voyager-text-secondary">{description}</p><span className="mt-6 inline-block text-sm font-semibold text-voyager-blue">Explore →</span></a>)}</div></div></section>
      <section className="px-5 py-20 text-center"><div className="voyager-card mx-auto max-w-3xl p-8 sm:p-12"><p className="font-mono text-xs uppercase tracking-[.2em] text-voyager-blue">Observe · Investigate · Recommend</p><h2 className="mt-5 font-display text-3xl font-bold">Give your database an agentic DBA.</h2><p className="mx-auto mt-4 max-w-xl leading-7 text-voyager-text-secondary">Connect PostgreSQL and surface the signals that matter before they become incidents.</p><a href="/signup" className="mt-7 inline-flex rounded-lg bg-voyager-blue px-5 py-3 font-semibold text-voyager-navy hover:bg-voyager-blue-light">Create your account →</a></div></section>
    </main>
    <footer className="border-t border-voyager-border px-5 py-10"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-4 text-sm text-voyager-text-secondary sm:flex-row"><span>DBVoyager — Autonomous Agentic DBA AI</span><div className="flex gap-5">{pages.map(([name, href]) => <a key={href} href={href} className="hover:text-voyager-text-primary">{name}</a>)}<a href={`${apiUrl}/docs`} className="hover:text-voyager-text-primary">Documentation</a></div></div></footer>
  </div>;
}
