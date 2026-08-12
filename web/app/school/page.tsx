"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { api, type OrgPanel } from "@/lib/api";

// The school panel. Same Client-Component reasoning as /admin: it needs state for the fetch and the
// actions, and there is no SEO upside to a page nobody should find.
//
// The gate below is UX only. Every /orgs/* route resolves the caller's own membership server-side
// and 404s — never 403 — whatever this page decides to render.
//
// WHAT THIS PAGE DOES NOT SHOW, and must never be extended to show: the text of anything a member
// wrote. Not a question, not an answer, not a saved lesson. Everything here comes from usage
// counters and usage_events, whose columns are a fixed list of measurements. The tempting shortcut
// — joining `sessions` to list "recent chats" — would surface `first_q`, the verbatim opening
// question of every conversation. See specs/004-school-accounts/plan.md decision 1.

export default function SchoolPanel() {
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState<OrgPanel | null>(null);
  const [denied, setDenied] = useState(false);
  const [demo, setDemo] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback((asDemo: boolean) => {
    setLoading(true);
    setDenied(false);
    api.orgs
      .panel(asDemo)
      .then(setPanel)
      .catch(() => setDenied(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // Try the caller's own school first; the operator, who belongs to none, falls back to the
    // synthetic one so the panel can be inspected without opening a real school's records.
    api.orgs
      .panel(false)
      .then((p) => {
        setPanel(p);
        setLoading(false);
      })
      .catch(() =>
        api.orgs
          .panel(true)
          .then((p) => {
            setPanel(p);
            setDemo(true);
          })
          .catch(() => setDenied(true))
          .finally(() => setLoading(false)),
      );
  }, []);

  async function mintCode(role: string) {
    setBusy(true);
    try {
      const res = await api.orgs.invite(role, role === "student" ? 30 : 1);
      setCode(res.code);
    } finally {
      setBusy(false);
    }
  }

  async function removeMember(ownerId: string) {
    setBusy(true);
    try {
      await api.orgs.removeMember(ownerId);
      load(demo);
    } finally {
      setBusy(false);
    }
  }

  async function setCap(ownerId: string, current: number) {
    const raw = window.prompt("תקרה יומית בטוקנים (0 = ברירת המחדל של המסלול)", String(current));
    if (raw === null) return;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) return;
    setBusy(true);
    try {
      await api.orgs.setCap(ownerId, value);
      load(demo);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="h-dvh grid place-items-center text-ink/50 text-sm">טוען…</div>;
  }

  if (denied || !panel) {
    return (
      <div dir="rtl" className="h-dvh grid place-items-center p-4">
        <div className="glass rounded-[28px] p-8 max-w-sm text-center flex flex-col gap-3">
          <h1 className="font-serif text-xl font-bold text-tekhelet">אין הרשאה</h1>
          <p className="text-sm text-ink/60">העמוד הזה זמין למנהלי מוסד ולמורים בלבד.</p>
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            חזרה לאפליקציה
          </Link>
        </div>
      </div>
    );
  }

  const isAdminRole = panel.role === "admin";
  const num = (n: number) => n.toLocaleString("he-IL");
  // Tokens mean nothing to a reader, so the pool is shown as questions — the unit people think in.
  // 23,512 normalized tokens is the measured mean of a real turn (166 production turns, 2026-08-12).
  const asTurns = (tokens: number) => Math.round(tokens / 23512);
  const ROLE_HE: Record<string, string> = { admin: "מנהל", teacher: "מורה", student: "תלמיד" };

  return (
    <div dir="rtl" className="min-h-dvh flex flex-col gap-4 p-4 lg:p-8">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Icon name="school" className="text-tekhelet text-[28px]" />
          <div>
            <h1 className="font-serif text-xl font-bold text-tekhelet">{panel.name}</h1>
            <p className="text-xs text-ink/50">
              {ROLE_HE[panel.role] ?? panel.role} · {panel.seats_used} מתוך {panel.seats} מושבים
            </p>
          </div>
        </div>
        <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
          חזרה לאפליקציה
        </Link>
      </header>

      {panel.is_demo && (
        <div className="glass rounded-2xl p-3 text-xs text-ink/70 border border-gold/40">
          <b>בית ספר לדוגמה.</b> נתונים מומצאים, לתצוגה ולבדיקה בלבד — אין כאן שום מוסד אמיתי ואף
          חשבון של אדם אמיתי.
        </div>
      )}

      {panel.warn_80 && (
        <div className="glass rounded-2xl p-3 text-xs text-gold-soft border border-gold/50">
          המוסד ניצל מעל 80% מהמכסה היומית. שווה לבדוק את התקרות האישיות למטה — אחרי שהמכסה נגמרת
          ההתראה כבר לא עוזרת.
        </div>
      )}

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "שאלות היום", value: num(asTurns(panel.pool_used_today)), sub: `מתוך ~${num(asTurns(panel.pool_daily))}` },
          { label: "שאלות השבוע", value: num(asTurns(panel.pool_used_week)), sub: `מתוך ~${num(asTurns(panel.pool_weekly))}` },
          { label: "שיעורים השבוע", value: num(panel.lessons_used_week), sub: `מתוך ${num(panel.weekly_lessons)}` },
          { label: "ניצול היום", value: `${Math.round(panel.pool_pct_today * 100)}%`, sub: "מהמכסה היומית" },
        ].map((c) => (
          <div key={c.label} className="glass rounded-2xl p-4">
            <div className="text-[11px] text-ink/50">{c.label}</div>
            <div className="text-2xl font-bold text-tekhelet">{c.value}</div>
            <div className="text-[11px] text-ink/40">{c.sub}</div>
          </div>
        ))}
      </section>

      <section className="glass rounded-2xl p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-serif font-bold text-tekhelet">צירוף חברים</h2>
          <div className="flex gap-2">
            <button
              disabled={busy}
              onClick={() => mintCode("student")}
              className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40"
            >
              קוד לתלמידים
            </button>
            {isAdminRole && (
              <button
                disabled={busy}
                onClick={() => mintCode("teacher")}
                className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40"
              >
                קוד למורה
              </button>
            )}
          </div>
        </div>
        {code ? (
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-lg font-bold tracking-[0.2em] text-tekhelet bg-ink/5 px-3 py-2 rounded-xl">
              {code}
            </code>
            <button
              onClick={() => navigator.clipboard?.writeText(code)}
              className="text-xs px-3 py-2 rounded-xl glass text-tekhelet"
            >
              העתקה
            </button>
          </div>
        ) : null}
        <p className="text-[11px] text-ink/50 leading-relaxed">
          החבר מזין את הקוד בהגדרות שלו ומצטרף בעצמו. אנחנו לא מצרפים חשבון לפי מזהה — כדי שאף אחד
          לא יצורף בלי שביקש, וכדי שלא נחשוף מידע על חשבונות שאינם שלך.
        </p>
      </section>

      <section className="glass rounded-2xl p-4 overflow-x-auto">
        <h2 className="font-serif font-bold text-tekhelet mb-3">חברים</h2>
        <table className="w-full text-sm min-w-[560px]">
          <thead className="text-[11px] text-ink/50">
            <tr>
              <th className="text-right font-normal pb-2">מזהה</th>
              <th className="text-right font-normal pb-2">תפקיד</th>
              <th className="text-right font-normal pb-2">שאלות היום</th>
              <th className="text-right font-normal pb-2">שאלות השבוע</th>
              <th className="text-right font-normal pb-2">תקרה יומית</th>
              {isAdminRole && <th className="text-right font-normal pb-2">פעולות</th>}
            </tr>
          </thead>
          <tbody>
            {panel.members.map((m) => (
              <tr key={m.owner_id} className="border-t border-ink/10">
                <td className="py-2 font-mono text-[11px] text-ink/70">{m.owner_id}</td>
                <td className="py-2">{ROLE_HE[m.role] ?? m.role}</td>
                <td className="py-2">{num(asTurns(m.tokens_today))}</td>
                <td className="py-2">{num(asTurns(m.tokens_week))}</td>
                <td className="py-2 text-ink/60">
                  {m.daily_cap ? num(asTurns(m.daily_cap)) : "ברירת מחדל"}
                </td>
                {isAdminRole && (
                  <td className="py-2 flex gap-2">
                    <button
                      disabled={busy}
                      onClick={() => setCap(m.owner_id, m.daily_cap)}
                      className="text-[11px] px-2 py-1 rounded-lg glass text-tekhelet disabled:opacity-40"
                    >
                      תקרה
                    </button>
                    <button
                      disabled={busy || m.role === "admin"}
                      onClick={() => removeMember(m.owner_id)}
                      className="text-[11px] px-2 py-1 rounded-lg glass text-ink/60 disabled:opacity-30"
                    >
                      הסרה
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {isAdminRole && (
        <section className="glass rounded-2xl p-4">
          <h2 className="font-serif font-bold text-tekhelet mb-1">נושאי לימוד</h2>
          <p className="text-[11px] text-ink/50 mb-3">
            סוגי השימוש והיקפם. תוכן השיחות עצמן אינו נגיש לאף אחד במוסד — לא למנהל, לא למורה, ולא
            בבקשה מיוחדת.
          </p>
          {panel.topics.length ? (
            <ul className="flex flex-wrap gap-2">
              {panel.topics.map((t) => (
                <li key={t.intent} className="text-xs glass rounded-xl px-3 py-2">
                  <b className="text-tekhelet">{t.intent}</b>
                  <span className="text-ink/50"> · {num(t.requests)} פניות</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-ink/40">אין עדיין שימוש לדווח עליו.</p>
          )}
        </section>
      )}
    </div>
  );
}
