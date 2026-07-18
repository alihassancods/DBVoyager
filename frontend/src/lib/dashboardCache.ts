const prefix = 'dbvoyager:dashboard:';
const maxEntries = 20;

export type DashboardCacheEntry = {
  payload: Record<string, unknown>;
  fetchedAt: number;
  etag?: string;
};

function keys(): string[] {
  return Object.keys(sessionStorage).filter(key => key.startsWith(prefix));
}

export function dashboardCacheKey(connectionId: string, resource: string): string {
  return `${prefix}${connectionId}:${resource}`;
}

export function readDashboardCache(key: string): DashboardCacheEntry | null {
  try {
    const value = sessionStorage.getItem(key);
    return value ? JSON.parse(value) as DashboardCacheEntry : null;
  } catch {
    sessionStorage.removeItem(key);
    return null;
  }
}

export function writeDashboardCache(key: string, entry: DashboardCacheEntry): void {
  try {
    const existing = keys().filter(candidate => candidate !== key).map(candidate => ({
      key: candidate,
      fetchedAt: readDashboardCache(candidate)?.fetchedAt || 0,
    })).sort((left, right) => left.fetchedAt - right.fetchedAt);
    for (const candidate of existing.slice(0, Math.max(0, existing.length - maxEntries + 1))) sessionStorage.removeItem(candidate.key);
    sessionStorage.setItem(key, JSON.stringify(entry));
  } catch {
    // Session storage is an optional performance layer.
  }
}

export function invalidateDashboardConnection(connectionId: string, resources?: string[]): void {
  const match = `${prefix}${connectionId}:`;
  for (const key of keys()) if (key.startsWith(match) && (!resources || resources.some(resource => key.endsWith(`:${resource}`)))) sessionStorage.removeItem(key);
}

export function clearDashboardCache(): void {
  for (const key of keys()) sessionStorage.removeItem(key);
}
