import { cachedResource, clearResourceCache } from './resourceCache';
import { trackRouteRequest } from './routeLoading';

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const sessionKey = 'dbvoyager-session';
let refreshInFlight: Promise<void> | null = null;

type AuthResponse = {
  token?: string;
  access_token?: string;
  session?: { access_token?: string; accessToken?: string };
  data?: { session?: { access_token?: string; accessToken?: string } };
};

function tokenFrom(response: Response, body: AuthResponse) {
  return response.headers.get('set-auth-jwt') || body.token || body.access_token || body.session?.access_token || body.session?.accessToken || body.data?.session?.access_token || body.data?.session?.accessToken;
}

function saveToken(token?: string) {
  if (!token) throw new Error('Authentication succeeded but no access token was returned.');
  sessionStorage.setItem(sessionKey, token);
}

export async function authenticate(path: '/auth/login' | '/auth/signup', data: Record<string, string>): Promise<void> {
  const response = await trackRouteRequest(fetch(`${apiUrl}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }), path === '/auth/login' ? 'Signing you in…' : 'Creating your account…');
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || 'Authentication failed. Please try again.');

  const auth = body as AuthResponse;
  const token = tokenFrom(response, auth);
  if (token) saveToken(token);
  else await refreshToken();
}

export async function refreshToken(): Promise<void> {
  if (!refreshInFlight) refreshInFlight = (async () => {
    const response = await fetch(`${apiUrl}/auth/token`, { method: 'POST', credentials: 'include' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error('Your session has expired. Please sign in again.');
    saveToken(tokenFrom(response, body as AuthResponse));
  })().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

export async function authFetch(path: string, init: RequestInit = {}, track = true): Promise<Response> {
  const request = () => fetch(`${apiUrl}${path}`, {
    ...init,
    credentials: 'include',
    headers: { ...init.headers, Authorization: `Bearer ${sessionStorage.getItem(sessionKey) || ''}` },
  });
  const work = async () => {
    let response = await request();
    if (response.status !== 401) return response;
    await refreshToken();
    return request();
  };
  return track ? trackRouteRequest(work()) : work();
}

export async function requireOk(response: Response): Promise<Response> {
  if (response.ok) return response;
  const body = await response.json().catch(() => ({})) as { detail?: string; message?: string };
  throw new Error(body.detail || body.message || 'Request failed');
}

export async function authJson<T>(path: string, init: RequestInit = {}, force = false, track = true): Promise<T> {
  const request = async () => {
    const response = await requireOk(await authFetch(path, init, false));
    const body = await response.json().catch(() => ({})) as T & { detail?: string; collection_status?: string; status?: string };
    return { body, cacheable: response.status !== 202 && body.collection_status !== 'collecting' && body.status !== 'collecting' };
  };
  const tracked = () => track ? trackRouteRequest(request()) : request();
  if ((init.method || 'GET').toUpperCase() !== 'GET') return (await tracked()).body;
  return cachedResource(path, tracked, value => value.cacheable, force).then(value => value.body);
}

export async function logout(): Promise<void> {
  await trackRouteRequest(fetch(`${apiUrl}/auth/logout`, { method: 'POST', credentials: 'include' }), 'Signing you out…');
  clearSession();
}

export const clearSession = () => { sessionStorage.removeItem(sessionKey); clearDashboardCache(); clearResourceCache(); };
export const isAuthenticated = () => Boolean(sessionStorage.getItem(sessionKey));
export const accessToken = () => sessionStorage.getItem(sessionKey);
export const apiBaseUrl = () => apiUrl;
import { clearDashboardCache } from './dashboardCache';
