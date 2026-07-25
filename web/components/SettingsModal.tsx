"use client";
import { useState } from "react";
import type { Lang } from "@/lib/types";
import { IntentId, tr, StringKey } from "@/lib/i18n";
import { Modal } from "./Modal";
import { useAuth } from "@/lib/auth";

export type Theme = "light" | "dark" | "auto";

// Default-mode options match the static UI (lesson / explain / qa / shut).
const MODES: { id: IntentId; key: StringKey }[] = [
  { id: "lesson", key: "lesson" },
  { id: "explain", key: "explain" },
  { id: "qa", key: "qa" },
  { id: "shut", key: "shutMode" },
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
  billingEnabled,
  onUpgrade,
  onCancelSubscription,
  onRedeemCoupon,
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
  billingEnabled?: boolean;
  onUpgrade?: () => void;
  onCancelSubscription?: () => void;
  onRedeemCoupon?: (code: string) => Promise<string>;   // resolves with a message to show
}) {
  const auth = useAuth();
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
              <span className="text-xs text-ink/60 truncate">{auth.user.email}</span>
              <button
                onClick={() => auth.signOut()}
                className="px-4 py-2 rounded-2xl glass text-red-500 font-semibold text-sm hover:bg-red-500/10 transition shrink-0"
              >
                {tr(lang, "signOut")}
              </button>
            </div>

            {/* Plan + billing — upgrade (free) or cancel subscription (paid). */}
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-xs text-ink/60">
                {tr(lang, "planLabel")}: {planName || tr(lang, "planFree")}
                {planUntil && <> · {tr(lang, "planUntil")} {fmtDate(planUntil)}</>}
                {!!credits && <> · {credits} {tr(lang, "creditsLabel")}</>}
              </span>
              {plan && plan !== "free" ? (
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

            {/* Coupon redemption — grants a time-boxed plan or prepaid credits. Always shown to a
                signed-in user, including when billing is off: coupons are the one way to get paid
                access on a deployment with no payment provider configured. */}
            {onRedeemCoupon && <CouponField lang={lang} onRedeem={onRedeemCoupon} />}

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
        </div>
      </div>
    </Modal>
  );
}
