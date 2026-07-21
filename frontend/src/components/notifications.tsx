import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { accessToken, apiBaseUrl, authJson, refreshToken } from '../lib/auth';
import { cachedResource } from '../lib/resourceCache';
import { Modal, useToast } from './ui';

export type Notification = { id: string; connection_id: string; severity: 'info' | 'warning' | 'critical'; title: string; body: string; action_path: string | null; metadata: Record<string, unknown>; delivered_at: string | null; read_at: string | null; created_at: string };
type AgentReport = { report_id: string; agent_kind: string; title: string; severity: string; report: { summary?: string; evidence?: string[]; recommendations?: string[] }; created_at: string };
type NotificationState = { items: Notification[]; unreadCount: number; markRead: (notification: Notification) => Promise<void> };
const Context = createContext<NotificationState | null>(null);

const wsUrl = () => {
  const url = new URL(apiBaseUrl());
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `${url.pathname.replace(/\/$/, '')}/ws/notifications`;
  return url.toString();
};

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();
  const [items, setItems] = useState<Notification[]>([]); const [unreadCount, setUnreadCount] = useState(0);
  const retries = useRef(0); const policyRetry = useRef(false); const timer = useRef<number>(); const heartbeat = useRef<number>(); const knownIds = useRef(new Set<string>());
  const add = useCallback((notification: Notification, toast = false) => {
    if (knownIds.current.has(notification.id)) return;
    knownIds.current.add(notification.id); setItems(current => [notification, ...current].slice(0, 50));
    if (!notification.read_at) setUnreadCount(current => current + 1);
    if (toast) showToast({ tone: notification.severity === 'critical' ? 'error' : 'success', message: notification.title });
  }, [showToast]);
  const load = useCallback(async () => {
    try { const result = await authJson<{ data: Notification[]; unread_count: number }>('/notifications', undefined, false, false); knownIds.current = new Set(result.data.map(item => item.id)); setItems(result.data); setUnreadCount(result.unread_count); } catch { /* The socket may still deliver live notifications. */ }
  }, []);
  useEffect(() => {
    void load(); let socket: WebSocket | null = null; let closed = false;
    const connect = () => {
      const token = accessToken(); if (!token || closed) return;
      socket = new WebSocket(wsUrl(), [`dbvoyager.jwt.${token}`]);
      socket.onopen = () => {
        retries.current = 0; policyRetry.current = false;
        heartbeat.current = window.setInterval(() => { if (socket?.readyState === WebSocket.OPEN) socket.send('{"type":"ping"}'); }, 15_000);
      };
      socket.onmessage = event => { try { const message = JSON.parse(String(event.data)) as { type?: string; notification?: Notification }; if (message.type === 'notification' && message.notification) add(message.notification, true); } catch { /* Ignore malformed frames. */ } };
      socket.onclose = event => {
        if (heartbeat.current) window.clearInterval(heartbeat.current);
        if (closed) return;
        if (event.code === 1008) {
          if (policyRetry.current) return;
          policyRetry.current = true;
          void refreshToken().then(() => { if (!closed) connect(); }).catch(() => undefined);
          return;
        }
        const delay = Math.min(30_000, 1_000 * 2 ** retries.current++); timer.current = window.setTimeout(connect, delay);
      };
    };
    timer.current = window.setTimeout(connect, 0);
    return () => { closed = true; socket?.close(); if (timer.current) window.clearTimeout(timer.current); if (heartbeat.current) window.clearInterval(heartbeat.current); };
  }, [add, load]);
  const markRead = async (notification: Notification) => {
    if (notification.read_at) return;
    await authJson(`/notifications/${notification.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ read: true }) }, false, false);
    setItems(current => current.map(item => item.id === notification.id ? { ...item, read_at: new Date().toISOString() } : item)); setUnreadCount(current => Math.max(0, current - 1));
  };
  const value = useMemo(() => ({ items, unreadCount, markRead }), [items, unreadCount]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useNotifications() { const value = useContext(Context); if (!value) throw new Error('useNotifications must be used within NotificationProvider'); return value; }

export function NotificationBell() {
  const { items, unreadCount, markRead } = useNotifications(); const [open, setOpen] = useState(false); const [report, setReport] = useState<AgentReport | null>(null); const navigate = useNavigate();
  const details = async (item: Notification) => { const reportId = typeof item.metadata.report_id === 'string' ? item.metadata.report_id : ''; if (!reportId) return; await markRead(item); setReport(await cachedResource(`/connections/${item.connection_id}/agent-reports/${reportId}`, () => authJson<AgentReport>(`/connections/${item.connection_id}/agent-reports/${reportId}`, undefined, false, false), () => true)); };
  return <div className="relative"><button type="button" onClick={() => setOpen(value => !value)} className="ui-icon-button relative" aria-label={`Notifications${unreadCount ? ` (${unreadCount} unread)` : ''}`}> <span className="material-symbols-outlined" aria-hidden="true">notifications</span>{unreadCount > 0 && <span className="absolute right-1 top-1 min-w-4 rounded-full bg-voyager-blue px-1 text-center text-[10px] font-bold text-voyager-navy">{unreadCount > 9 ? '9+' : unreadCount}</span>}</button>{open && <section className="absolute right-0 top-12 z-50 w-80 overflow-hidden rounded-lg border border-voyager-border bg-voyager-surface shadow-lg"><header className="border-b border-voyager-border px-4 py-3"><h2 className="font-display font-semibold">Notifications</h2></header>{items.length ? <div className="max-h-96 overflow-auto">{items.map(item => <article key={item.id} className={`border-b border-voyager-border px-4 py-3 ${item.read_at ? 'opacity-70' : ''}`}><p className="text-sm font-medium">{item.title}</p><p className="mt-1 text-sm text-voyager-text-secondary">{item.body}</p><div className="mt-2 flex items-center justify-between"><span className="font-mono text-xs text-voyager-text-muted">{item.severity.toUpperCase()}</span>{typeof item.metadata.report_id === 'string' ? <button type="button" onClick={() => void details(item)} className="text-sm text-voyager-blue">View details</button> : <button type="button" onClick={() => { void markRead(item); setOpen(false); if (item.action_path) navigate(item.action_path); }} className="text-sm text-voyager-blue">Open</button>}</div></article>)}</div> : <p className="p-4 text-sm text-voyager-text-secondary">No notifications yet.</p>}</section>}{report && <Modal title={report.title} onClose={() => setReport(null)}><p className="font-mono text-xs uppercase tracking-widest text-voyager-blue">VoyagerAI · {report.agent_kind}</p><p className="mt-4 text-sm leading-6 text-voyager-text-secondary">{report.report.summary}</p><ReportList title="Evidence" items={report.report.evidence} /><ReportList title="Recommendations" items={report.report.recommendations} /></Modal>}</div>;
}

function ReportList({ title, items = [] }: { title: string; items?: string[] }) { return items.length ? <section className="mt-5"><h3 className="font-display font-semibold">{title}</h3><ul className="mt-2 space-y-2 text-sm text-voyager-text-secondary">{items.map((item, index) => <li key={index} className="border-l-2 border-voyager-blue pl-3">{item}</li>)}</ul></section> : null; }
