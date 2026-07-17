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

export const api = {
  listSessions: () => req<Session[]>("/sessions"),
  sessionMessages: (id: string) => req<Message[]>(`/sessions/${id}/messages`),
  deleteSession: (id: string) => req<{ ok: boolean }>(`/sessions/${id}`, { method: "DELETE" }),

  // POST /sessions creates a session and runs the first query atomically.
  createSession: (question: string, intent: string, lang: string) =>
    req<CreatedSession>("/sessions", {
      method: "POST",
      body: JSON.stringify({ question, intent, lang }),
    }),

  // POST /sessions/{id}/query continues an existing conversation (sticky mode enforced server-side).
  sessionQuery: (id: string, question: string, intent: string, lang: string) =>
    req<QueryResponse>(`/sessions/${id}/query`, {
      method: "POST",
      body: JSON.stringify({ question, intent, lang }),
    }),

  ready: () => req<{ status: string; points?: number; reason?: string }>("/ready"),
};
