import { useSyncExternalStore } from 'react';

type State = { active: number; label: string };
let state: State = { active: 0, label: 'Loading DBVoyager…' };
const listeners = new Set<() => void>();

const notify = () => listeners.forEach(listener => listener());

export function trackRouteRequest<T>(work: Promise<T>, label = 'Loading DBVoyager…'): Promise<T> {
  state = { active: state.active + 1, label };
  notify();
  return work.finally(() => requestAnimationFrame(() => {
    state = { ...state, active: Math.max(0, state.active - 1) };
    notify();
  }));
}

export function useRouteLoading(): State {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener); }, () => state);
}
