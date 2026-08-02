"use client";
import { useState } from "react";
import type { Lang } from "@/lib/types";
import { tr, type StringKey } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { TERMS_VERSION } from "@/lib/legal";
import { Icon } from "./Icon";

// Map Supabase's English auth errors onto localized copy — this is a Hebrew-first product, so the
// message a user actually sees must be Hebrew. Unknown errors fall through to a generic string.
function authErrorKey(msg: string): StringKey {
  const m = msg.toLowerCase();
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
  const { signIn, signUp, resetPassword } = useAuth();
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
        if (needsConfirm) setNotice(tr(lang, "authCheckEmail"));
      } else {
        await signIn(email.trim(), password);
      }
    } catch (err) {
      // Supabase returns an English message (e.g. "Invalid login credentials") — localize it.
      const raw = err instanceof Error ? err.message : "";
      setError(tr(lang, authErrorKey(raw)));
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
      setError(tr(lang, authErrorKey(raw)));
    } finally {
      setResetBusy(false);
    }
  };

  const field =
    "w-full glass rounded-2xl px-4 py-3 font-serif text-[15px] outline-none focus:ring-2 focus:ring-indigo/30";

  return (
    <div className="min-h-screen grid place-items-center p-4">
      <div className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-5">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="menu_book" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-2xl font-bold text-tekhelet">{tr(lang, "signInTitle")}</h1>
          <p className="text-xs text-ink/55 leading-relaxed">{tr(lang, "signInSubtitle")}</p>
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

          {error && <p className="text-xs text-red-600 leading-relaxed">{error}</p>}
          {notice && <p className="text-xs text-green-700 leading-relaxed">{notice}</p>}

          <button
            type="submit"
            disabled={busy || (mode === "up" && (!acceptedTerms || !confirmedAge))}
            className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60"
          >
            {busy ? tr(lang, "authWorking") : tr(lang, mode === "up" ? "signUpBtn" : "signInBtn")}
          </button>
        </form>

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
        <p className="text-[11px] text-ink/40 text-center flex justify-center gap-1.5">
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
  );
}
