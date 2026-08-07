"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import {
  api,
  type AdminOverview,
  type AdminWindow,
  type FeedbackItem,
  type FlaggedMessage,
  type UsageByOwnerRow,
} from "@/lib/api";

// No `metadata` export here — same reason as limits/page.tsx: this is a Client Component (needs
// useState/useEffect for the data fetch + window toggle), and Next only resolves `metadata` on
// Server Components. There's no SEO upside to one here anyway — this route is disallowed from
// indexing (see robots.ts) and was never meant to be found, only reached directly.
//
// The real protection is server-side: every /admin/* call 404s for a non-admin owner regardless of
// what this page renders (see app/api.py::_require_admin). The gate below is UX only — showing a
// plain "not authorized" instead of a broken dashboard to someone who typed the URL without access.
export default function AdminDashboard() {
  const [meLoading, setMeLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [since, setSince] = useState<AdminWindow>("30d");

  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [byOwner, setByOwner] = useState<UsageByOwnerRow[] | null>(null);
  const [flagged, setFlagged] = useState<FlaggedMessage[] | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[] | null>(null);
  const [dataLoading, setDataLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.me().then((me) => setIsAdmin(me.is_admin)).catch(() => setIsAdmin(false))
      .finally(() => setMeLoading(false));
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    setDataLoading(true);
    setError(false);
    Promise.all([
      api.admin.overview(since),
      api.admin.usageByOwner(since, 20),
      api.admin.flaggedMessages(false),
      api.admin.feedback(false),
    ])
      .then(([ov, owners, flags, fb]) => {
        setOverview(ov);
        setByOwner(owners);
        setFlagged(flags);
        setFeedback(fb);
      })
      .catch(() => setError(true))
      .finally(() => setDataLoading(false));
  }, [isAdmin, since]);

  async function reviewMessage(reportId: number) {
    await api.admin.reviewMessage(reportId);
    setFlagged((cur) => (cur ? cur.filter((f) => f.id !== reportId) : cur));
  }

  async function reviewFeedback(feedbackId: number) {
    await api.admin.reviewFeedback(feedbackId);
    setFeedback((cur) => (cur ? cur.filter((f) => f.id !== feedbackId) : cur));
  }

  if (meLoading) {
    return <div className="h-screen grid place-items-center text-ink/50 text-sm">טוען…</div>;
  }

  if (!isAdmin) {
    return (
      <div dir="rtl" className="h-screen grid place-items-center p-4">
        <div className="glass rounded-[28px] p-8 max-w-sm text-center flex flex-col gap-3">
          <h1 className="font-serif text-xl font-bold text-tekhelet">אין הרשאה</h1>
          <p className="text-sm text-ink/60">העמוד הזה זמין רק לחשבון המנהל.</p>
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            חזרה לאפליקציה
          </Link>
        </div>
      </div>
    );
  }

  const money = (n: number) => `₪${n.toLocaleString("he-IL", { maximumFractionDigits: 0 })}`;
  // Request latency as minutes:seconds — a raw "3233ms" makes people do the division in their
  // head; most requests here are single-digit seconds, so this reads as "0:03" rather than "0
  // minutes" (which a plain-minutes display would round down to for nearly everything).
  const duration = (ms: number) => {
    const totalSeconds = Math.round(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  };

  return (
    <div dir="rtl" className="h-screen overflow-y-auto py-10 px-4">
      <div className="max-w-4xl mx-auto flex flex-col gap-5">
        <div className="flex items-center justify-between gap-3">
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold inline-flex items-center gap-1">
            <Icon name="chevron_right" className="text-[16px]" />
            חזרה לאפליקציה
          </Link>
          <div className="flex items-center gap-1 glass rounded-full p-1">
            {(["7d", "30d", "all"] as AdminWindow[]).map((w) => (
              <button
                key={w}
                onClick={() => setSince(w)}
                className={
                  "px-3 py-1 rounded-full text-xs font-semibold transition " +
                  (since === w ? "grad text-white" : "text-ink/60 hover:text-tekhelet")
                }
              >
                {w === "7d" ? "7 ימים" : w === "30d" ? "30 יום" : "הכל"}
              </button>
            ))}
          </div>
        </div>

        <header className="flex items-center gap-2">
          <Icon name="admin_panel_settings" className="text-tekhelet text-[26px]" />
          <h1 className="font-serif text-2xl font-bold text-tekhelet">דשבורד ניהול</h1>
        </header>

        {dataLoading ? (
          <p className="text-sm text-ink/50">טוען נתונים…</p>
        ) : error || !overview ? (
          <p className="text-sm text-ink/50">שגיאה בטעינת הנתונים.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Card label="חשבונות" value={String(overview.accounts.total)} />
              <Card label="בקשות" value={String(overview.usage.requests ?? 0)} />
              <Card label="שגיאות" value={String(overview.usage.errors ?? 0)} tone={
                (overview.usage.errors ?? 0) > 0 ? "warn" : undefined
              } />
              <Card label="משתמשים פעילים" value={String(overview.usage.users ?? 0)} />
              <Card
                label="מבוסס-מקורות"
                value={
                  overview.usage.requests
                    ? `${Math.round(100 * (overview.usage.grounded ?? 0) / overview.usage.requests)}%`
                    : "—"
                }
              />
              <Card label="זמן ממוצע (דק:שנ)" value={overview.usage.avg_ms ? duration(overview.usage.avg_ms) : "—"} />
              <Card label="שיא מקבילות" value={String(overview.concurrency.peak ?? 0)} />
              <Card label="הכנסות" value={money(overview.revenue.totals.ILS ?? 0)} />
            </div>

            <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
              <h2 className="font-serif text-lg font-bold text-tekhelet">משתמשים מובילים לפי שימוש</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-ink/10">
                      <th className="py-2 px-3 font-semibold text-tekhelet text-start">משתמש</th>
                      <th className="py-2 px-3 font-semibold text-tekhelet text-start">בקשות</th>
                      <th className="py-2 px-3 font-semibold text-tekhelet text-start">טוקנים</th>
                      <th className="py-2 px-3 font-semibold text-tekhelet text-start">זמן ממוצע (דק:שנ)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(byOwner ?? []).map((row) => (
                      <tr key={row.owner_id ?? "unknown"} className="border-b border-ink/5 last:border-0">
                        <td className="py-2 px-3 font-mono text-xs text-ink/70">{row.owner_id ?? "—"}</td>
                        <td className="py-2 px-3 text-ink/70">{row.requests}</td>
                        <td className="py-2 px-3 text-ink/70">{row.tokens ?? 0}</td>
                        <td className="py-2 px-3 text-ink/70">{row.avg_ms ? duration(row.avg_ms) : "—"}</td>
                      </tr>
                    ))}
                    {(byOwner ?? []).length === 0 && (
                      <tr><td colSpan={4} className="py-3 text-center text-ink/40">אין נתונים בחלון הזה</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
              <h2 className="font-serif text-lg font-bold text-tekhelet">הודעות מסומנות לבדיקה</h2>
              <div className="flex flex-col gap-2">
                {(flagged ?? []).map((f) => (
                  <div key={f.id} className="rounded-2xl bg-ink/5 p-3 flex flex-col gap-1.5">
                    <div className="flex items-center justify-between gap-2 text-xs text-ink/50">
                      <span>{f.reason || "(ללא סיבה)"} · {f.source === "auto" ? "אוטומטי" : "משתמש"}</span>
                      <button
                        onClick={() => reviewMessage(f.id)}
                        className="px-3 py-1 rounded-full glass text-tekhelet text-xs font-semibold hover:bg-tekhelet/10"
                      >
                        סומן כנבדק
                      </button>
                    </div>
                    <p className="text-sm text-ink/80 line-clamp-3">{f.text}</p>
                  </div>
                ))}
                {(flagged ?? []).length === 0 && (
                  <p className="text-sm text-ink/40 text-center py-2">אין הודעות ממתינות לבדיקה 🎉</p>
                )}
              </div>
            </section>

            <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
              <h2 className="font-serif text-lg font-bold text-tekhelet">משוב והצעות</h2>
              <div className="flex flex-col gap-2">
                {(feedback ?? []).map((f) => (
                  <div key={f.id} className="rounded-2xl bg-ink/5 p-3 flex flex-col gap-1.5">
                    <div className="flex items-center justify-between gap-2 text-xs text-ink/50">
                      <span>{f.owner_id} · {new Date(f.created_at).toLocaleString("he-IL")}</span>
                      <button
                        onClick={() => reviewFeedback(f.id)}
                        className="px-3 py-1 rounded-full glass text-tekhelet text-xs font-semibold hover:bg-tekhelet/10"
                      >
                        סומן כנבדק
                      </button>
                    </div>
                    <p className="text-sm text-ink/80 whitespace-pre-line">{f.text}</p>
                  </div>
                ))}
                {(feedback ?? []).length === 0 && (
                  <p className="text-sm text-ink/40 text-center py-2">אין משוב ממתין לבדיקה 🎉</p>
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function Card({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="glass rounded-2xl p-4 flex flex-col gap-1">
      <span className="text-xs text-ink/50">{label}</span>
      <span className={"text-xl font-bold " + (tone === "warn" ? "text-red-500" : "text-tekhelet")}>
        {value}
      </span>
    </div>
  );
}
