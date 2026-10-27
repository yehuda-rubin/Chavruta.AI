"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { api, type Me } from "@/lib/api";
import { Icon } from "./Icon";

const field =
  "w-full bg-white border border-line rounded-full px-5 py-3.5 text-[15px] outline-none transition focus:border-indigo focus:ring-4 focus:ring-indigo/15";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const POLL_MS = 20000;

// Parental consent step (spec 009 T091). Shown when /me says parental_consent_required: a minor with no
// school link and no approved consent. The minor enters a parent's email; the parent approves on the public
// /parent-consent/[token] page. While pending, /me is polled so the app opens as soon as the parent says yes.
export function ParentConsentStep({ lang, me, onRefresh }: { lang: Lang; me: Me; onRefresh: () => void }) {
  const { user, signOut } = useAuth();
  const status = me.parental_consent?.status ?? "none";
  const masked = me.parental_consent?.parent_email_masked ?? "";
  const [email, setEmail] = useState("");
  const [changing, setChanging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const waiting = status === "pending" && !changing;

  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(onRefresh, POLL_MS);
    return () => clearInterval(t);
  }, [waiting, onRefresh]);

  const send = async (to: string, resend: boolean) => {
    if (busy) return;
    setError("");
    setNote("");
    const addr = to.trim();
    if (!EMAIL_RE.test(addr)) { setError(tr(lang, "pcInvalidEmail")); return; }
    if (user?.email && addr.toLowerCase() === user.email.toLowerCase()) { setError(tr(lang, "pcSameEmail")); return; }
    setBusy(true);
    try {
      await api.requestParentalConsent(addr);
      setChanging(false);
      setEmail("");
      if (resend) setNote(tr(lang, "pcResent"));
      onRefresh();
    } catch (err) {
      const e2 = err as Error & { status?: number; code?: string };
      if (e2.code === "same_as_child") setError(tr(lang, "pcSameEmail"));
      else if (e2.status === 429) setError(tr(lang, "pcRateLimited"));
      else if (e2.status === 422) setError(tr(lang, "pcInvalidEmail"));
      else setError(tr(lang, "pcFailed"));
    } finally {
      setBusy(false);
    }
  };

  // Resending needs the full address, which the server only returns masked, so the minor retypes it.
  // (The server may also accept a bare re-POST of the same address.)
  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(me.owner);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard unavailable: the ID is selectable text */ }
  };

  const dir = lang === "he" ? "rtl" : "ltr";
  return (
    <div className="min-h-dvh grid place-items-center p-4">
      <div dir={dir} className="glass rounded-[28px] p-8 w-full max-w-md flex flex-col gap-4">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="family_restroom" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-xl font-bold text-tekhelet">
            {tr(lang, waiting ? "pcWaitTitle" : "pcTitle")}
          </h1>
        </div>

        {waiting ? (
          <>
            <p role="status" className="text-sm text-ink/80 leading-relaxed text-center">
              {tr(lang, "pcWaitBody").split("{email}").map((part, i, arr) => (
                <span key={i}>
                  {part}
                  {i < arr.length - 1 && <bdi dir="ltr" className="font-mono text-[13px]">{masked}</bdi>}
                </span>
              ))}
            </p>
            <form onSubmit={(e) => { e.preventDefault(); send(email, true); }} className="flex flex-col gap-2">
              <label className="flex flex-col gap-1 text-xs text-ink/70">
                <span>{tr(lang, "pcEmailLabel")}</span>
                <input type="email" dir="ltr" autoComplete="off" value={email}
                       onChange={(e) => setEmail(e.target.value)} className={field} />
              </label>
              <button type="submit" disabled={busy || !email.trim()}
                      className="py-3 rounded-full glass text-tekhelet font-semibold text-sm disabled:opacity-50">
                {busy ? tr(lang, "authWorking") : tr(lang, "pcResend")}
              </button>
            </form>
            <div className="flex gap-3 justify-center flex-wrap">
              <button type="button" onClick={onRefresh} className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
                {tr(lang, "pcCheckNow")}
              </button>
              <button type="button" onClick={() => { setChanging(true); setError(""); setNote(""); }}
                      className="text-xs text-ink/50 hover:text-tekhelet">
                {tr(lang, "pcChangeEmail")}
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); send(email, false); }} className="flex flex-col gap-3">
            <p className="text-sm text-ink/70 leading-relaxed text-center">{tr(lang, "pcBody")}</p>
            {status === "declined" && (
              <p role="status" className="rounded-2xl p-3 bg-amber-500/10 border border-amber-500/25 text-amber-900 text-sm leading-relaxed">
                {tr(lang, "pcDeclined")}
              </p>
            )}
            {status === "expired" && (
              <p role="status" className="rounded-2xl p-3 bg-amber-500/10 border border-amber-500/25 text-amber-900 text-sm leading-relaxed">
                {tr(lang, "pcExpired")}
              </p>
            )}
            <label className="flex flex-col gap-1 text-xs text-ink/70">
              <span>{tr(lang, "pcEmailLabel")}</span>
              <input type="email" dir="ltr" autoComplete="off" required value={email}
                     onChange={(e) => setEmail(e.target.value)} className={field} />
            </label>
            <button type="submit" disabled={busy || !email.trim()}
                    className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60">
              {busy ? tr(lang, "authWorking") : tr(lang, "pcSend")}
            </button>
          </form>
        )}

        {error && <p role="alert" className="text-xs text-red-600 leading-relaxed">{error}</p>}
        {note && <p role="status" className="text-xs text-green-700 leading-relaxed">{note}</p>}

        <section className="rounded-2xl p-3 border border-line flex flex-col gap-2" aria-label={tr(lang, "pcAltHeading")}>
          <h2 className="font-semibold text-xs text-tekhelet">{tr(lang, "pcAltHeading")}</h2>
          <p className="text-xs text-ink/70 leading-relaxed">{tr(lang, "pcAltSchool")}</p>
          <div className="flex items-center gap-2">
            <code dir="ltr" className="flex-1 min-w-0 break-all font-mono text-[11px] text-ink/80 bg-white border border-line rounded-xl px-3 py-2 select-all">
              {me.owner}
            </code>
            <button type="button" onClick={copyId}
                    className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold shrink-0">
              {copied ? tr(lang, "pcCopied") : tr(lang, "pcCopy")}
            </button>
          </div>
          <p className="text-xs text-ink/70 leading-relaxed">{tr(lang, "pcAltParent")}</p>
          <Link href="/family" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            {tr(lang, "pcAltParentLink")}
          </Link>
        </section>

        <button type="button" onClick={() => signOut()} className="text-xs text-ink/50 hover:text-tekhelet">
          {tr(lang, "signOut")}
        </button>
      </div>
    </div>
  );
}
