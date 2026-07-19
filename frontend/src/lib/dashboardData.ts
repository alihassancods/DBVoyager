import { authFetch } from './auth';
import { dashboardCacheKey, readDashboardCache, writeDashboardCache } from './dashboardCache';

export type DashboardSection = 'overview' | 'statistics' | 'health-checks' | 'schema' | 'schema-diagram' | 'optimizer' | 'slow-queries' | 'statistics/tables' | 'statistics/indexes' | 'statistics/locks' | 'kpis' | 'settings';
export type JsonRecord = Record<string, unknown>;

const pathFor = (section: DashboardSection) => section === 'optimizer' ? 'optimizer/slow-queries' : section === 'kpis' ? 'kpis/dashboard' : section;
const ttlFor = (section: DashboardSection) => section === 'schema' ? 3_600_000 : 30_000;
const asRecord = (value: unknown): JsonRecord => value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};
const asRows = (value: unknown): JsonRecord[] => Array.isArray(value) ? value as JsonRecord[] : [];

export function overviewFromReport(report: JsonRecord): JsonRecord {
  const brief = asRecord(asRecord(report.brief).data);
  if (Object.keys(brief).length) {
    const insights = asRows(brief.insights);
    return {
      database_stats: asRecord(brief.database_stats), top_slow_queries: asRows(brief.queries),
      table_count: asRows(brief.tables).length, insights, query_telemetry_available: brief.query_telemetry_available,
      health_summary: { critical: insights.filter(item => item.severity === 'critical').length, warning: insights.filter(item => item.severity === 'warning').length, info: insights.filter(item => item.severity === 'info').length },
    };
  }
  const statistics = asRecord(asRecord(report.statistics).data), health = asRows(asRecord(report.health_checks).data), schema = asRecord(asRecord(report.schema).data);
  return {
    generated_at: report.generated_at,
    health_summary: { critical: health.filter(item => item.severity === 'critical').length, warning: health.filter(item => item.severity === 'warning').length, info: health.filter(item => item.severity === 'info').length },
    database_stats: asRecord(statistics.database_stats), top_slow_queries: asRows(statistics.query_stats).slice(0, 5), table_count: asRows(schema.tables).length, insights: health,
  };
}

export function resourcesFromReport(report: JsonRecord): Partial<Record<DashboardSection, JsonRecord>> {
  const statistics = asRecord(asRecord(report.statistics).data), visualization = report.schema_visualization;
  const result: Partial<Record<DashboardSection, JsonRecord>> = { overview: overviewFromReport(report) };
  if (report.statistics) result.statistics = asRecord(report.statistics);
  if (report.health_checks) result['health-checks'] = asRecord(report.health_checks);
  if (report.schema) result.schema = asRecord(report.schema);
  if (typeof visualization === 'string') result['schema-diagram'] = { status: 'ok', data: visualization };
  else if (visualization) result['schema-diagram'] = asRecord(visualization);
  if (Array.isArray(statistics.query_stats)) result['slow-queries'] = { status: 'ok', data: statistics.query_stats };
  for (const [section, key] of [['statistics/tables', 'table_stats'], ['statistics/indexes', 'index_stats'], ['statistics/locks', 'lock_stats']] as const) {
    if (Array.isArray(statistics[key])) result[section] = { status: 'ok', data: statistics[key] };
  }
  return result;
}

export async function fetchDashboardResource(connectionId: string, section: DashboardSection, signal?: AbortSignal): Promise<{ payload: JsonRecord; cached: boolean; collecting: boolean }> {
  const resource = pathFor(section), key = dashboardCacheKey(connectionId, resource), cached = readDashboardCache(key);
  if (cached && Date.now() - cached.fetchedAt < ttlFor(section)) return { payload: cached.payload, cached: true, collecting: false };
  const response = await authFetch(`/connections/${connectionId}/${resource}`, { signal, headers: cached?.etag ? { 'If-None-Match': cached.etag } : {} });
  if (response.status === 304 && cached) return { payload: cached.payload, cached: true, collecting: false };
  const payload = await response.json().catch(() => ({})) as JsonRecord;
  if (!response.ok) throw new Error(String(payload.detail || 'Request failed'));
  const collecting = response.status === 202 || payload.collection_status === 'collecting' || payload.status === 'collecting';
  if (!collecting) writeDashboardCache(key, { payload, fetchedAt: Date.now(), etag: response.headers.get('etag') || undefined });
  return { payload, cached: false, collecting };
}

export function seedDashboardCache(connectionId: string, resources: Partial<Record<DashboardSection, JsonRecord>>): void {
  for (const [section, payload] of Object.entries(resources) as [DashboardSection, JsonRecord][]) {
    writeDashboardCache(dashboardCacheKey(connectionId, pathFor(section)), { payload, fetchedAt: Date.now() });
  }
}
