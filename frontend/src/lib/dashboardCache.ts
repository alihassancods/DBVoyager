const prefix = 'dbvoyager:dashboard:';
const maxEntries = 20;
const memory = new Map<string, DashboardCacheEntry>();

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
  const cached = memory.get(key);
  if (cached) return cached;
  try {
    const value = sessionStorage.getItem(key);
    const entry = value ? JSON.parse(value) as DashboardCacheEntry : null;
    if (entry) memory.set(key, entry);
    return entry;
  } catch {
    sessionStorage.removeItem(key);
    return null;
  }
}

export function writeDashboardCache(key: string, entry: DashboardCacheEntry): void {
  memory.set(key, entry);
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
  for (const key of new Set([...keys(), ...memory.keys()])) if (key.startsWith(match) && (!resources || resources.some(resource => key.endsWith(`:${resource}`)))) {
    memory.delete(key); sessionStorage.removeItem(key);
  }
}

export function clearDashboardCache(): void {
  memory.clear();
  for (const key of keys()) sessionStorage.removeItem(key);
}
