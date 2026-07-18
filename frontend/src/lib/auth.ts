const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const sessionKey = 'dbvoyager-session';

type AuthResponse = { session?: { access_token?: string }; data?: { session?: { access_token?: string } } };

export async function authenticate(path: '/auth/login' | '/auth/signup', data: Record<string, string>) {
  const response = await fetch(`${apiUrl}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || 'Authentication failed. Please try again.');

  const auth = body as AuthResponse;
  const token = response.headers.get('set-auth-jwt') || auth.session?.access_token || auth.data?.session?.access_token;
  localStorage.setItem(sessionKey, token || 'authenticated');
}

export const isAuthenticated = () => Boolean(localStorage.getItem(sessionKey));
