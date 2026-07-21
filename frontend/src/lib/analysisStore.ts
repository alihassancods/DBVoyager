/** Per-connection analysis section data and run events, persisted across route changes. */

import type { JsonRecord } from './dashboardData';

const prefix = 'dbvoyager:analysis:';
const memory = new Map<string, JsonRecord | null>();

function key(connectionId: string, section: string) {
  return `${prefix}${connectionId}:${section}`;
}

export function getSection(connectionId: string, section: string): JsonRecord | null {
  const k = key(connectionId, section);
  const cached = memory.get(k);
  if (cached !== undefined) return cached;
  try {
    const raw = sessionStorage.getItem(k);
    if (raw) {
      const entry = JSON.parse(raw) as JsonRecord;
      memory.set(k, entry);
      return entry;
    }
  } catch { /* sessionStorage flaky */ }
  return null;
}

export function setSection(connectionId: string, section: string, data: JsonRecord): void {
  const k = key(connectionId, section);
  memory.set(k, data);
  try { sessionStorage.setItem(k, JSON.stringify(data)); } catch { /* best-effort */ }
}

export function clearConnection(connectionId: string): void {
  const match = `${prefix}${connectionId}:`;
  for (const k of memory.keys()) if (k.startsWith(match)) memory.delete(k);
  for (const k of Object.keys(sessionStorage)) if (k.startsWith(match)) sessionStorage.removeItem(k);
}

/* ---- Analysis run events cache ---- */

const eventPrefix = 'dbvoyager:analysis-logs:';

function eventKey(connectionId: string, runId: string) {
  return `${eventPrefix}${connectionId}:events:${runId}`;
}

function runListKey(connectionId: string) {
  return `${eventPrefix}${connectionId}:runs`;
}

export type AnalysisRunSummary = {
  id: string;
  status: string;
  trigger: string;
  collection_kind: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  event_count: number;
};

export type AnalysisEvent = {
  id: number;
  stage: string;
  message: string;
  created_at: string | null;
};

export function setRunList(connectionId: string, runs: AnalysisRunSummary[]): void {
  try { sessionStorage.setItem(runListKey(connectionId), JSON.stringify(runs)); } catch { /* best-effort */ }
}

export function getRunList(connectionId: string): AnalysisRunSummary[] | null {
  try {
    const raw = sessionStorage.getItem(runListKey(connectionId));
    return raw ? JSON.parse(raw) as AnalysisRunSummary[] : null;
  } catch { return null; }
}

export function setRunEvents(connectionId: string, runId: string, events: AnalysisEvent[]): void {
  try { sessionStorage.setItem(eventKey(connectionId, runId), JSON.stringify(events)); } catch { /* best-effort */ }
}

export function getRunEvents(connectionId: string, runId: string): AnalysisEvent[] | null {
  try {
    const raw = sessionStorage.getItem(eventKey(connectionId, runId));
    return raw ? JSON.parse(raw) as AnalysisEvent[] : null;
  } catch { return null; }
}

export function appendRunEvents(connectionId: string, runId: string, newEvents: AnalysisEvent[]): void {
  const existing = getRunEvents(connectionId, runId) || [];
  existing.push(...newEvents);
  setRunEvents(connectionId, runId, existing);
}
