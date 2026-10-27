"use client";
import { useCallback, useEffect, useState } from "react";
import type { Lang } from "@/lib/types";
import { api, type CrisisAlert, type OrgMember } from "@/lib/api";
import { tr, type StringKey } from "@/lib/i18n";
import { ContentTree } from "./ContentTree";

// School-track minors sections (spec 009), added to /school WITHOUT touching the existing student-code
// button or anything else on that page. What the school may see here is deliberately thin: alerts carry
// a category, a time and a "minor" badge, never text and never an age. Every /orgs/* route 404s for
// someone without the role it needs, so a section that fails to load is simply not drawn.

function JoinRequest({ lang }: { lang: Lang }) {
  const [id, setId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id.trim() || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.orgs.requestJoin(id.trim());
      setId("");
      setMsg({ ok: true, text: tr(lang, "schoolJoinReqSent") });
    } catch {
      setMsg({ ok: false, text: tr(lang, "schoolJoinReqFailed") });
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="glass rounded-2xl p-4 flex flex-col gap-3">
      <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "schoolJoinReqHeading")}</h2>
      <p className="text-[11px] text-ink/50 leading-relaxed">{tr(lang, "schoolJoinReqExplainer")}</p>
      <form onSubmit={send} className="flex gap-2 flex-wrap">
        <input
          value={id}
          onChange={(e) => setId(e.target.value)}
          dir="ltr"
          aria-label={tr(lang, "schoolJoinReqPlaceholder")}
          placeholder={tr(lang, "schoolJoinReqPlaceholder")}
          className="flex-1 min-w-48 bg-white border border-line rounded-xl px-3 py-2 text-sm font-mono outline-none focus:border-indigo"
        />
        <button disabled={busy || !id.trim()}
                className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40">
          {tr(lang, "schoolJoinReqBtn")}
        </button>
      </form>
      {msg && (
        <p role={msg.ok ? "status" : "alert"} className={`text-xs ${msg.ok ? "text-green-700" : "text-red-600"}`}>
          {msg.text}
        </p>
      )}
    </section>
  );
}

function SafetyContacts({ lang, members }: { lang: Lang; members: OrgMember[] }) {
  const staff = members.filter((m) => m.accepted && (m.role === "admin" || m.role === "teacher"));
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [bad, setBad] = useState(false);

  useEffect(() => {
    api.orgs.safetyContacts().then((r) => setChosen(new Set(r.owner_ids))).catch(() => {});
  }, []);

  const save = async () => {
    setBusy(true);
    setMsg("");
    setBad(false);
    try {
      const r = await api.orgs.setSafetyContacts([...chosen]);
      setChosen(new Set(r.owner_ids));
      setMsg(tr(lang, "schoolSafetySaved"));
    } catch {
      setBad(true);
      setMsg(tr(lang, "schoolAlertFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass rounded-2xl p-4 flex flex-col gap-3">
      <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "schoolSafetyHeading")}</h2>
      <p className="text-[11px] text-ink/50 leading-relaxed">{tr(lang, "schoolSafetyExplainer")}</p>
      {staff.length === 0 ? (
        <p className="text-xs text-ink/40">{tr(lang, "schoolSafetyNone")}</p>
      ) : (
        <fieldset className="flex flex-col gap-1.5">
          <legend className="sr-only">{tr(lang, "schoolSafetyHeading")}</legend>
          {staff.map((m) => (
            <label key={m.owner_id} className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={chosen.has(m.owner_id)}
                onChange={(e) => setChosen((p) => {
                  const n = new Set(p);
                  if (e.target.checked) n.add(m.owner_id); else n.delete(m.owner_id);
                  return n;
                })}
                className="accent-tekhelet"
              />
              <span className="font-mono text-[11px] text-ink/70">{m.owner_id}</span>
            </label>
          ))}
        </fieldset>
      )}
      <div className="flex items-center gap-3">
        <button disabled={busy || staff.length === 0} onClick={save}
                className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40">
          {tr(lang, "schoolSafetySave")}
        </button>
        <span role={bad ? "alert" : "status"} className={`text-xs ${bad ? "text-red-600" : "text-ink/60"}`}>{msg}</span>
      </div>
    </section>
  );
}

function Alerts({ lang }: { lang: Lang }) {
  const [alerts, setAlerts] = useState<CrisisAlert[] | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    api.orgs.alerts().then((r) => setAlerts(r.alerts)).catch(() => setAlerts(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const ack = async (id: number) => {
    setBusyId(id);
    setError("");
    try {
      await api.orgs.ackAlert(id);
      load();
    } catch {
      setError(tr(lang, "schoolAlertFailed"));
    } finally {
      setBusyId(null);
    }
  };

  if (alerts === null) return null;       // not a safety contact or admin: nothing to show
  const catLabel = (c: string) => {
    const key = `schoolAlertCat_${c}` as StringKey;
    return key in STRINGS_KEYS ? tr(lang, key) : c;
  };
  const when = (iso: string) =>
    new Date(iso).toLocaleString(lang === "he" ? "he-IL" : "en-US", { dateStyle: "medium", timeStyle: "short" });

  return (
    <section className="glass rounded-2xl p-4 flex flex-col gap-3">
      <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "schoolAlertsHeading")}</h2>
      <p className="text-[11px] text-ink/50 leading-relaxed">{tr(lang, "schoolAlertsExplainer")}</p>
      {alerts.length === 0 ? (
        <p className="text-xs text-ink/40">{tr(lang, "schoolAlertsEmpty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => (
            <li key={a.id} className="flex items-center gap-2 flex-wrap text-xs border-t border-ink/10 pt-2">
              {a.minor && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-tekhelet/10 text-tekhelet">
                  {tr(lang, "schoolAlertMinor")}
                </span>
              )}
              <span className="font-mono text-[11px] text-ink/70">{a.student_label}</span>
              <span className="text-ink/80">{catLabel(a.category)}</span>
              {a.immediate_danger && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-500/10 text-red-700">
                  {tr(lang, "schoolAlertDanger")}
                </span>
              )}
              <span className="text-ink/50">{when(a.created_at)}</span>
              {a.acknowledged ? (
                <span className="text-ink/50">{tr(lang, "schoolAlertAcked")}</span>
              ) : (
                <button disabled={busyId === a.id} onClick={() => ack(a.id)}
                        className="text-[11px] px-2 py-1 rounded-lg glass text-tekhelet disabled:opacity-40">
                  {tr(lang, "schoolAlertAck")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    </section>
  );
}

// tr() takes a StringKey; the alert categories are open-ended server strings, so check membership.
const STRINGS_KEYS = {
  schoolAlertCat_self_harm: true, schoolAlertCat_suicide: true,
  schoolAlertCat_abuse: true, schoolAlertCat_danger: true,
} as const;

export function SchoolMinors({
  lang, isAdmin, members,
}: {
  lang: Lang; isAdmin: boolean; members: OrgMember[];
}) {
  return (
    <>
      {isAdmin && <JoinRequest lang={lang} />}
      {isAdmin && (
        <section className="glass rounded-2xl p-4 flex flex-col gap-3">
          <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "schoolContentHeading")}</h2>
          <p className="text-[11px] text-ink/50 leading-relaxed">{tr(lang, "schoolContentExplainer")}</p>
          <ContentTree lang={lang} load={api.orgs.content} save={api.orgs.setContent} />
        </section>
      )}
      {isAdmin && <SafetyContacts lang={lang} members={members} />}
      <Alerts lang={lang} />
    </>
  );
}
