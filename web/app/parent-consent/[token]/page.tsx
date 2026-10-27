"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr, type StringKey } from "@/lib/i18n";
import { api } from "@/lib/api";
import { Icon } from "@/components/Icon";

// The parent's consent page (spec 009 T091). PUBLIC: no sign-in, no account, no marketing, no prices.
// Served at /parent-consent/[token], NOT /consent/[token]: /consent is an API prefix (nginx.conf and
// next.config.mjs proxy it to FastAPI), so a page there would be shadowed. This page calls the API at
// /consent/{token}. The text is Part A of specs/009-school-minors/legal-drafts/parent-consent-he.md.
// It never shows the child's name or email; the API does not send them.

type View =
  | { kind: "loading" }
  | { kind: "ready"; expiresAt?: string }
  | { kind: "done"; decision: "approve" | "decline" }
  | { kind: "already" }
  | { kind: "expired" }
  | { kind: "invalid" }
  | { kind: "error" };

const BEFORE_RULES: [StringKey, StringKey][] = [["pcPublicWhatH", "pcPublicWhat"]];
const AFTER_RULES: [StringKey, StringKey][] = [
  ["pcPublicDataH", "pcPublicData"],
  ["pcPublicKeepH", "pcPublicKeep"],
  ["pcPublicTrainH", "pcPublicTrain"],
  ["pcPublicCrisisH", "pcPublicCrisis"],
  ["pcPublicNoBuyH", "pcPublicNoBuy"],
  ["pcPublicGivesH", "pcPublicGives"],
  ["pcPublicRevokeH", "pcPublicRevoke"],
];

export default function ParentConsentPage() {
  const params = useParams<{ token: string }>();
  const token = Array.isArray(params?.token) ? params.token[0] : params?.token;
  const [lang, setLang] = useState<Lang>("he");
  const [view, setView] = useState<View>({ kind: "loading" });
  const [busy, setBusy] = useState<"" | "approve" | "decline">("");
  const [actionError, setActionError] = useState(false);

  useEffect(() => {
    let l: Lang = "he";
    try {
      const sp = new URLSearchParams(window.location.search).get("lang");
      const saved = localStorage.getItem("chavruta-lang");
      if (sp === "he" || sp === "en") l = sp;
      else if (saved === "he" || saved === "en") l = saved;
    } catch {}
    setLang(l);
  }, []);

  const toggleLang = () => {
    const next: Lang = lang === "he" ? "en" : "he";
    setLang(next);
    try { localStorage.setItem("chavruta-lang", next); } catch {}
  };

  useEffect(() => {
    if (!token) { setView({ kind: "invalid" }); return; }
    let live = true;
    api.consentInfo(token).then((r) => {
      if (!live) return;
      if (r.status === "pending") setView({ kind: "ready", expiresAt: r.expires_at });
      else if (r.status === "expired") setView({ kind: "expired" });
      else if (r.status === "approved" || r.status === "declined") setView({ kind: "already" });
      else setView({ kind: "invalid" });
    }).catch((err) => {
      if (!live) return;
      const status = (err as Error & { status?: number }).status;
      if (status === 410) setView({ kind: "expired" });
      else if (status === 404) setView({ kind: "invalid" });
      else setView({ kind: "error" });
    });
    return () => { live = false; };
  }, [token]);

  const decide = async (decision: "approve" | "decline") => {
    if (!token || busy) return;
    setBusy(decision);
    setActionError(false);
    try {
      await api.consentDecide(token, decision);
      setView({ kind: "done", decision });
    } catch (err) {
      const status = (err as Error & { status?: number }).status;
      if (status === 410) setView({ kind: "expired" });
      else if (status === 404) setView({ kind: "invalid" });
      else if (status === 409) setView({ kind: "already" });
      else setActionError(true);
    } finally {
      setBusy("");
    }
  };

  const dir = lang === "he" ? "rtl" : "ltr";
  let expires = "";
  if (view.kind === "ready" && view.expiresAt) {
    const d = new Date(view.expiresAt);
    if (!isNaN(d.getTime())) expires = d.toLocaleDateString(lang === "he" ? "he-IL" : "en-US");
  }

  const notice = (key: StringKey, tone: "ok" | "warn") => (
    <p role="status"
       className={`rounded-2xl p-4 text-sm leading-relaxed border ${
         tone === "ok" ? "bg-green-500/10 border-green-500/25 text-green-900"
                       : "bg-amber-500/10 border-amber-500/25 text-amber-900"}`}>
      {tr(lang, key)}
    </p>
  );

  const section = ([h, t]: [StringKey, StringKey]) => (
    <section key={h} className="flex flex-col gap-1">
      <h2 className="font-serif font-bold text-tekhelet">{tr(lang, h)}</h2>
      <p className="text-sm text-ink/80 leading-relaxed">{tr(lang, t)}</p>
    </section>
  );

  let body: React.ReactNode;
  if (view.kind === "loading") body = <p role="status" className="text-sm text-ink/50">{tr(lang, "pcPublicLoading")}</p>;
  else if (view.kind === "done") body = notice(view.decision === "approve" ? "pcPublicApproved" : "pcPublicDeclined", view.decision === "approve" ? "ok" : "warn");
  else if (view.kind === "already") body = notice("pcPublicAlready", "warn");
  else if (view.kind === "expired") body = notice("pcPublicExpired", "warn");
  else if (view.kind === "invalid") body = notice("pcPublicInvalid", "warn");
  else if (view.kind === "error") body = notice("pcPublicFailed", "warn");
  else {
    body = (
      <>
        <p className="text-sm text-ink/80 leading-relaxed">{tr(lang, "pcPublicIntro")}</p>
        {BEFORE_RULES.map(section)}
        <section className="flex flex-col gap-1">
          <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "pcPublicRulesH")}</h2>
          <ul className="flex flex-col gap-1.5 text-sm text-ink/80 leading-relaxed">
            {(["pcPublicRule1", "pcPublicRule2", "pcPublicRule3", "pcPublicRule4"] as const).map((k) => (
              <li key={k} className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-gold-soft shrink-0" aria-hidden="true" />
                <span>{tr(lang, k)}</span>
              </li>
            ))}
          </ul>
        </section>
        {AFTER_RULES.map(section)}
        <p className="text-sm text-ink/80">
          {tr(lang, "pcPublicFull")}{" "}
          <Link href="/terms" target="_blank" className="text-tekhelet underline">{tr(lang, "pcPublicTerms")}</Link>
          {" · "}
          <Link href="/privacy" target="_blank" className="text-tekhelet underline">{tr(lang, "pcPublicPrivacy")}</Link>
        </p>
        <div className="glass rounded-2xl p-4 flex flex-col gap-3">
          <div className="flex gap-2 flex-wrap">
            <button type="button" disabled={!!busy} onClick={() => decide("approve")}
                    className="flex-1 min-w-56 py-3 px-4 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60">
              {busy === "approve" ? tr(lang, "pcPublicWorking") : tr(lang, "pcPublicApprove")}
            </button>
            <button type="button" disabled={!!busy} onClick={() => decide("decline")}
                    className="py-3 px-5 rounded-full glass text-ink/80 font-semibold text-sm disabled:opacity-60">
              {busy === "decline" ? tr(lang, "pcPublicWorking") : tr(lang, "pcPublicDecline")}
            </button>
          </div>
          <p className="text-[11px] text-ink/50 leading-relaxed">
            {tr(lang, "pcPublicRecorded")}{expires ? ` · ${expires}` : ""}
          </p>
          {actionError && <p role="alert" className="text-xs text-red-600">{tr(lang, "pcPublicFailed")}</p>}
        </div>
      </>
    );
  }

  return (
    <div dir={dir} lang={lang} className="min-h-dvh flex flex-col gap-4 p-4 lg:p-8 max-w-2xl mx-auto">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Icon name="family_restroom" className="text-tekhelet text-[28px]" />
          <h1 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "pcPublicTitle")}</h1>
        </div>
        <button onClick={toggleLang} className="px-3 py-1.5 rounded-full glass text-ink/70 text-xs font-semibold">
          עברית · EN
        </button>
      </header>
      {body}
    </div>
  );
}
