import { Link, useParams } from 'react-router-dom';

const pages = {
  'autonomous-dba': {
    eyebrow: 'AUTONOMOUS DBA',
    title: 'An always-on second set of eyes for PostgreSQL.',
    body: 'DBVoyager keeps database signals visible so your team can act before a performance or health issue becomes an incident.',
    points: ['Continuous database health signals', 'Clear, evidence-led findings', 'Human-controlled next actions'],
  },
  'query-investigation': {
    eyebrow: 'QUERY INVESTIGATION',
    title: 'Move from a slow query to the evidence behind it.',
    body: 'Inspect query behavior, understand where time is going, and review a focused optimization recommendation before any change is made.',
    points: ['Slow-query visibility', 'Plan and schema context', 'Reviewable optimization recommendations'],
  },
  'schema-intelligence': {
    eyebrow: 'SCHEMA INTELLIGENCE',
    title: 'Understand the shape of your database before you touch it.',
    body: 'Explore tables, columns, indexes, and relationships in one place so every investigation starts with the right context.',
    points: ['Tables and column details', 'Index and relationship context', 'A clearer path from schema to action'],
  },
} as const;

export default function ProductPage() {
  const slug = useParams().slug as keyof typeof pages;
  const page = pages[slug];
  if (!page) return null;

  return <main className="flex min-h-screen items-center bg-voyager-navy px-5 text-voyager-text-primary"><section className="mx-auto max-w-3xl"><Link to="/" className="text-sm font-semibold text-voyager-blue">← DBVoyager</Link><p className="mt-12 font-mono text-xs uppercase tracking-[.2em] text-voyager-blue">{page.eyebrow}</p><h1 className="mt-5 font-display text-4xl font-bold leading-tight sm:text-6xl">{page.title}</h1><p className="mt-6 max-w-2xl text-lg leading-8 text-voyager-text-secondary">{page.body}</p><ul className="mt-8 space-y-3">{page.points.map(point => <li key={point} className="voyager-card px-4 py-3">✓ {point}</li>)}</ul><Link to="/signup" className="mt-10 inline-flex rounded-lg bg-voyager-blue px-5 py-3 font-semibold text-voyager-navy hover:bg-voyager-blue-light">Deploy your DBA AI →</Link></section></main>;
}
