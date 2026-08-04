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

// BYOK (bring-your-own-key): the user's own provider API key, if they've entered one in Settings.
// Lives ONLY in this tab's memory + the browser's localStorage — it is never sent anywhere except as
// this one header on a generation call, and the backend never persists it (see app/api.py::_byok_llm).
// Read from localStorage once at module load so it survives closing/reopening the browser on the
// same device without the user re-typing it; a different device/browser starts with none, which is
// the accepted tradeoff for not storing it server-side at all.
const _BYOK_STORAGE_KEY = "chavruta.userLlmKey";
// Optional: point the key at a DIFFERENT provider/model than this deployment's own. "" (the default)
// means "use this deployment's own configured provider/model" — see app/api.py::_byok_llm.
const _BYOK_BASE_URL_KEY = "chavruta.userLlmBaseUrl";
const _BYOK_MODEL_KEY = "chavruta.userLlmModel";

function _lsGet(k: string): string | null {
  return typeof window !== "undefined" ? window.localStorage.getItem(k) : null;
}
function _lsSet(k: string, v: string | null) {
  if (typeof window === "undefined") return;
  if (v) window.localStorage.setItem(k, v);
  else window.localStorage.removeItem(k);
}

let _userLLMKey: string | null = _lsGet(_BYOK_STORAGE_KEY);
let _userLLMBaseUrl: string | null = _lsGet(_BYOK_BASE_URL_KEY);
let _userLLMModel: string | null = _lsGet(_BYOK_MODEL_KEY);

export function getUserLLMKey(): string | null {
  return _userLLMKey;
}
export function getUserLLMBaseUrl(): string | null {
  return _userLLMBaseUrl;
}
export function getUserLLMModel(): string | null {
  return _userLLMModel;
}

export function setUserLLMKey(key: string | null) {
  _userLLMKey = key && key.trim() ? key.trim() : null;
  _lsSet(_BYOK_STORAGE_KEY, _userLLMKey);
}
export function setUserLLMBaseUrl(url: string | null) {
  _userLLMBaseUrl = url && url.trim() ? url.trim() : null;
  _lsSet(_BYOK_BASE_URL_KEY, _userLLMBaseUrl);
}
export function setUserLLMModel(model: string | null) {
  _userLLMModel = model && model.trim() ? model.trim() : null;
  _lsSet(_BYOK_MODEL_KEY, _userLLMModel);
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_authToken) headers.Authorization = `Bearer ${_authToken}`;
  if (_userLLMKey) {
    headers["X-User-LLM-Key"] = _userLLMKey;
    if (_userLLMBaseUrl) headers["X-User-LLM-Base-URL"] = _userLLMBaseUrl;
    if (_userLLMModel) headers["X-User-LLM-Model"] = _userLLMModel;
  }
  const res = await fetch(path, {
    ...opts,
    headers: { ...headers, ...(opts?.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    // Surface the server's human-readable `detail` (often bilingual, e.g. the quota/429 message)
    // rather than a raw "API 502: {json}" blob. Tag with the status so callers can special-case.
    const raw = await res.text().catch(() => "");
    let detail = raw;
    try {
      const j = JSON.parse(raw);
      detail = typeof j.detail === "string" ? j.detail : raw;
    } catch {
      // Not JSON. If it's a whole HTML document, the request never reached the API — Next owns the
      // origin and served its own 404 page for a path that has no rewrite (see next.config.mjs).
      // Say that, because dumping the markup at the user is what made this bug look like a model
      // failure rather than a missing route.
      if (looksLikeHtml(raw)) detail = `הבקשה לא הגיעה לשרת (${path}) — HTTP ${res.status}`;
    }
    const err = new Error(detail || `HTTP ${res.status}`);
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }
  // A 200 carrying HTML means the same routing problem, just without an error status to catch it.
  const body = await res.text();
  if (looksLikeHtml(body)) {
    throw new Error(`הבקשה לא הגיעה לשרת (${path}) — התקבל HTML במקום JSON`);
  }
  return JSON.parse(body) as T;
}

/** Whether a response body is an HTML document rather than the JSON the API always returns. */
function looksLikeHtml(body: string): boolean {
  const head = body.trimStart().slice(0, 200).toLowerCase();
  return head.startsWith("<!doctype html") || head.startsWith("<html");
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
  let networkFailures = 0;
  for (;;) {
    let s: JobStatus<T>;
    try {
      s = await req<JobStatus<T>>(`/jobs/${jobId}`);
      networkFailures = 0;
    } catch (e) {
      // A transient network blip WHILE POLLING (a backgrounded mobile tab, a brief drop) must not
      // throw away a job that's still running — or already finished — server-side; the user saw this
      // as a false "no connection" error on a request that was actually still working. Only a real
      // network-level failure (fetch never reaching the server, surfaced as a TypeError — same check
      // page.tsx uses to pick the network-error message) is retried, and only for a bounded number of
      // consecutive misses; a clean 4xx/5xx from the server is a resolved response, not a thrown
      // TypeError, so it still fails immediately as before.
      if ((e as Error)?.name !== "TypeError" || ++networkFailures > 10) throw e;
      await new Promise((r) => setTimeout(r, intervalMs));
      continue;
    }
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
  // Rename and/or pin/unpin. `lang` only affects the 409 pin-limit message; the frontend already
  // disables the pin button pre-emptively (see SessionsPanel), so that path is a rare backstop.
  updateSession: (id: string, updates: { title?: string; pinned?: boolean }, lang: string = "he") =>
    req<Session>(`/sessions/${id}?lang=${lang}`, { method: "PATCH", body: JSON.stringify(updates) }),

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

  // Billing: is it available, start a checkout (returns a hosted payment URL), cancel the subscription.
  billingConfig: () => req<{ enabled: boolean; tiers: Tier[] }>("/billing/config"),

  // Coupons: the user-facing half. Issuing is operator-only (scripts/manage_coupons.py).
  redeemCoupon: (code: string) =>
    req<Redeemed>("/coupons/redeem", { method: "POST", body: JSON.stringify({ code }) }),
  checkout: (email: string, name: string, plan = "pro", cycle: "monthly" | "annual" = "monthly") =>
    req<{ url: string }>("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ email, name, plan, cycle }),
    }),
  cancelSubscription: () => req<{ ok: boolean }>("/billing/cancel", { method: "POST" }),

  // Flag a specific answer for operator review — the self-serve half of the defamation/quality
  // safety net (grounding reduces but doesn't eliminate the risk of a mischaracterizing answer).
  reportMessage: (messageId: number, reason: string) =>
    req<{ ok: boolean }>(`/messages/${messageId}/report`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // BYOK: validate a candidate key/base-url/model BEFORE saving it (see setUserLLMKey et al.) — the
  // candidate key is sent explicitly as a header (overriding whatever is already saved) so this
  // checks what the user just typed, not necessarily what's persisted yet.
  byokCheck: (candidateKey: string, model: string, baseUrl: string, lang: string) =>
    req<{ ok: boolean; models: string[]; message: string }>(`/byok/check?lang=${lang}`, {
      method: "POST",
      headers: { "X-User-LLM-Key": candidateKey },
      body: JSON.stringify({ model, base_url: baseUrl }),
    }),
};

// Account + today's free-tier quota (GET /me). daily_quota / remaining are null when unlimited
// (the local user, or quota disabled) — the UI then shows no counter.
export interface Me {
  owner: string;
  authenticated: boolean;
  plan: string;
  plan_name: string;
  // Allowances arrive as FRACTIONS remaining (1 = untouched, 0 = spent), never absolute figures.
  // A published number becomes a promise; a ratio stays true as the budget underneath it moves.
  day_left: number | null;                  // conversation pool, today. null ⇒ uncapped
  week_left: number | null;                 // conversation pool, this week
  lessons_left: number | null;              // lesson pool, this week — its own, independent pool
  lessons_exhausted: boolean;
  multiple: number;                         // usage relative to free: the only allowance figure shown
  credits: number;                          // prepaid generations, spent once a cap is hit
  // BYOK (bring-your-own-key): whether this deployment's backend even accepts a provider key (false
  // for the bridge backend), and — once the pools above are exhausted — a SECOND allowance the same
  // size as the plan's own, spent only when the user has entered their own key in Settings.
  byok_supported: boolean;
  byok_day_left: number | null;
  byok_week_left: number | null;
  byok_lessons_left: number | null;
  plan_until: string | null;                // ISO ts the paid/coupon period ends
  cycle: string;                            // 'monthly' | 'annual' | 'coupon'
  cancel_at_period_end: boolean;            // cancelled: access runs to plan_until, then lapses
  deletion_scheduled_for: string | null;   // ISO ts if the account is pending deletion
  blocked: boolean;
  blocked_until: string | null;             // ISO ts the block lifts (null + blocked ⇒ permanent)
  blocked_reason: string;
}

export interface Tier {
  id: string;
  name: string;
  price_ils: number;              // per month
  annual_price_ils: number;       // the year's total, for "₪1,990 a year"
  annual_monthly_ils: number;     // what is actually charged each month (instalment)
  annual_saving_pct: number;
  multiple: number;               // "3x the free tier" — no absolute allowance is published
}

export interface Redeemed {
  ok: boolean;
  kind: "plan" | "credits" | "";
  plan: string | null;
  plan_name: string;
  until: string | null;
  credits_added: number;
  credits_balance: number;
  message: string;          // already localized by the server
}

export interface Deletion {
  deletion_scheduled_for: string | null;
}
