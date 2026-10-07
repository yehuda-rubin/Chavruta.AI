"use client";
import { useEffect, useState } from "react";
import type { Lang } from "@/lib/types";
import { tr, type StringKey } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { TERMS_VERSION } from "@/lib/legal";
import { Icon } from "./Icon";

// Map Supabase's English auth errors onto localized copy — this is a Hebrew-first product, so the
function authErrorKey(msg: string, mode: "in" | "up" = "in"): StringKey {
  const m = msg.toLowerCase();
  if (
    m.includes("email_daily_quota_exhausted") ||
    m.includes("quota") ||
    m.includes("daily limit") ||
    m.includes("limit exceeded") ||
    m.includes("confirmation mail")
  ) {
    return mode === "up" ? "authErrDailyQuotaExceeded" : "authErrResetQuotaExceeded";
  }
  if (m.includes("invalid login")) return "authErrBadCreds";
  if (m.includes("already registered") || m.includes("already been registered")) return "authErrRegistered";
  if (m.includes("not confirmed") || m.includes("confirm your email")) return "authErrUnconfirmed";
  if (m.includes("at least") && m.includes("password")) return "authErrWeakPassword";
  if (m.includes("email") && (m.includes("invalid") || m.includes("valid"))) return "authErrBadEmail";
  if (m.includes("rate limit")) return "authErrRateLimited";
  return "authGenericError";
}

// Full-screen sign-in gate, shown only when Supabase is configured AND no user is signed in. Headless
// (our own markup) precisely so the form is native Hebrew RTL — the reason we chose Supabase over a
// prebuilt component library. Email + password, with a sign-up toggle.
export function SignIn({ lang }: { lang: Lang }) {
  const { signIn, signUp, resendConfirmation, resetPassword } = useAuth();
  const [resetBusy, setResetBusy] = useState(false);
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  // Separate from the terms box on purpose. Bundling "I accept the terms" with "I am 18" produces one
  // tick that means neither: the age statement has to be its own deliberate act to be worth anything.
  const [confirmedAge, setConfirmedAge] = useState(false);
  // Opt-IN, unchecked by default, and never required — this is what makes a later marketing email
  // lawful under the anti-spam law (Communications Law §30A), which needs explicit prior consent
  // separate from accepting the terms.
  const [marketingConsent, setMarketingConsent] = useState(false);

  // Email confirmation state & 60-second cooldown timer
  const [confirmPendingEmail, setConfirmPendingEmail] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(60);
  const [resendBusy, setResendBusy] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const [billingEnabled, setBillingEnabled] = useState(false);

  useEffect(() => {
    api.billingConfig().then((c) => setBillingEnabled(Boolean(c?.enabled))).catch(() => setBillingEnabled(false));
  }, []);

  useEffect(() => {
    try {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get("ref") || sp.get("mode") === "up" || sp.get("mode") === "signup") {
        setMode("up");
      }
    } catch {}
  }, []);

  useEffect(() => {
    if (!confirmPendingEmail || resendCooldown <= 0) return;
    const interval = setInterval(() => {
      setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [confirmPendingEmail, resendCooldown]);

  const handleResend = async () => {
    if (!confirmPendingEmail || resendCooldown > 0 || resendBusy) return;
    setResendBusy(true);
    setError("");
    setResendSuccess(false);
    try {
      await resendConfirmation(confirmPendingEmail);
      setResendSuccess(true);
      setResendCooldown(60);
    } catch (err) {
      const raw = err instanceof Error ? err.message : "";
      setError(tr(lang, authErrorKey(raw, "up")));
    } finally {
      setResendBusy(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");
    // Registration requires accepting the terms; enforced here (and the button is disabled without it).
    if (mode === "up" && !acceptedTerms) {
      setError(tr(lang, "termsMustAccept"));
      return;
    }
    if (mode === "up" && !confirmedAge) {
      setError(tr(lang, "ageMustConfirm"));
      return;
    }
    setBusy(true);
    try {
      if (mode === "up") {
        // Record consent durably on the account (which terms version, when) — and the age statement
        // alongside it. This is a self-declaration, not verification: it establishes who the service
        // is for and what the user said, which is what the model providers' terms turn on.
        const { needsConfirm } = await signUp(email.trim(), password, {
          terms_version: TERMS_VERSION,
          terms_accepted_at: new Date().toISOString(),
          age_confirmed_18: true,
          age_confirmed_at: new Date().toISOString(),
          // Recorded either way (true or false) so "never asked" and "declined" stay distinguishable.
          marketing_consent: marketingConsent,
          marketing_consent_at: new Date().toISOString(),
        });
        if (needsConfirm) {
          setConfirmPendingEmail(email.trim());
          setResendCooldown(60);
          setResendSuccess(false);
        }
      } else {
        await signIn(email.trim(), password);
      }
    } catch (err) {
      // Supabase returns an English message (e.g. "Invalid login credentials") — localize it.
      const raw = err instanceof Error ? err.message : "";
      setError(tr(lang, authErrorKey(raw, mode)));
    } finally {
      setBusy(false);
    }
  };

  const requestReset = async () => {
    setError("");
    setNotice("");
    if (!email.trim()) {
      setError(tr(lang, "resetPasswordNeedsEmail"));
      return;
    }
    setResetBusy(true);
    try {
      await resetPassword(email.trim());
      setNotice(tr(lang, "resetPasswordSent"));
    } catch (err) {
      const raw = err instanceof Error ? err.message : "";
      setError(tr(lang, authErrorKey(raw, "in")));
    } finally {
      setResetBusy(false);
    }
  };

  if (confirmPendingEmail) {
    return (
      <div className="min-h-dvh grid place-items-center p-4">
        <div className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-5 text-center">
          <div className="h-16 w-16 rounded-2xl grad mx-auto grid place-items-center text-white shadow-md">
            <Icon name="mark_email_read" className="text-[32px]" />
          </div>
          <div className="flex flex-col gap-1.5">
            <h2 className="font-serif text-2xl font-bold text-tekhelet">{tr(lang, "authConfirmSentTitle")}</h2>
            <p className="text-xs text-ink/75 leading-relaxed">
              {tr(lang, "authConfirmSentDesc")}{" "}
              <strong className="text-tekhelet font-semibold dir-ltr inline-block">{confirmPendingEmail}</strong>
            </p>
            <p className="text-[11px] text-ink/50 leading-relaxed mt-1">
              {tr(lang, "authConfirmCheckSpam")}
            </p>
          </div>

          {resendSuccess && (
            <div className="rounded-2xl p-2.5 bg-emerald-500/10 border border-emerald-500/25 text-emerald-800 text-xs flex items-center justify-center gap-2">
              <Icon name="check_circle" className="text-emerald-600 text-sm" />
              <span>{tr(lang, "authResendSuccess")}</span>
            </div>
          )}

          {error && (
            error === tr(lang, "authErrDailyQuotaExceeded") ? (
              <div className="rounded-2xl p-3 bg-amber-500/10 border border-amber-500/25 text-amber-900 flex items-start gap-2.5 text-xs leading-relaxed text-right">
                <Icon name="schedule" className="text-amber-700 text-base shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            ) : (
              <p className="text-xs text-red-600 leading-relaxed">{error}</p>
            )
          )}

          <div className="flex flex-col gap-2.5 pt-1">
            <button
              onClick={handleResend}
              disabled={resendBusy || resendCooldown > 0}
              className="py-3 px-4 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-50 flex items-center justify-center gap-2 shadow-sm"
            >
              {resendBusy ? (
                <span>{tr(lang, "authWorking")}</span>
              ) : resendCooldown > 0 ? (
                <>
                  <Icon name="schedule" className="text-base" />
                  <span>{tr(lang, "authResendCooldown").replace("{seconds}", String(resendCooldown))}</span>
                </>
              ) : (
                <>
                  <Icon name="refresh" className="text-base" />
                  <span>{tr(lang, "authResendEmail")}</span>
                </>
              )}
            </button>

            <button
              onClick={() => {
                setConfirmPendingEmail(null);
                setError("");
                setResendSuccess(false);
              }}
              className="text-xs text-ink/55 hover:text-tekhelet py-1 transition"
            >
              {tr(lang, "authChangeEmail")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const field =
    "w-full bg-white border border-line rounded-full px-5 py-3.5 text-[15px] outline-none transition focus:border-indigo focus:ring-4 focus:ring-indigo/15";

  // A worked example beside the form: the product's whole promise (a cited answer) in one glance.
  const demoQ = lang === "he" ? "למה התורה מתחילה ב״בראשית״?" : "Why does the Torah begin with “Bereshit”?";
  const demoA = lang === "he"
    ? "רש״י עונה על כך כבר בפסוק הראשון, ומפנה למצווה הראשונה."
    : "Rashi answers this at the very first verse, pointing to the first commandment.";

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-2 lg:gap-5 lg:p-5">
      <div className="grid place-items-center p-4">
      <div className="w-full max-w-sm flex flex-col gap-5">
        <div className="flex flex-col items-start gap-2">
          <a href="/welcome" className="inline-flex items-center gap-2.5 mb-6 font-extrabold text-2xl text-ink">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" className="h-10 w-10" />
            {tr(lang, "brand")}
          </a>
          <h1 className="font-serif text-4xl font-extrabold text-ink leading-tight">{tr(lang, mode === "up" ? "signUpBtn" : "signInTitle")}</h1>
          <p className="text-sm text-ink/60 leading-relaxed">{tr(lang, "signInSubtitle")}</p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={field}
            placeholder={tr(lang, "signInEmail")}
          />
          <input
            type="password"
            required
            autoComplete={mode === "up" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={field}
            placeholder={tr(lang, "signInPassword")}
          />

          {/* Terms acceptance — required to register. */}
          {mode === "up" && (
            <label className="flex items-start gap-2 text-xs text-ink/70 leading-relaxed cursor-pointer">
              <input
                type="checkbox"
                checked={acceptedTerms}
                onChange={(e) => setAcceptedTerms(e.target.checked)}
                className="mt-0.5 accent-tekhelet"
              />
              <span>
                {tr(lang, "termsAgreePrefix")}{" "}
                <a href="/terms" target="_blank" rel="noopener noreferrer"
                   className="text-tekhelet font-semibold hover:underline">
                  {tr(lang, "termsLink")}
                </a>{" "}
                {tr(lang, "termsAnd")}{" "}
                <a href="/privacy" target="_blank" rel="noopener noreferrer"
                   className="text-tekhelet font-semibold hover:underline">
                  {tr(lang, "privacyLink")}
                </a>
              </span>
            </label>
          )}

          {/* Age gate — required to register. The service is not directed at minors. */}
          {mode === "up" && (
            <label className="flex items-start gap-2 text-xs text-ink/70 leading-relaxed cursor-pointer">
              <input
                type="checkbox"
                checked={confirmedAge}
                onChange={(e) => setConfirmedAge(e.target.checked)}
                className="mt-0.5 accent-tekhelet"
              />
              <span>{tr(lang, "ageConfirm")}</span>
            </label>
          )}

          {/* Marketing consent — optional and unchecked by default; never blocks submission. */}
          {mode === "up" && (
            <label className="flex items-start gap-2 text-xs text-ink/70 leading-relaxed cursor-pointer">
              <input
                type="checkbox"
                checked={marketingConsent}
                onChange={(e) => setMarketingConsent(e.target.checked)}
                className="mt-0.5 accent-tekhelet"
              />
              <span>{tr(lang, "marketingConsentLabel")}</span>
            </label>
          )}

          {error && (
            error === tr(lang, "authErrDailyQuotaExceeded") || error === tr(lang, "authErrResetQuotaExceeded") ? (
              <div className="rounded-2xl p-3 bg-amber-500/10 border border-amber-500/25 text-amber-900 flex items-start gap-2.5 text-xs leading-relaxed">
                <Icon name="schedule" className="text-amber-700 text-base shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                <p className="text-xs text-red-600 leading-relaxed">{error}</p>
                {error === tr(lang, "authErrUnconfirmed") && email.trim() && (
                  <button
                    type="button"
                    onClick={() => {
                      setConfirmPendingEmail(email.trim());
                      setResendCooldown(0);
                      setError("");
                      setResendSuccess(false);
                    }}
                    className="text-xs text-tekhelet font-semibold hover:underline self-start"
                  >
                    {tr(lang, "authResendEmail")}
                  </button>
                )}
              </div>
            )
          )}
          {notice && <p className="text-xs text-green-700 leading-relaxed">{notice}</p>}

          <button
            type="submit"
            disabled={busy || (mode === "up" && (!acceptedTerms || !confirmedAge))}
            className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60"
          >
            {busy ? tr(lang, "authWorking") : tr(lang, mode === "up" ? "signUpBtn" : "signInBtn")}
          </button>
        </form>

        {mode === "up" && billingEnabled && (
          <a
            href="/partner"
            className="flex items-center gap-2 p-2.5 rounded-2xl bg-tekhelet/5 border border-tekhelet/15 text-tekhelet hover:bg-tekhelet/10 transition justify-center text-xs font-semibold text-center"
          >
            <Icon name="groups" className="text-base shrink-0" />
            <span>{tr(lang, "partnerSignUpBadge")}</span>
          </a>
        )}

        {mode === "in" && (
          <button
            onClick={requestReset}
            disabled={resetBusy}
            className="text-xs text-ink/50 hover:text-tekhelet -mt-2 disabled:opacity-60"
          >
            {tr(lang, "forgotPassword")}
          </button>
        )}

        <button
          onClick={() => {
            setMode(mode === "in" ? "up" : "in");
            setError("");
            setNotice("");
          }}
          className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold"
        >
          {tr(lang, mode === "in" ? "signInToSignUp" : "signInToSignIn")}
        </button>

        <p className="text-[11px] text-ink/40 text-center">{tr(lang, "footer")}</p>
        <p className="text-[11px] text-ink/40 text-center flex flex-wrap justify-center gap-1.5">
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
          {billingEnabled && (
            <>
              <span>·</span>
              <a href="/partner" className="hover:text-tekhelet hover:underline">
                {tr(lang, "partnerProgramLink")}
              </a>
            </>
          )}
        </p>
      </div>
      </div>

      <aside
        aria-hidden="true"
        className="hidden lg:flex flex-col justify-end gap-3.5 rounded-[36px] p-10 text-white relative overflow-hidden"
        style={{ background: "linear-gradient(150deg,#5b3df5,#8d5cff 60%,#ff6b5e)" }}
      >
        <div className="self-start max-w-[85%] rounded-3xl rounded-es-md bg-white/20 backdrop-blur px-5 py-3.5 text-xl">{demoQ}</div>
        <div className="self-end max-w-[90%] rounded-3xl rounded-ee-md bg-white text-ink px-5 py-3.5 text-lg">{demoA}</div>
      </aside>
    </div>
  );
}
