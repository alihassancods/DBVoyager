import { createContext, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';

export type DataTableColumn<T> = {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number;
  className?: string;
};

export function DataTable<T>({ columns, rows, rowKey, empty }: { columns: DataTableColumn<T>[]; rows: T[]; rowKey: (row: T, index: number) => string; empty?: ReactNode }) {
  const [sort, setSort] = useState<{ id: string; descending: boolean } | null>(null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find(item => item.id === sort.id);
    if (!column?.sortValue) return rows;
    return [...rows].sort((left, right) => {
      const a = column.sortValue!(left), b = column.sortValue!(right);
      const result = typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b));
      return sort.descending ? -result : result;
    });
  }, [columns, rows, sort]);
  const toggle = (column: DataTableColumn<T>) => column.sortValue && setSort(current => current?.id === column.id ? { id: column.id, descending: !current.descending } : { id: column.id, descending: false });
  if (!rows.length) return <>{empty || <p className="p-6 text-sm text-voyager-text-secondary">No records available.</p>}</>;
  return <div className="overflow-auto"><table className="w-full min-w-max text-left text-sm"><thead className="sticky top-0 z-10 bg-voyager-surface2 text-xs text-voyager-text-secondary"><tr>{columns.map(column => <th key={column.id} aria-sort={sort?.id === column.id ? sort.descending ? 'descending' : 'ascending' : undefined} className={`px-4 py-3 font-mono font-medium uppercase tracking-wider ${column.className || ''}`}>{column.sortValue ? <button type="button" onClick={() => toggle(column)} className="inline-flex items-center gap-1 hover:text-voyager-text-primary">{column.header}<span aria-hidden="true">{sort?.id === column.id ? sort.descending ? '↓' : '↑' : '↕'}</span></button> : column.header}</th>)}</tr></thead><tbody>{sorted.map((row, index) => <tr key={rowKey(row, index)} className="border-t border-voyager-border hover:bg-voyager-blue/5">{columns.map(column => <td key={column.id} className={`px-4 py-3 ${column.className || ''}`}>{column.cell(row)}</td>)}</tr>)}</tbody></table></div>;
}

export function Skeleton({ className = '' }: { className?: string }) { return <div aria-hidden="true" className={`ui-skeleton ${className}`} />; }

export function Modal({ title, children, onClose, className = '' }: { title: string; children: ReactNode; onClose: () => void; className?: string }) {
  const ref = useRef<HTMLElement>(null); const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusFirst = () => (ref.current?.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') || ref.current)?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); return; }
      if (event.key !== 'Tab' || !ref.current) return;
      const items = [...ref.current.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')];
      if (!items.length) { event.preventDefault(); return; }
      const first = items[0], last = items.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', keydown); document.body.style.overflow = 'hidden'; focusFirst();
    return () => { document.removeEventListener('keydown', keydown); document.body.style.overflow = ''; previous?.focus(); };
  }, [onClose]);
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/75 p-4 backdrop-blur" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}><section ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className={`w-full max-w-2xl rounded-xl border border-voyager-border bg-voyager-surface p-6 shadow-lg ${className}`}><header className="mb-5 flex items-center justify-between gap-4"><h2 id={titleId} className="font-display text-2xl font-semibold">{title}</h2><button type="button" onClick={onClose} aria-label={`Close ${title}`} className="ui-icon-button"><span aria-hidden="true" className="material-symbols-outlined">close</span></button></header>{children}</section></div>;
}

type Toast = { id: number; tone: 'success' | 'error'; message: string };
const ToastContext = createContext<{ showToast: (toast: Omit<Toast, 'id'>) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const showToast = ({ tone, message }: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random(); setToasts(current => [...current, { id, tone, message }]);
    if (tone === 'success') window.setTimeout(() => setToasts(current => current.filter(item => item.id !== id)), 5000);
  };
  return <ToastContext.Provider value={{ showToast }}>{children}<div className="fixed right-4 top-4 z-[60] space-y-3" aria-live="polite">{toasts.map(toast => <div key={toast.id} role={toast.tone === 'error' ? 'alert' : 'status'} className={`flex max-w-sm items-start gap-3 rounded-lg border p-4 shadow-lg ${toast.tone === 'error' ? 'border-red-400/50 bg-red-950 text-red-100' : 'border-emerald-400/50 bg-emerald-950 text-emerald-100'}`}><span className="material-symbols-outlined" aria-hidden="true">{toast.tone === 'error' ? 'error' : 'check_circle'}</span><p className="flex-1 text-sm">{toast.message}</p><button type="button" onClick={() => setToasts(current => current.filter(item => item.id !== toast.id))} aria-label="Dismiss notification">×</button></div>)}</div></ToastContext.Provider>;
}

export function useToast() { const context = useContext(ToastContext); if (!context) throw new Error('useToast must be used within ToastProvider'); return context; }
