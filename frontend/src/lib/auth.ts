const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const sessionKey = 'dbvoyager-session';

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
  const response = await fetch(`${apiUrl}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || 'Authentication failed. Please try again.');

  const auth = body as AuthResponse;
  const token = tokenFrom(response, auth);
  if (token) saveToken(token);
  else await refreshToken();
}

export async function refreshToken(): Promise<void> {
  const response = await fetch(`${apiUrl}/auth/token`, { method: 'POST', credentials: 'include' });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error('Your session has expired. Please sign in again.');
  saveToken(tokenFrom(response, body as AuthResponse));
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const request = () => fetch(`${apiUrl}${path}`, {
    ...init,
    credentials: 'include',
    headers: { ...init.headers, Authorization: `Bearer ${sessionStorage.getItem(sessionKey) || ''}` },
  });
  let response = await request();
  if (response.status !== 401) return response;
  await refreshToken();
  response = await request();
  return response;
}

export async function logout(): Promise<void> {
  await fetch(`${apiUrl}/auth/logout`, { method: 'POST', credentials: 'include' });
  clearSession();
}

export const clearSession = () => { sessionStorage.removeItem(sessionKey); clearDashboardCache(); };
export const isAuthenticated = () => Boolean(sessionStorage.getItem(sessionKey));
import { clearDashboardCache } from './dashboardCache';
