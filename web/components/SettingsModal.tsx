"use client";
import { useState } from "react";
import type { Lang } from "@/lib/types";
import { IntentId, tr, StringKey } from "@/lib/i18n";
import { Modal } from "./Modal";
import { useAuth } from "@/lib/auth";
import {
  api, getUserLLMKey, setUserLLMKey,
  getUserLLMBaseUrl, setUserLLMBaseUrl, getUserLLMModel, setUserLLMModel,
} from "@/lib/api";

// Change-password field — kept self-contained (own busy/result state) so a failed attempt doesn't
// disturb the rest of the settings panel, same pattern as CouponField below.
function ChangePasswordField({ lang }: { lang: Lang }) {
  const { updatePassword } = useAuth();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  async function submit() {
    if (!password || busy) return;
    setBusy(true);
    setResult(null);
    try {
      await updatePassword(password);
      setResult({ ok: true, msg: tr(lang, "passwordUpdated") });
      setPassword("");
    } catch (e) {
      setResult({ ok: false, msg: e instanceof Error ? e.message : tr(lang, "authGenericError") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      <span className="text-xs text-ink/60">{tr(lang, "changePassword")}</span>
      <div className="flex gap-2">
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder={tr(lang, "newPassword")}
          autoComplete="new-password"
          disabled={busy}
          className="flex-1 min-w-0 px-3 py-2 rounded-2xl glass text-sm outline-none
                     focus:ring-2 focus:ring-brand/40 disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={busy || !password}
          className="px-4 py-2 rounded-2xl grad text-white font-semibold text-sm shrink-0
                     hover:opacity-95 transition disabled:opacity-40"
        >
          {tr(lang, "changePasswordBtn")}
        </button>
      </div>
      {result && (
        <p role="status" aria-live="polite"
           className={"text-xs leading-relaxed " + (result.ok ? "text-emerald-600" : "text-red-500")}>
          {result.msg}
        </p>
      )}
    </div>
  );
}

// BYOK (bring-your-own-key) field — self-contained like ChangePasswordField/CouponField. Key/base
// URL/model live in localStorage via lib/api.ts, never sent to our own DB. Base URL and model are
// both optional: blank base URL means "this deployment's own provider", in which case the deployment's
// own model is used automatically and no server round-trip is needed to save. Naming a custom base
// URL (a different provider) or a specific model always validates first via /byok/check — guessing a
// model name on an unfamiliar provider isn't safe, so a mismatch hands back that provider's own model
// list to pick from instead.
function ByokKeyField({ lang }: { lang: Lang }) {
  const [key, setKey] = useState(() => getUserLLMKey() || "");
  const [baseUrl, setBaseUrl] = useState(() => getUserLLMBaseUrl() || "");
  const [model, setModel] = useState(() => getUserLLMModel() || "");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [modelOptions, setModelOptions] = useState<string[]>([]);

  const persist = () => {
    setUserLLMKey(key);
    setUserLLMBaseUrl(baseUrl);
    setUserLLMModel(model);
  };

  const checkAndSave = async () => {
    if (!key.trim() || busy) return;
    setBusy(true);
    setResult(null);
    setModelOptions([]);
    try {
      // Safe default: no custom provider and no custom model named — this deployment's own
      // provider/model, already known to work. No need to call the provider to validate that.
      if (!baseUrl.trim() && !model.trim()) {
        persist();
        setResult({ ok: true, msg: tr(lang, "byokSaved") });
        return;
      }
      const r = await api.byokCheck(key.trim(), model.trim(), baseUrl.trim(), lang);
      if (r.ok) {
        persist();
        setResult({ ok: true, msg: tr(lang, "byokSaved") });
      } else {
        setResult({ ok: false, msg: r.message });
        setModelOptions(r.models || []);
      }
    } catch (e) {
      setResult({ ok: false, msg: e instanceof Error ? e.message : tr(lang, "authGenericError") });
    } finally {
      setBusy(false);
    }
  };

  const clear = () => {
    setKey("");
    setBaseUrl("");
    setModel("");
    setUserLLMKey(null);
    setUserLLMBaseUrl(null);
    setUserLLMModel(null);
    setResult(null);
    setModelOptions([]);
  };

  return (
    <div className="mt-2 flex flex-col gap-2">
      <span className="text-xs text-ink/60">{tr(lang, "byokLabel")}</span>
      <p className="text-[11px] text-ink/45 leading-relaxed">{tr(lang, "byokHelp")}</p>
      <input
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder={tr(lang, "byokPlaceholder")}
        spellCheck={false}
        autoComplete="off"
        className="px-3 py-2 rounded-2xl glass text-sm outline-none focus:ring-2 focus:ring-brand/40"
      />
      <input
        value={baseUrl}
        onChange={(e) => setBaseUrl(e.target.value)}
        placeholder={tr(lang, "byokBaseUrlPlaceholder")}
        spellCheck={false}
        autoComplete="off"
        dir="ltr"
        className="px-3 py-2 rounded-2xl glass text-sm outline-none focus:ring-2 focus:ring-brand/40"
      />
      <input
        value={model}
        onChange={(e) => setModel(e.target.value)}
        placeholder={tr(lang, "byokModelPlaceholder")}
        spellCheck={false}
        autoComplete="off"
        dir="ltr"
        className="px-3 py-2 rounded-2xl glass text-sm outline-none focus:ring-2 focus:ring-brand/40"
      />
      <div className="flex gap-2">
        <button
          onClick={checkAndSave}
          disabled={busy || !key.trim()}
          className="flex-1 px-4 py-2 rounded-2xl grad text-white font-semibold text-sm
                     hover:opacity-95 transition disabled:opacity-40"
        >
          {busy ? tr(lang, "byokChecking") : tr(lang, "byokSave")}
        </button>
        {key && (
          <button
            onClick={clear}
            className="px-3 py-2 rounded-2xl glass text-red-500 font-semibold text-sm shrink-0
                       hover:bg-red-500/10 transition"
          >
            {tr(lang, "byokClear")}
          </button>
        )}
      </div>
      {result && (
        <p role="status" aria-live="polite"
           className={"text-xs leading-relaxed " + (result.ok ? "text-emerald-600" : "text-red-500")}>
          {result.msg}
        </p>
      )}
      {modelOptions.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-ink/45">{tr(lang, "byokPickModel")}</span>
          <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
            {modelOptions.map((m) => (
              <button
                key={m}
                onClick={() => { setModel(m); setModelOptions([]); setResult(null); }}
                dir="ltr"
                className="text-[11px] px-2.5 py-1 rounded-full bg-tekhelet/8 text-tekhelet hover:bg-tekhelet/15 transition"
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export type Theme = "light" | "dark" | "auto";

// Default-mode options match the static UI (lesson / explain / qa / shut / chavruta). parsha/
// dafyomi are deliberately excluded — they're occasional calendar lookups, not a sensible default
// for every new chat (and are beta-gated besides).
const MODES: { id: IntentId; key: StringKey }[] = [
  { id: "lesson", key: "lesson" },
  { id: "explain", key: "explain" },
  { id: "qa", key: "qa" },
  { id: "shut", key: "shutMode" },
  { id: "chavruta", key: "chavrutaMode" },
];

function Seg<T extends string>({
  value,
  options,
  onPick,
  wrap,
}: {
  value: T;
  options: { v: T; label: string }[];
  onPick: (v: T) => void;
  wrap?: boolean;
}) {
  return (
    <div className={`flex bg-white/50 rounded-2xl p-1 text-sm font-semibold gap-1 ${wrap ? "flex-wrap" : ""}`}>
      {options.map((o) => (
        <button
          key={o.v}
          onClick={() => onPick(o.v)}
          className={"flex-1 px-3 py-1.5 rounded-full transition " + (value === o.v ? "grad text-white" : "text-ink/60 hover:text-tekhelet")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** A remaining-allowance bar. Percentage only — the absolute figure behind it is deliberately not
 *  published (see app/plans.py), and a token count would mean nothing to a reader anyway. */
function Gauge({ label, value, caption }: { label: string; value: number; caption?: string }) {
  const pct = Math.round(value * 100);
  const bar = value === 0 ? "bg-red-500" : value <= 0.15 ? "bg-amber-500" : "bg-tekhelet/60";
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-2 text-xs text-ink/60">
        <span className="w-20 shrink-0">{label}</span>
        <span className="flex-1 h-1.5 rounded-full bg-ink/10 overflow-hidden"
              role="img" aria-label={`${label}: ${pct}%`}>
          <span className={"block h-full rounded-full " + bar} style={{ width: `${pct}%` }} />
        </span>
        <span className="w-9 text-end tabular-nums">{pct}%</span>
      </div>
      {caption && <p className="text-[11px] text-ink/40 ps-[88px]">{caption}</p>}
    </div>
  );
}

/** How long until a quota pool next resets — daily pools at local midnight, weekly pools (including
 *  the separate lessons pool, see app/plans.py) at the coming Sunday 00:00, matching the actual
 *  reset moment the backend's own quota messages already describe ("It resets on Sunday" / "It
 *  resets tomorrow" — app/api.py). Computed client-side since both are deterministic; no backend
 *  field needed. */
function resetsIn(kind: "day" | "week", lang: Lang): string {
  const now = new Date();
  const target = new Date(now);
  if (kind === "day") {
    target.setHours(24, 0, 0, 0);
  } else {
    const day = now.getDay(); // 0 = Sunday
    target.setDate(now.getDate() + (day === 0 ? 7 : 7 - day));
    target.setHours(0, 0, 0, 0);
  }
  const hours = Math.round((target.getTime() - now.getTime()) / 3_600_000);
  if (hours < 1) return lang === "he" ? "מתאפס בקרוב" : "resets soon";
  if (hours < 24) return lang === "he" ? `מתאפס בעוד כ-${hours} שעות` : `resets in about ${hours}h`;
  const days = Math.round(hours / 24);
  return lang === "he" ? `מתאפס בעוד כ-${days} ימים` : `resets in about ${days}d`;
}

/** Coupon entry. Keeps its own state so a failed attempt doesn't disturb the rest of settings; the
 *  result line is whatever the server said (already localized there, so the two never disagree). */
function CouponField({ lang, onRedeem }: { lang: Lang; onRedeem: (c: string) => Promise<string> }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  async function submit() {
    const c = code.trim();
    if (!c || busy) return;
    setBusy(true);
    setResult(null);
    try {
      setResult({ ok: true, msg: await onRedeem(c) });
      setCode("");
    } catch (e) {
      setResult({ ok: false, msg: e instanceof Error ? e.message : tr(lang, "couponFailed") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      <span className="text-xs text-ink/60">{tr(lang, "couponLabel")}</span>
      <div className="flex gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder={tr(lang, "couponPlaceholder")}
          aria-label={tr(lang, "couponLabel")}
          disabled={busy}
          spellCheck={false}
          autoComplete="off"
          className="flex-1 min-w-0 px-3 py-2 rounded-2xl glass text-sm tracking-wider uppercase
                     outline-none focus:ring-2 focus:ring-brand/40 disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={busy || !code.trim()}
          className="px-4 py-2 rounded-2xl grad text-white font-semibold text-sm shrink-0
                     hover:opacity-95 transition disabled:opacity-40"
        >
          {busy ? tr(lang, "couponRedeeming") : tr(lang, "couponRedeem")}
        </button>
      </div>
      {result && (
        <p role="status" aria-live="polite"
           className={"text-xs leading-relaxed " + (result.ok ? "text-emerald-600" : "text-red-500")}>
          {result.msg}
        </p>
      )}
    </div>
  );
}

/* Join an institution by CODE. Deliberately the member's own action: a school never attaches an
 * account by typing its id, so this field is the only way in. Mirrors CouponField because it is the
 * same interaction — paste a short code, get one line back — and reusing the shape means a user who
 * has redeemed a coupon already knows how this works. */
function OrgJoinField({ lang, orgName, onJoin }: {
  lang: Lang; orgName?: string; onJoin: (c: string) => Promise<string>;
}) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const he = lang === "he";

  async function submit() {
    const c = code.trim();
    if (!c || busy) return;
    setBusy(true);
    setResult(null);
    try {
      setResult({ ok: true, msg: await onJoin(c) });
      setCode("");
    } catch (e) {
      setResult({ ok: false, msg: e instanceof Error ? e.message : (he ? "ההצטרפות נכשלה" : "Could not join") });
    } finally {
      setBusy(false);
    }
  }

  if (orgName) {
    return (
      <div className="mt-2 flex flex-col gap-1">
        <span className="text-xs text-ink/60">{he ? "מוסד" : "Institution"}</span>
        <p className="text-sm text-tekhelet font-semibold">{orgName}</p>
        <p className="text-[11px] text-ink/45 leading-relaxed">
          {he
            ? "המכסה שלך מגיעה מהמוסד. המוסד רואה את היקף השימוש ואת סוגי הפעילות שלך — ולעולם לא את תוכן השיחות."
            : "Your allowance comes from the institution. It can see how much you use and which modes — never the content of your conversations."}
        </p>
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      <span className="text-xs text-ink/60">{he ? "קוד הצטרפות למוסד" : "Institution join code"}</span>
      <div className="flex gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder={he ? "קוד מהמוסד" : "Code from your institution"}
          aria-label={he ? "קוד הצטרפות למוסד" : "Institution join code"}
          disabled={busy}
          spellCheck={false}
          autoComplete="off"
          className="flex-1 min-w-0 px-3 py-2 rounded-2xl glass text-sm tracking-wider uppercase
                     outline-none focus:ring-2 focus:ring-brand/40 disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={busy || !code.trim()}
          className="px-4 py-2 rounded-2xl grad text-white font-semibold text-sm shrink-0
                     hover:opacity-95 transition disabled:opacity-40"
        >
          {busy ? (he ? "מצטרף…" : "Joining…") : (he ? "הצטרפות" : "Join")}
        </button>
      </div>
      {result && (
        <p role="status" aria-live="polite"
           className={"text-xs leading-relaxed " + (result.ok ? "text-emerald-600" : "text-red-500")}>
          {result.msg}
        </p>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-bold text-ink/55">{label}</label>
      {children}
    </div>
  );
}

// Settings — full parity with the static UI: interface language, default mode, theme (light/dark/
// auto), sources default (collapsed/expanded), clear history, and an about/version footer.
export function SettingsModal({
  open,
  lang,
  theme,
  defaultIntent,
  srcDefaultOpen,
  onClose,
  onLang,
  onTheme,
  onDefaultIntent,
  onSrcDefaultOpen,
  onClearHistory,
  deletionScheduledFor,
  onDeleteAccount,
  onCancelDeletion,
  plan,
  planName,
  planUntil,
  credits,
  cycle,
  cancelAtPeriodEnd,
  dayLeft,
  weekLeft,
  lessonsLeft,
  billingEnabled,
  onUpgrade,
  onCancelSubscription,
  onRedeemCoupon,
  onJoinOrg,
  orgName,
  byokSupported,
}: {
  open: boolean;
  lang: Lang;
  theme: Theme;
  defaultIntent: IntentId;
  srcDefaultOpen: boolean;
  onClose: () => void;
  onLang: (l: Lang) => void;
  onTheme: (t: Theme) => void;
  onDefaultIntent: (i: IntentId) => void;
  onSrcDefaultOpen: (v: boolean) => void;
  onClearHistory: () => void;
  deletionScheduledFor?: string | null;   // ISO ts if the account is pending deletion
  onDeleteAccount?: () => void;
  onCancelDeletion?: () => void;
  plan?: string;                           // tier id — see app/plans.py
  planName?: string;                       // localized tier name from /me
  planUntil?: string | null;               // ISO ts a coupon-granted plan lapses
  credits?: number;                        // prepaid generations left
  cycle?: string;                          // 'monthly' | 'annual' | 'coupon'
  cancelAtPeriodEnd?: boolean;             // cancelled: access runs to planUntil, then lapses
  dayLeft?: number | null;                 // fraction of today's conversation allowance left
  weekLeft?: number | null;                // fraction of this week's conversation allowance left
  lessonsLeft?: number | null;             // fraction of this week's lessons left (separate pool)
  billingEnabled?: boolean;
  onUpgrade?: () => void;
  onCancelSubscription?: () => void;
  onRedeemCoupon?: (code: string) => Promise<string>;   // resolves with a message to show
  onJoinOrg?: (code: string) => Promise<string>;        // institution join code (spec 004)
  orgName?: string;                                    // set ⇒ already a member, show what
                                                       // the school can and cannot see
  byokSupported?: boolean;   // /me: whether this deployment's backend accepts a provider key at all
}) {
  const auth = useAuth();
  const [idCopied, setIdCopied] = useState(false);
  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString(lang === "he" ? "he-IL" : "en-US",
      { year: "numeric", month: "long", day: "numeric" });
  return (
    <Modal open={open} title={tr(lang, "settingsHeading")} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto">
        <Field label={tr(lang, "setLanguage")}>
          <Seg<Lang>
            value={lang}
            onPick={onLang}
            options={[
              { v: "he", label: "עברית" },
              { v: "en", label: "English" },
            ]}
          />
        </Field>

        <Field label={tr(lang, "setDefaultMode")}>
          <Seg<IntentId>
            value={defaultIntent}
            onPick={onDefaultIntent}
            wrap
            options={MODES.map((m) => ({ v: m.id, label: tr(lang, m.key) }))}
          />
        </Field>

        <Field label={tr(lang, "setTheme")}>
          <Seg<Theme>
            value={theme}
            onPick={onTheme}
            options={[
              { v: "light", label: tr(lang, "themeLight") },
              { v: "dark", label: tr(lang, "themeDark") },
              { v: "auto", label: tr(lang, "themeAuto") },
            ]}
          />
        </Field>

        <Field label={tr(lang, "setSourcesDefault")}>
          <Seg<"collapsed" | "expanded">
            value={srcDefaultOpen ? "expanded" : "collapsed"}
            onPick={(v) => onSrcDefaultOpen(v === "expanded")}
            options={[
              { v: "collapsed", label: tr(lang, "srcCollapsed") },
              { v: "expanded", label: tr(lang, "srcExpanded") },
            ]}
          />
        </Field>

        <Field label={tr(lang, "setHistory")}>
          <button
            onClick={onClearHistory}
            className="w-full py-2.5 rounded-2xl glass text-red-500 font-semibold text-sm hover:bg-red-500/10 transition"
          >
            {tr(lang, "clearAll")}
          </button>
        </Field>

        {/* Account — only in Supabase mode (auth.enabled). Shows who's signed in + a sign-out. */}
        {auth.enabled && auth.user && (
          <Field label={tr(lang, "account")}>
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 flex flex-col gap-0.5">
                <span className="text-xs text-ink/60 truncate">{auth.user.email}</span>
                {/* The account id, under the email. It's what support needs to identify an account
                    (grants and coupons are applied by this id, never by email), so it has to be
                    readable and copyable by the person being helped. Click copies it. */}
                <button
                  type="button"
                  title={tr(lang, "copyUserId")}
                  onClick={() => {
                    navigator.clipboard?.writeText(auth.user!.id);
                    setIdCopied(true);
                    setTimeout(() => setIdCopied(false), 1500);
                  }}
                  className="text-[11px] font-mono text-ink/40 hover:text-tekhelet truncate text-start transition"
                  dir="ltr"
                >
                  {idCopied ? tr(lang, "copied") : auth.user.id}
                </button>
              </div>
              <button
                onClick={() => auth.signOut()}
                className="px-4 py-2 rounded-2xl glass text-red-500 font-semibold text-sm hover:bg-red-500/10 transition shrink-0"
              >
                {tr(lang, "signOut")}
              </button>
            </div>

            <ChangePasswordField lang={lang} />

            {/* Marketing consent — opt-in, changeable any time; mirrors the sign-up checkbox but
                reflects (and updates) the value actually stored in user_metadata. */}
            <label className="mt-2 flex items-center gap-2 text-xs text-ink/70 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(auth.user.user_metadata?.marketing_consent)}
                onChange={(e) => auth.updateMetadata({
                  marketing_consent: e.target.checked,
                  marketing_consent_at: new Date().toISOString(),
                })}
                className="accent-tekhelet"
              />
              <span>{tr(lang, "marketingConsentSetting")}</span>
            </label>

            {/* Global data-review opt-out — overrides the per-chat toggle in SessionsPanel. Only
                meaningful for chats created on/after 2026-08-10 (privacy policy section 12); stored
                in user_metadata like marketing_consent above, not a server-side schema change. */}
            <label className="mt-2 flex items-center gap-2 text-xs text-ink/70 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(auth.user.user_metadata?.data_review_opt_out)}
                onChange={(e) => auth.updateMetadata({
                  data_review_opt_out: e.target.checked,
                  data_review_opt_out_at: new Date().toISOString(),
                })}
                className="accent-tekhelet"
              />
              <span>{tr(lang, "dataReviewOptOutSetting")}</span>
            </label>

            {/* Plan + billing — upgrade (free) or cancel subscription (paid). */}
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-xs text-ink/60">
                {tr(lang, "planLabel")}: {planName || tr(lang, "planFree")}
                {cycle === "annual" && <> ({tr(lang, "cycleAnnual")})</>}
                {planUntil && <> · {tr(lang, "planUntil")} {fmtDate(planUntil)}</>}
                {!!credits && <> · {credits} {tr(lang, "creditsLabel")}</>}
              </span>
              {/* Already cancelled: there is nothing left to cancel, and offering the button again
                  would suggest access is still being billed for. State the end date instead. */}
              {plan && plan !== "free" && cancelAtPeriodEnd ? (
                <span className="text-xs text-ink/50 shrink-0">
                  {tr(lang, "subCanceledNotice")} {planUntil ? fmtDate(planUntil) : ""}
                </span>
              ) : plan && plan !== "free" ? (
                <button
                  onClick={() => {
                    if (window.confirm(tr(lang, "cancelSubscriptionConfirm"))) onCancelSubscription?.();
                  }}
                  className="px-4 py-2 rounded-2xl glass text-red-500 font-semibold text-sm hover:bg-red-500/10 transition shrink-0"
                >
                  {tr(lang, "cancelSubscription")}
                </button>
              ) : (
                billingEnabled && (
                  <button
                    onClick={() => onUpgrade?.()}
                    className="px-4 py-2 rounded-2xl grad text-white font-semibold text-sm hover:opacity-95 transition shrink-0"
                  >
                    {tr(lang, "upgrade")}
                  </button>
                )
              )}
            </div>

            {/* Three gauges because there are up to three independent pools: daily and weekly
                conversation usage, and lessons (its own pool — running out of conversation usage
                does not touch it, and a single combined bar would imply it does). Moved here from
                the main header entirely — see Header.tsx. */}
            {(typeof dayLeft === "number" || typeof weekLeft === "number" || typeof lessonsLeft === "number") && (
              <div className="mt-2 flex flex-col gap-2.5">
                {typeof dayLeft === "number" && (
                  <Gauge label={tr(lang, "usageLeftDay")} value={dayLeft} caption={resetsIn("day", lang)} />
                )}
                {typeof weekLeft === "number" && (
                  <Gauge label={tr(lang, "usageLeftWeek")} value={weekLeft} caption={resetsIn("week", lang)} />
                )}
                {typeof lessonsLeft === "number" && (
                  <Gauge label={tr(lang, "lessonsLeft")} value={lessonsLeft} caption={resetsIn("week", lang)} />
                )}
              </div>
            )}

            {/* Coupon redemption — grants a time-boxed plan or prepaid credits. Always shown to a
                signed-in user, including when billing is off: coupons are the one way to get paid
                access on a deployment with no payment provider configured. */}
            {onRedeemCoupon && <CouponField lang={lang} onRedeem={onRedeemCoupon} />}

            {/* Institution membership — join by code, or, once in, what the school can see. */}
            {onJoinOrg && <OrgJoinField lang={lang} orgName={orgName} onJoin={onJoinOrg} />}

            {/* BYOK — only offered when the backend has a provider-key concept at all (not 'bridge'). */}
            {byokSupported && <ByokKeyField lang={lang} />}

            {/* Account deletion — scheduled with a grace period, cancellable until the deadline. */}
            {deletionScheduledFor ? (
              <div className="mt-2 p-3 rounded-2xl bg-red-500/5 ring-1 ring-red-500/15 flex flex-col gap-2">
                <p className="text-xs text-red-600/90 leading-relaxed">
                  {tr(lang, "deletionScheduledPrefix")} {fmtDate(deletionScheduledFor)}. {tr(lang, "deletionCanCancel")}
                </p>
                <button
                  onClick={() => onCancelDeletion?.()}
                  className="py-2 rounded-2xl grad text-white font-semibold text-sm hover:opacity-95 transition"
                >
                  {tr(lang, "cancelDeletion")}
                </button>
              </div>
            ) : (
              <button
                onClick={() => {
                  if (window.confirm(tr(lang, "deleteAccountConfirm"))) onDeleteAccount?.();
                }}
                className="mt-2 w-full py-2 rounded-2xl glass text-red-500 font-semibold text-sm hover:bg-red-500/10 transition"
              >
                {tr(lang, "deleteAccount")}
              </button>
            )}
          </Field>
        )}

        <div className="pt-3 border-t border-white/60">
          <p className="text-xs text-ink/55 leading-relaxed">{tr(lang, "aboutText")}</p>
          <p className="text-[11px] text-ink/40 mt-1">{tr(lang, "appVersion")}</p>
          <p className="text-[11px] text-ink/40 mt-2 flex gap-1.5">
            <a href="/terms" target="_blank" rel="noopener noreferrer" className="hover:text-tekhelet hover:underline">
              {tr(lang, "termsLink")}
            </a>
            <span>·</span>
            <a href="/privacy" target="_blank" rel="noopener noreferrer" className="hover:text-tekhelet hover:underline">
              {tr(lang, "privacyLink")}
            </a>
            <span>·</span>
            <a href="/accessibility" target="_blank" rel="noopener noreferrer" className="hover:text-tekhelet hover:underline">
              {tr(lang, "accessibilityLink")}
            </a>
          </p>
        </div>
      </div>
    </Modal>
  );
}
