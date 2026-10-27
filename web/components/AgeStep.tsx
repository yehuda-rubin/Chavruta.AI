"use client";
import { useState } from "react";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Icon } from "./Icon";

const field =
  "w-full bg-white border border-line rounded-full px-5 py-3.5 text-[15px] outline-none transition focus:border-indigo focus:ring-4 focus:ring-indigo/15";

/** Whole months between a birth month/year and now. Used only for the client-side "under 12" refusal;
 *  the server (POST /account/age) is the authority and answers 422 under_minimum_age on its own. */
export function monthsSinceBirth(year: number, month: number, now = new Date()): number {
  return (now.getFullYear() * 12 + now.getMonth() + 1) - (year * 12 + month);
}
export const MIN_AGE_MONTHS = 12 * 12;

/** Birth month + year selectors. Controlled; `month`/`year` are "" until chosen. */
export function BirthFields({
  lang, month, year, onMonth, onYear,
}: {
  lang: Lang; month: string; year: string; onMonth: (v: string) => void; onYear: (v: string) => void;
}) {
  const locale = lang === "he" ? "he-IL" : "en-US";
  const thisYear = new Date().getFullYear();
  const years: number[] = [];
  for (let y = thisYear; y >= thisYear - 100; y--) years.push(y);
  return (
    <div className="grid grid-cols-2 gap-3">
      <label className="flex flex-col gap-1 text-xs text-ink/70">
        <span>{tr(lang, "ageMonthLabel")}</span>
        <select value={month} onChange={(e) => onMonth(e.target.value)} className={field} required>
          <option value="">{tr(lang, "ageMonthPlaceholder")}</option>
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
            <option key={m} value={m}>
              {new Date(2000, m - 1, 1).toLocaleDateString(locale, { month: "long" })}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink/70">
        <span>{tr(lang, "ageYearLabel")}</span>
        <select value={year} onChange={(e) => onYear(e.target.value)} className={field} required>
          <option value="">{tr(lang, "ageYearPlaceholder")}</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
    </div>
  );
}

/** The short, child-friendly disclosure shown once an account resolves to age 12 to 17. */
export function MinorDisclosure({ lang, onContinue }: { lang: Lang; onContinue: () => void }) {
  return (
    <div className="min-h-dvh grid place-items-center p-4">
      <div dir={lang === "he" ? "rtl" : "ltr"} className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-4">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="info" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "minorDiscTitle")}</h1>
        </div>
        <ul className="flex flex-col gap-3 text-sm text-ink/80 leading-relaxed">
          {(["minorDisc1", "minorDisc2", "minorDisc3", "minorDisc4"] as const).map((k) => (
            <li key={k} className="flex gap-2">
              <span className="mt-2 h-1.5 w-1.5 rounded-full bg-gold-soft shrink-0" aria-hidden="true" />
              <span>{tr(lang, k)}</span>
            </li>
          ))}
        </ul>
        <button onClick={onContinue}
                className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition">
          {tr(lang, "minorDiscContinue")}
        </button>
      </div>
    </div>
  );
}

// The age step. Shown after sign-up, on the first authenticated load, when /me says age_required —
// so a delayed email confirmation needs no special handling: the step simply appears when the person
// is first signed in. Asked once; the server refuses a second answer (409) and under-12 (422).
export function AgeStep({ lang, onDone }: { lang: Lang; onDone: () => void }) {
  const { signOut, updateMetadata } = useAuth();
  const [month, setMonth] = useState("");
  const [year, setYear] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tooYoung, setTooYoung] = useState(false);
  const [minor, setMinor] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const m = Number(month), y = Number(year);
    if (!m || !y) { setError(tr(lang, "ageStepInvalid")); return; }
    if (monthsSinceBirth(y, m) < MIN_AGE_MONTHS) { setTooYoung(true); setError(""); return; }
    setBusy(true);
    setError("");
    try {
      const res = await api.setAge(y, m);
      if (res.is_minor) {
        // A marketing opt-in ticked on the sign-up form, before age was known, is withdrawn here; the
        // server already excludes minors from marketing, this keeps the stored flag honest as well.
        try {
          await updateMetadata({ marketing_consent: false, marketing_consent_at: new Date().toISOString() });
        } catch { /* best effort */ }
        setMinor(true);
      } else {
        onDone();
      }
    } catch (err) {
      const e2 = err as Error & { status?: number; code?: string };
      if (e2.code === "under_minimum_age") setTooYoung(true);
      else if (e2.status === 409) onDone();          // already answered (e.g. another tab): move on
      else setError(tr(lang, "ageStepFailed"));
    } finally {
      setBusy(false);
    }
  };

  if (minor) return <MinorDisclosure lang={lang} onContinue={onDone} />;

  return (
    <div className="min-h-dvh grid place-items-center p-4">
      <form onSubmit={submit} dir={lang === "he" ? "rtl" : "ltr"}
            className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-4">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="cake" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "ageStepTitle")}</h1>
          <p className="text-sm text-ink/70 leading-relaxed">{tr(lang, "ageStepBody")}</p>
        </div>

        {tooYoung ? (
          <p role="alert" className="rounded-2xl p-3 bg-amber-500/10 border border-amber-500/25 text-amber-900 text-sm leading-relaxed">
            {tr(lang, "ageStepTooYoung")}
          </p>
        ) : (
          <>
            <BirthFields lang={lang} month={month} year={year} onMonth={setMonth} onYear={setYear} />
            <p className="text-[11px] text-ink/50 leading-relaxed">{tr(lang, "ageStepNote")}</p>
            {error && <p role="alert" className="text-xs text-red-600 leading-relaxed">{error}</p>}
            <button type="submit" disabled={busy || !month || !year}
                    className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60">
              {busy ? tr(lang, "authWorking") : tr(lang, "ageStepContinue")}
            </button>
          </>
        )}

        <button type="button" onClick={() => signOut()} className="text-xs text-ink/50 hover:text-tekhelet">
          {tr(lang, "signOut")}
        </button>
      </form>
    </div>
  );
}
