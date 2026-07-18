// API client. Uses the SAME bare paths the active static UI calls (/query, /sessions, /lessons);
// next.config.mjs rewrites them to the FastAPI backend, so there is no hardcoded host and no CORS.

import type { Message, QueryResponse, Session } from "./types";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface CreatedSession {
  id: string;
  first_q: string;
  created_at: string;
  result: QueryResponse;
}

// Extra fields only lesson mode sends (audience / grade band / length). Empty strings are dropped
// so the backend applies its own auto-detection, matching the static UI.
export interface LessonExtras {
  audience?: string;
  grade_band?: string;
  length?: string;
}

function body(question: string, intent: string, lang: string, extras?: LessonExtras) {
  const b: Record<string, unknown> = { question, intent, lang };
  if (extras) for (const [k, v] of Object.entries(extras)) if (v) b[k] = v;
  return JSON.stringify(b);
}

export const api = {
  listSessions: () => req<Session[]>("/sessions"),
  sessionMessages: (id: string) => req<Message[]>(`/sessions/${id}/messages`),
  deleteSession: (id: string) => req<{ ok: boolean }>(`/sessions/${id}`, { method: "DELETE" }),

  // POST /sessions creates a session and runs the first query atomically.
  createSession: (question: string, intent: string, lang: string, extras?: LessonExtras) =>
    req<CreatedSession>("/sessions", { method: "POST", body: body(question, intent, lang, extras) }),

  // POST /sessions/{id}/query continues an existing conversation (sticky mode enforced server-side).
  sessionQuery: (id: string, question: string, intent: string, lang: string, extras?: LessonExtras) =>
    req<QueryResponse>(`/sessions/${id}/query`, { method: "POST", body: body(question, intent, lang, extras) }),

  ready: () => req<{ status: string; points?: number; reason?: string }>("/ready"),
};
