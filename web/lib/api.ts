// API client. Uses the SAME bare paths the active static UI calls (/query, /sessions, /lessons);
// next.config.mjs rewrites them to the FastAPI backend, so there is no hardcoded host and no CORS.

import type { Attachment, Message, QueryResponse, SavedLesson, Session } from "./types";

// The current Supabase access token, kept in sync by the auth provider (setAuthToken). When set, it's
// attached as `Authorization: Bearer <token>` so the backend can verify the user and scope their data;
// when null (Supabase not configured / signed out) requests go out unauthenticated, unchanged.
let _authToken: string | null = null;
export function setAuthToken(token: string | null) {
  _authToken = token;
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_authToken) headers.Authorization = `Bearer ${_authToken}`;
  const res = await fetch(path, {
    ...opts,
    headers: { ...headers, ...(opts?.headers as Record<string, string> | undefined) },
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

function body(question: string, intent: string, lang: string, extras?: LessonExtras, attachments?: Attachment[]) {
  const b: Record<string, unknown> = { question, intent, lang };
  if (extras) for (const [k, v] of Object.entries(extras)) if (v) b[k] = v;
  if (attachments && attachments.length) b.attachments = attachments;
  return JSON.stringify(b);
}

// Async generation (job queue). A full lesson can take minutes — longer than a proxy's 504 window —
// so the backend returns a job id immediately and we poll GET /jobs/{id} until it flips to done/error.
// This is what keeps long lessons from failing on a hosted deployment behind nginx/Cloudflare.
interface JobAccepted {
  job_id: string;
  session_id?: string;
}
interface JobStatus<T> {
  status: "pending" | "running" | "done" | "error";
  result?: T;
  error?: string;
}

async function pollJob<T>(jobId: string, intervalMs = 1400, timeoutMs = 10 * 60 * 1000): Promise<T> {
  const start = Date.now();
  for (;;) {
    const s = await req<JobStatus<T>>(`/jobs/${jobId}`);
    if (s.status === "done") return s.result as T;
    if (s.status === "error") throw new Error(s.error || "generation failed");
    if (Date.now() - start > timeoutMs) throw new Error("timed out waiting for generation");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export const api = {
  listSessions: () => req<Session[]>("/sessions"),
  sessionMessages: (id: string) => req<Message[]>(`/sessions/${id}/messages`),
  deleteSession: (id: string) => req<{ ok: boolean }>(`/sessions/${id}`, { method: "DELETE" }),

  // POST /sessions creates a session and runs the first query atomically (synchronous).
  createSession: (q: string, intent: string, lang: string, extras?: LessonExtras, att?: Attachment[]) =>
    req<CreatedSession>("/sessions", { method: "POST", body: body(q, intent, lang, extras, att) }),

  // POST /sessions/{id}/query continues an existing conversation (sticky mode enforced server-side).
  sessionQuery: (id: string, q: string, intent: string, lang: string, extras?: LessonExtras, att?: Attachment[]) =>
    req<QueryResponse>(`/sessions/${id}/query`, { method: "POST", body: body(q, intent, lang, extras, att) }),

  // Async variants — the ones the UI actually uses. The session is created server-side immediately
  // (onSession fires with its id so the chat can appear in the list while it generates); the result
  // is polled off the job queue so a long lesson never trips a gateway timeout.
  createSessionAsync: async (
    q: string, intent: string, lang: string, extras?: LessonExtras, att?: Attachment[],
    onSession?: (id: string) => void,
  ) => {
    const acc = await req<JobAccepted>("/sessions/async", { method: "POST", body: body(q, intent, lang, extras, att) });
    if (acc.session_id && onSession) onSession(acc.session_id);
    return pollJob<CreatedSession>(acc.job_id);
  },

  sessionQueryAsync: async (
    id: string, q: string, intent: string, lang: string, extras?: LessonExtras, att?: Attachment[],
  ) => {
    const acc = await req<JobAccepted>(`/sessions/${id}/query/async`, { method: "POST", body: body(q, intent, lang, extras, att) });
    return pollJob<QueryResponse>(acc.job_id);
  },

  // My Shiurim — saved lessons.
  listLessons: () => req<SavedLesson[]>("/lessons"),
  getLesson: (id: string) => req<SavedLesson>(`/lessons/${id}`),
  deleteLesson: (id: string) => req<void>(`/lessons/${id}`, { method: "DELETE" }),

  ready: () => req<{ status: string; points?: number; reason?: string }>("/ready"),
  me: () => req<Me>("/me"),

  // Account deletion (scheduled, with a grace period). deleteAccount schedules it; cancel undoes it.
  deleteAccount: () => req<Deletion>("/account/delete", { method: "POST" }),
  cancelAccountDeletion: () => req<Deletion>("/account/delete/cancel", { method: "POST" }),
};

// Account + today's free-tier quota (GET /me). daily_quota / remaining are null when unlimited
// (the local user, or quota disabled) — the UI then shows no counter.
export interface Me {
  owner: string;
  authenticated: boolean;
  plan: string;
  daily_quota: number | null;
  used_today: number;
  remaining: number | null;
  deletion_scheduled_for: string | null;   // ISO ts if the account is pending deletion
  blocked: boolean;
  blocked_until: string | null;             // ISO ts the block lifts (null + blocked ⇒ permanent)
  blocked_reason: string;
}

export interface Deletion {
  deletion_scheduled_for: string | null;
}
