import { useEffect, useRef, useState, type ReactNode } from 'react';
import officialLogo from '../../../../sample/stitch/stitch_dbvoyager_platform_ui/dbvoyager_logo_icon/screen.png';
import { isAuthenticated } from '../lib/auth';

const features = [
  ['◉', 'AI Health Audit'], ['▦', 'Schema Inspector'], ['›_', 'Query Optimizer'],
  ['✦', 'BI Chat'], ['⌁', 'KPI Agents'], ['◈', 'Proactive Alerts'],
] as const;
const plans = [
  ['Hobbyist', '$0', ['500MB data capacity', 'Community support', 'Weekly AI audits']],
  ['Team', '$29', ['50GB data capacity', 'Priority support', 'Real-time AI guardians', 'Custom edge functions']],
  ['Mission Control', 'Custom', ['Unlimited scale', 'Dedicated engineer', 'HIPAA / SOC2 compliance']],
];
const footer = { Product: ['Features', 'Integrations', 'Enterprise', 'Pricing'], Resources: ['Documentation', 'Guides', 'API reference', 'Changelog'], Company: ['About', 'Blog', 'Careers', 'Contact'], Legal: ['Privacy policy', 'Terms of service', 'Security'] };

function Logo() { return <a href="/" className="flex items-center gap-2 font-display text-lg font-bold"><img src={officialLogo} alt="DBVoyager logo" className="size-9 rounded-lg" />DBVoyager</a>; }
function Button({ href, children, primary = true }: { href: string; children: ReactNode; primary?: boolean }) { return <a href={href} className={`inline-flex items-center justify-center gap-2 rounded-lg px-5 py-3 font-semibold transition ${primary ? 'bg-voyager-blue text-voyager-navy hover:bg-voyager-blue-light' : 'border border-voyager-border text-voyager-text-primary hover:bg-voyager-surface2'}`}>{children}</a>; }

function InteractiveDots() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const section = canvas?.parentElement;
    const context = canvas?.getContext('2d');
    if (!canvas || !section || !context) return;

    let pointer: { x: number; y: number } | undefined;
    let frame = 0;
    let width = 0;
    let height = 0;
    const draw = () => {
      frame = 0;
      context.clearRect(0, 0, width, height);
      for (let y = 12; y < height; y += 20) for (let x = 12; x < width; x += 20) {
        const distance = pointer ? Math.hypot(x - pointer.x, y - pointer.y) : Infinity;
        const force = Math.max(0, 1 - distance / 220);
        const dx = pointer ? (x - pointer.x) / (distance || 1) : 0;
        const dy = pointer ? (y - pointer.y) / (distance || 1) : 0;
        context.fillStyle = force ? `rgba(14, 165, 233, ${.3 + force * .7})` : 'rgba(148, 163, 184, .3)';
        context.beginPath();
        context.arc(x + dx * force * 38, y + dy * force * 38, 1 + force * 2.4, 0, Math.PI * 2);
        context.fill();
      }
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(draw); };
    const resize = () => {
      const rect = section.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      width = rect.width;
      height = rect.height;
      canvas.width = width * scale;
      canvas.height = height * scale;
      context.setTransform(scale, 0, 0, scale, 0, 0);
      draw();
    };
    const move = (event: PointerEvent) => {
      const rect = section.getBoundingClientRect();
      pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      schedule();
    };
    const leave = () => { pointer = undefined; schedule(); };
    const observer = new ResizeObserver(resize);
    observer.observe(section);
    section.addEventListener('pointermove', move);
    section.addEventListener('pointerleave', leave);
    resize();
    return () => { observer.disconnect(); section.removeEventListener('pointermove', move); section.removeEventListener('pointerleave', leave); cancelAnimationFrame(frame); };
  }, []);

  return <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 size-full" />;
}

function DashboardPreview() {
  return <div className="relative mx-auto mt-14 max-w-5xl rounded-2xl border border-voyager-border bg-voyager-surface/80 p-2 shadow-glow backdrop-blur animate-[float_6s_ease-in-out_infinite]">
    <div className="overflow-hidden rounded-xl border border-voyager-border bg-voyager-navy2">
      <div className="flex h-10 items-center justify-between border-b border-voyager-border px-4"><div className="flex gap-2"><i className="size-2.5 rounded-full bg-red-400/70" /><i className="size-2.5 rounded-full bg-voyager-warning/70" /><i className="size-2.5 rounded-full bg-voyager-success/70" /></div><span className="font-mono text-[10px] uppercase tracking-widest text-voyager-text-secondary">production / db-cluster-01</span><span /></div>
      <div className="grid min-h-[260px] grid-cols-[110px_1fr] sm:min-h-[390px] sm:grid-cols-[150px_1fr]"><aside className="hidden border-r border-voyager-border bg-voyager-navy p-4 sm:block"><Logo /><div className="mt-8 space-y-3 text-xs text-voyager-text-secondary">Overview<br />Health Monitor<br />Schema<br />Query Optimizer<br />BI Chat</div></aside><div className="p-4 sm:p-6"><div className="grid grid-cols-3 gap-3">{['38ms', 'B+', '12/100'].map((value, i) => <div key={value} className="rounded-lg border border-voyager-border bg-voyager-surface p-3"><span className="text-[9px] uppercase tracking-wider text-voyager-text-secondary">{['Query speed', 'Health', 'Connections'][i]}</span><b className="mt-2 block font-mono text-lg text-voyager-blue">{value}</b></div>)}</div><div className="mt-4 grid gap-4 lg:grid-cols-2"><div className="rounded-lg border border-voyager-border bg-voyager-surface p-4"><p className="text-xs font-semibold">AI Agent <span className="ml-1 text-voyager-success">● Live</span></p><div className="mt-4 rounded-lg border border-voyager-border bg-voyager-navy p-3 text-[10px] text-voyager-text-secondary">I found a sequential scan on <em className="text-voyager-blue">public.orders</em>.<div className="mt-3 font-mono text-voyager-blue">CREATE INDEX idx_orders_user_id;</div></div></div><div className="rounded-lg border border-voyager-border bg-voyager-surface p-4"><p className="text-xs font-semibold">Database health</p><div className="mt-5 flex h-24 items-end gap-2">{[54, 78, 41, 92, 65, 84, 60].map((height, i) => <i key={i} style={{ height: `${height}%` }} className="flex-1 rounded-t bg-voyager-blue/30 ring-1 ring-inset ring-voyager-blue/50" />)}</div></div></div></div></div>
    </div><div className="absolute -left-24 top-1/3 -z-10 size-56 rounded-full bg-voyager-blue/20 blur-[100px]" /><div className="absolute -right-20 bottom-0 -z-10 size-56 rounded-full bg-cyan-400/10 blur-[100px]" />
  </div>;
}

export default function LandingPage() {
  const [light, setLight] = useState(false);
  const authenticated = isAuthenticated();

  return <div className={`overflow-hidden bg-voyager-navy text-voyager-text-primary ${light ? 'light' : ''}`}>
    <header className="sticky top-0 z-20 border-b border-voyager-border bg-voyager-navy/85 backdrop-blur"><div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5"><Logo /><nav className="hidden gap-6 text-sm text-voyager-text-secondary md:flex"><a href="#features">Features</a><a href="#pricing">Pricing</a><a href="#opensource">Open source</a></nav><div className="hidden items-center gap-3 sm:flex"><button type="button" onClick={() => setLight(value => !value)} className="rounded-lg border border-voyager-border px-3 py-2 text-sm text-voyager-text-secondary hover:bg-voyager-surface2" aria-label={`Switch to ${light ? 'dark' : 'light'} mode`}>{light ? '☾ Dark' : '☀ Light'}</button>{authenticated ? <Button href="/dashboard">Dashboard</Button> : <><a href="/login" className="px-3 py-2 text-sm font-medium text-voyager-text-secondary hover:text-voyager-text-primary">Sign In</a><Button href="/signup">Start for Free</Button></>}</div><button type="button" onClick={() => setLight(value => !value)} className="text-sm sm:hidden" aria-label={`Switch to ${light ? 'dark' : 'light'} mode`}>{light ? '☾' : '☀'}</button></div></header>
    <main>
      <section className="stitch-grid relative isolate overflow-hidden px-5 pb-12 pt-20 text-center sm:pt-28"><InteractiveDots /><div className="relative z-10 mx-auto max-w-4xl"><p className="mx-auto inline-flex items-center gap-2 rounded-full border border-voyager-blue/30 bg-voyager-blue/10 px-3 py-1 font-mono text-[10px] tracking-widest text-voyager-blue"><span className="size-2 animate-pulse rounded-full bg-voyager-blue" />AUTONOMOUS ENGINE NOW LIVE</p><h1 className="mt-7 font-display text-5xl font-bold leading-[1.05] sm:text-7xl">Navigate Your Data.<br /><i className="text-voyager-blue">Autonomously.</i></h1><p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-voyager-text-secondary sm:text-lg">Autonomous database engineering for PostgreSQL. Deploy, optimize, and secure your data ecosystem with always-on AI agents.</p><div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row"><Button href="/signup">Start Your Project →</Button><Button href="/signup" primary={false}>View Demo</Button></div></div><div className="relative z-10"><DashboardPreview /></div></section>
      <section className="border-y border-voyager-border bg-voyager-navy2/50 px-5 py-10"><div className="mx-auto flex max-w-6xl flex-wrap justify-center gap-3">{features.map(([icon, label]) => <div key={label} className="voyager-card voyager-glow flex items-center gap-2 px-4 py-3 text-sm"><span className="text-voyager-blue">{icon}</span>{label}</div>)}</div></section>
      <section id="features" className="mx-auto max-w-7xl space-y-24 px-5 py-24">{[['◈', 'Autonomous Database Guardian', 'Catch RLS gaps, security drift, and performance regressions before they become incidents.', 'RLS enabled across public tables'], ['›_', 'Queries that keep getting faster', 'Voyager finds expensive query patterns and gives your team a reviewed SQL fix, not an opaque black box.', '42% lower latency after index recommendation'], ['✦', 'Ask your database anything', 'Turn a plain-language question into an answer, a chart, and the SQL that produced it.', 'Top customers by revenue this month']].map(([icon, title, copy, label], i) => <article key={title} className={`grid items-center gap-10 md:grid-cols-2 ${i % 2 ? 'md:[&>div:first-child]:order-2' : ''}`}><div><span className="text-3xl text-voyager-blue">{icon}</span><h2 className="mt-5 font-display text-3xl font-bold">{title}</h2><p className="mt-4 max-w-lg leading-7 text-voyager-text-secondary">{copy}</p><a href="/signup" className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-voyager-blue">Explore DBVoyager →</a></div><div className="voyager-card p-6"><p className="font-mono text-[11px] uppercase tracking-widest text-voyager-blue">Live signal</p><p className="mt-6 text-xl font-semibold">{label}</p><div className="mt-8 h-2 rounded bg-voyager-navy2"><div className="h-full w-3/4 rounded bg-voyager-blue" /></div><div className="mt-5 grid grid-cols-3 gap-3">{['Analyze', 'Propose', 'Approve'].map((step, j) => <span key={step} className={`rounded-lg border p-3 text-center text-xs ${j === 1 ? 'border-voyager-blue bg-voyager-blue/10 text-voyager-blue' : 'border-voyager-border text-voyager-text-secondary'}`}>{step}</span>)}</div></div></article>)}</section>
      <section className="border-y border-voyager-border bg-voyager-surface px-5 py-16"><div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 text-center sm:grid-cols-3">{[['< 38ms', 'Average query latency'], ['5M+', 'Rows optimized daily'], ['100%', 'PostgreSQL native']].map(([value, label]) => <div key={label}><b className="font-mono text-3xl text-voyager-blue">{value}</b><p className="mt-2 font-mono text-[11px] uppercase tracking-widest text-voyager-text-secondary">{label}</p></div>)}</div></section>
      <section id="opensource" className="px-5 py-24 text-center"><div className="voyager-card mx-auto max-w-3xl p-8 sm:p-12"><span className="text-4xl text-voyager-blue">◉</span><h2 className="mt-5 font-display text-3xl font-bold">Open source from day one</h2><p className="mx-auto mt-4 max-w-xl leading-7 text-voyager-text-secondary">Audit the engine, contribute to the platform, and build the next generation of data infrastructure with us.</p><div className="mt-7"><Button href="https://github.com">Star on GitHub</Button></div></div></section>
      <section id="pricing" className="bg-voyager-navy2 px-5 py-24"><div className="mx-auto max-w-6xl"><div className="text-center"><h2 className="font-display text-3xl font-bold">Engineered for every team</h2><p className="mt-3 text-voyager-text-secondary">Flexible pricing that scales with your data footprint.</p></div><div className="mt-12 grid gap-6 md:grid-cols-3">{plans.map(([name, price, items], i) => <div key={name} className={`voyager-card relative p-7 ${i === 1 ? 'border-voyager-blue bg-voyager-blue/5' : ''}`}>{i === 1 && <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-voyager-blue px-3 py-1 font-mono text-[10px] font-bold text-voyager-navy">MOST POPULAR</span>}<h3 className="font-display text-xl font-bold">{name}</h3><p className="mt-3 font-mono text-3xl text-voyager-blue">{price}<small className="text-sm text-voyager-text-secondary">{price.startsWith('$') ? '/mo' : ''}</small></p><ul className="my-7 space-y-3 text-sm text-voyager-text-secondary">{items.map(item => <li key={item} className="flex gap-2"><span className="shrink-0 text-voyager-blue">✓</span>{item}</li>)}</ul><Button href="/signup" primary={i === 1}>{price === 'Custom' ? 'Contact Sales' : 'Get Started'}</Button></div>)}</div></div></section>
    </main>
    <footer className="border-t border-voyager-border px-5 py-16"><div className="mx-auto grid max-w-7xl gap-10 sm:grid-cols-2 lg:grid-cols-5"><div><Logo /><p className="mt-4 max-w-xs text-sm leading-6 text-voyager-text-secondary">Autonomous database engineering for modern teams.</p></div>{Object.entries(footer).map(([title, links]) => <div key={title}><h3 className="font-mono text-[11px] uppercase tracking-widest text-voyager-text-primary">{title}</h3><ul className="mt-4 space-y-2 text-sm text-voyager-text-secondary">{links.map(link => <li key={link}><a href="#">{link}</a></li>)}</ul></div>)}</div><p className="mx-auto mt-12 max-w-7xl border-t border-voyager-border pt-6 text-xs text-voyager-text-muted">© 2026 DBVoyager. Navigate with confidence.</p></footer>
  </div>;
}
