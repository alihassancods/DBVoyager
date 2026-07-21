import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { accessToken, apiBaseUrl, authJson } from '../lib/auth';
import { useToast } from './ui';

export type Notification = { id: string; connection_id: string; severity: 'info' | 'warning' | 'critical'; title: string; body: string; action_path: string | null; metadata: Record<string, unknown>; delivered_at: string | null; read_at: string | null; created_at: string };
type NotificationState = { items: Notification[]; unreadCount: number; markRead: (notification: Notification) => Promise<void> };
const Context = createContext<NotificationState | null>(null);

const wsUrl = () => {
  const url = new URL(apiBaseUrl());
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = '/ws/notifications';
  return url.toString();
};

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();
  const [items, setItems] = useState<Notification[]>([]); const [unreadCount, setUnreadCount] = useState(0);
  const retries = useRef(0); const timer = useRef<number>(); const knownIds = useRef(new Set<string>());
  const add = useCallback((notification: Notification, toast = false) => {
    if (knownIds.current.has(notification.id)) return;
    knownIds.current.add(notification.id); setItems(current => [notification, ...current].slice(0, 50));
    if (!notification.read_at) setUnreadCount(current => current + 1);
    if (toast) showToast({ tone: notification.severity === 'critical' ? 'error' : 'success', message: notification.title });
  }, [showToast]);
  const load = useCallback(async () => {
    try { const result = await authJson<{ data: Notification[]; unread_count: number }>('/notifications'); knownIds.current = new Set(result.data.map(item => item.id)); setItems(result.data); setUnreadCount(result.unread_count); } catch { /* The socket may still deliver live notifications. */ }
  }, []);
  useEffect(() => {
    void load(); let socket: WebSocket | null = null; let closed = false;
    const connect = () => {
      const token = accessToken(); if (!token || closed) return;
      socket = new WebSocket(wsUrl(), [`dbvoyager.jwt.${token}`]);
      socket.onopen = () => { retries.current = 0; };
      socket.onmessage = event => { try { const message = JSON.parse(String(event.data)) as { type?: string; notification?: Notification }; if (message.type === 'notification' && message.notification) add(message.notification, true); } catch { /* Ignore malformed frames. */ } };
      socket.onclose = () => { if (closed) return; const delay = Math.min(30_000, 1_000 * 2 ** retries.current++); timer.current = window.setTimeout(connect, delay); };
    };
    connect();
    return () => { closed = true; socket?.close(); if (timer.current) window.clearTimeout(timer.current); };
  }, [add, load]);
  const markRead = async (notification: Notification) => {
    if (notification.read_at) return;
    await authJson(`/notifications/${notification.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ read: true }) });
    setItems(current => current.map(item => item.id === notification.id ? { ...item, read_at: new Date().toISOString() } : item)); setUnreadCount(current => Math.max(0, current - 1));
  };
  const value = useMemo(() => ({ items, unreadCount, markRead }), [items, unreadCount]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useNotifications() { const value = useContext(Context); if (!value) throw new Error('useNotifications must be used within NotificationProvider'); return value; }

export function NotificationBell() {
  const { items, unreadCount, markRead } = useNotifications(); const [open, setOpen] = useState(false); const navigate = useNavigate();
  return <div className="relative"><button type="button" onClick={() => setOpen(value => !value)} className="ui-icon-button relative" aria-label={`Notifications${unreadCount ? ` (${unreadCount} unread)` : ''}`}> <span className="material-symbols-outlined" aria-hidden="true">notifications</span>{unreadCount > 0 && <span className="absolute right-1 top-1 min-w-4 rounded-full bg-voyager-blue px-1 text-center text-[10px] font-bold text-voyager-navy">{unreadCount > 9 ? '9+' : unreadCount}</span>}</button>{open && <section className="absolute right-0 top-12 z-50 w-80 overflow-hidden rounded-lg border border-voyager-border bg-voyager-surface shadow-lg"><header className="border-b border-voyager-border px-4 py-3"><h2 className="font-display font-semibold">Notifications</h2></header>{items.length ? <div className="max-h-96 overflow-auto">{items.map(item => <button key={item.id} type="button" onClick={() => { void markRead(item); setOpen(false); if (item.action_path) navigate(item.action_path); }} className={`block w-full border-b border-voyager-border px-4 py-3 text-left hover:bg-voyager-surface2 ${item.read_at ? 'opacity-70' : ''}`}><p className="text-sm font-medium">{item.title}</p><p className="mt-1 text-sm text-voyager-text-secondary">{item.body}</p><p className="mt-2 font-mono text-xs text-voyager-text-muted">{item.severity.toUpperCase()}</p></button>)}</div> : <p className="p-4 text-sm text-voyager-text-secondary">No notifications yet.</p>}</section>}</div>;
}
