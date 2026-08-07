"use client";
import { useState } from "react";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { TERMS_VERSION } from "@/lib/legal";
import { Icon } from "./Icon";

// Shown instead of the app when a signed-in account is missing terms/age consent in its
// user_metadata — the case an account created by calling Supabase's own signup API directly (not
// through SignIn.tsx) falls into, since that path skips both checkboxes entirely. The backend
// already 403s every route except /me and /account for such an account (see app/security.py
// require_auth, docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md Finding A) — this is the self-serve way
// out, rather than a dead-end error.
export function ConfirmConsent({ lang }: { lang: Lang }) {
  const { updateMetadata, signOut } = useAuth();
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [confirmedAge, setConfirmedAge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!acceptedTerms || !confirmedAge || busy) return;
    setBusy(true);
    setError("");
    try {
      await updateMetadata({
        terms_version: TERMS_VERSION,
        terms_accepted_at: new Date().toISOString(),
        age_confirmed_18: true,
        age_confirmed_at: new Date().toISOString(),
      });
      // onAuthStateChange (lib/auth.tsx) picks up the USER_UPDATED event and refreshes `user`,
      // which re-renders page.tsx past this gate automatically — no manual redirect needed.
    } catch (err) {
      setError(err instanceof Error ? err.message : tr(lang, "authGenericError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh grid place-items-center p-4">
      <div className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-4">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="menu_book" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "termsTitle")}</h1>
        </div>

        <label className="flex items-start gap-2 text-xs text-ink/70 leading-relaxed cursor-pointer">
          <input type="checkbox" checked={acceptedTerms}
                 onChange={(e) => setAcceptedTerms(e.target.checked)} className="mt-0.5 accent-tekhelet" />
          <span>
            {tr(lang, "termsAgreePrefix")}{" "}
            <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-tekhelet font-semibold hover:underline">
              {tr(lang, "termsLink")}
            </a>{" "}
            {tr(lang, "termsAnd")}{" "}
            <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-tekhelet font-semibold hover:underline">
              {tr(lang, "privacyLink")}
            </a>
          </span>
        </label>

        <label className="flex items-start gap-2 text-xs text-ink/70 leading-relaxed cursor-pointer">
          <input type="checkbox" checked={confirmedAge}
                 onChange={(e) => setConfirmedAge(e.target.checked)} className="mt-0.5 accent-tekhelet" />
          <span>{tr(lang, "ageConfirm")}</span>
        </label>

        {error && <p className="text-xs text-red-600 leading-relaxed">{error}</p>}

        <button
          onClick={submit}
          disabled={busy || !acceptedTerms || !confirmedAge}
          className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60"
        >
          {busy ? tr(lang, "authWorking") : tr(lang, "signInBtn")}
        </button>

        <button onClick={() => signOut()} className="text-xs text-ink/50 hover:text-tekhelet">
          {tr(lang, "signOut")}
        </button>
      </div>
    </div>
  );
}
