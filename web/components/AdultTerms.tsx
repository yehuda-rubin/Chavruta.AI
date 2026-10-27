"use client";
import { useState } from "react";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { TERMS_VERSION } from "@/lib/legal";
import { Icon } from "./Icon";

// Shown when /me says adult_terms_required: the account has turned 18 and has not yet accepted the
// adult Terms. Sending is blocked server-side (403 adult_terms_required) until it does, so this takes
// the place of the app rather than sitting beside it. Marketing consent is a separate, optional,
// unticked choice and is never bundled with the terms.
export function AdultTerms({ lang, onDone }: { lang: Lang; onDone: () => void }) {
  const { updateMetadata, signOut } = useAuth();
  const [accepted, setAccepted] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (busy) return;
    if (!accepted) { setError(tr(lang, "adultTermsMustAccept")); return; }
    setBusy(true);
    setError("");
    try {
      await api.acceptAdultTerms(TERMS_VERSION);
      if (marketing) {
        try {
          await updateMetadata({ marketing_consent: true, marketing_consent_at: new Date().toISOString() });
        } catch { /* optional; the terms are what matter */ }
      }
      onDone();
    } catch {
      setError(tr(lang, "authGenericError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh grid place-items-center p-4">
      <div dir={lang === "he" ? "rtl" : "ltr"} className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-4">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="menu_book" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "adultTermsTitle")}</h1>
          <p className="text-sm text-ink/70 leading-relaxed">{tr(lang, "adultTermsBody")}</p>
        </div>

        <label className="flex items-start gap-2 text-xs text-ink/70 leading-relaxed cursor-pointer">
          <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)}
                 className="mt-0.5 accent-tekhelet" />
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
          <input type="checkbox" checked={marketing} onChange={(e) => setMarketing(e.target.checked)}
                 className="mt-0.5 accent-tekhelet" />
          <span>{tr(lang, "marketingConsentLabel")}</span>
        </label>

        {error && <p role="alert" className="text-xs text-red-600 leading-relaxed">{error}</p>}

        <button onClick={submit} disabled={busy || !accepted}
                className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60">
          {busy ? tr(lang, "authWorking") : tr(lang, "adultTermsContinue")}
        </button>
        <button onClick={() => signOut()} className="text-xs text-ink/50 hover:text-tekhelet">
          {tr(lang, "signOut")}
        </button>
      </div>
    </div>
  );
}
