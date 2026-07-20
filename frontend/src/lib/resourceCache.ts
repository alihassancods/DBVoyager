const prefix = 'dbvoyager:resource:';
const maxEntries = 50;
const inFlight = new Map<string, Promise<unknown>>();

function keys() { return Object.keys(sessionStorage).filter(key => key.startsWith(prefix)); }

export function readResource<T>(path: string): T | null {
  try {
    const value = sessionStorage.getItem(`${prefix}${path}`);
    return value ? JSON.parse(value) as T : null;
  } catch {
    sessionStorage.removeItem(`${prefix}${path}`);
    return null;
  }
}

function writeResource(path: string, value: unknown) {
  try {
    const key = `${prefix}${path}`;
    const existing = keys().filter(item => item !== key);
    for (const item of existing.slice(0, Math.max(0, existing.length - maxEntries + 1))) sessionStorage.removeItem(item);
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Session storage is an optional performance layer.
  }
}

export async function cachedResource<T>(path: string, load: () => Promise<T>, cacheable: (value: T) => boolean, force = false): Promise<T> {
  if (!force) {
    const cached = readResource<T>(path);
    if (cached !== null) return cached;
    const pending = inFlight.get(path);
    if (pending) return pending as Promise<T>;
  }
  const pending = load().then(value => { if (cacheable(value)) writeResource(path, value); return value; }).finally(() => inFlight.delete(path));
  inFlight.set(path, pending);
  return pending;
}

export function invalidateResource(pathPrefix: string) {
  for (const key of keys()) if (key.slice(prefix.length).startsWith(pathPrefix)) sessionStorage.removeItem(key);
}

export function clearResourceCache() {
  for (const key of keys()) sessionStorage.removeItem(key);
  inFlight.clear();
}
