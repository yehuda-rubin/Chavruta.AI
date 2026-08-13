"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import {
  api,
  type AdminOverview,
  type AdminWindow,
  type Coupon,
  type FeedbackItem,
  type FlaggedMessage,
  type GrantResult,
  type DevHelper,
  type GuardFindings,
  type HelperFeature,
  type UsageOverTime,
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

type Section = "overview" | "inbox" | "guards" | "helpers" | "coupons";

// The sortable columns of the top-users table, and how many rows a page may hold.
type OwnerSortKey = "owner_id" | "requests" | "tokens" | "avg_ms";
const OWNER_PAGE_SIZES = [10, 20, 50, 100];

const SECTIONS: { id: Section; label: string; icon: string }[] = [
  { id: "overview", label: "סקירה", icon: "monitoring" },
  { id: "inbox", label: "משוב ודיווחים", icon: "inbox" },
  { id: "guards", label: "בקרת איכות", icon: "policy" },
  { id: "helpers", label: "עוזרי פיתוח", icon: "group" },
  { id: "coupons", label: "קופונים והרשאות", icon: "confirmation_number" },
];

// Hebrew names for the guard kinds. Kept beside the filter buttons that use the same ids, so the
// label and the query string can't drift apart.
const GUARD_LABELS: Record<string, string> = {
  misattribution: "ייחוס שגוי",
  deontic: "סתירה עצמית",
  calendar: "תאריך/דף שגוי",
};

const PLANS = [
  { id: "basic", label: "בסיסי" },
  { id: "pro", label: "מלא" },
  { id: "institution", label: "מוסדי" },
];

export default function AdminDashboard() {
  const [meLoading, setMeLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [section, setSection] = useState<Section>("overview");
  const [since, setSince] = useState<AdminWindow>("30d");

  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [byOwner, setByOwner] = useState<UsageByOwnerRow[] | null>(null);
  const [flagged, setFlagged] = useState<FlaggedMessage[] | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[] | null>(null);
  const [guards, setGuards] = useState<GuardFindings | null>(null);
  const [guardKind, setGuardKind] = useState("");
  const [spend, setSpend] = useState<UsageOverTime | null>(null);
  const [spendBucket, setSpendBucket] = useState<"day" | "week">("day");
  const [dataLoading, setDataLoading] = useState(true);
  const [error, setError] = useState(false);

  // The top-users table. Paged and sorted in the browser over one generous fetch, rather than a
  // request per page: the row count here is in the hundreds at most, and a round trip per click
  // would be slower AND would make sorting need a server change it does not otherwise need.
  const [ownerPageSize, setOwnerPageSize] = useState(20);
  const [ownerPage, setOwnerPage] = useState(0);
  const [ownerSort, setOwnerSort] = useState<OwnerSortKey>("tokens");
  const [ownerAsc, setOwnerAsc] = useState(false);

  useEffect(() => {
    api.me().then((me) => setIsAdmin(me.is_admin)).catch(() => setIsAdmin(false))
      .finally(() => setMeLoading(false));
  }, []);

  // Sorting or resizing while on page 7 would otherwise leave the reader on a page that no longer
  // holds what they were looking at — or past the end of a shorter list, staring at nothing.
  useEffect(() => setOwnerPage(0), [ownerSort, ownerAsc, ownerPageSize, since]);

  useEffect(() => {
    if (!isAdmin) return;
    setDataLoading(true);
    setError(false);
    Promise.all([
      api.admin.overview(since),
      // Fetched once, deep enough that paging has something to page through. 20 was the whole
      // table before, so there was nothing beyond the first screen to reach.
      api.admin.usageByOwner(since, 500),
      api.admin.flaggedMessages(false),
      api.admin.feedback(false),
      api.admin.guards(since, guardKind, 200),
      api.admin.usageOverTime(since, spendBucket),
    ])
      .then(([ov, owners, flags, fb, gd, sp]) => {
        setOverview(ov);
        setByOwner(owners);
        setFlagged(flags);
        setFeedback(fb);
        setGuards(gd);
        setSpend(sp);
      })
      .catch(() => setError(true))
      .finally(() => setDataLoading(false));
  }, [isAdmin, since, guardKind, spendBucket]);

  async function reviewMessage(reportId: number) {
    await api.admin.reviewMessage(reportId);
    setFlagged((cur) => (cur ? cur.filter((f) => f.id !== reportId) : cur));
  }

  async function reviewFeedback(feedbackId: number) {
    await api.admin.reviewFeedback(feedbackId);
    setFeedback((cur) => (cur ? cur.filter((f) => f.id !== feedbackId) : cur));
  }

  if (meLoading) {
    return <div className="h-dvh grid place-items-center text-ink/50 text-sm">טוען…</div>;
  }

  if (!isAdmin) {
    return (
      <div dir="rtl" className="h-dvh grid place-items-center p-4">
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

  // Totals for the spend section. Computed here rather than server-side: the rows are already
  // in hand, and a second endpoint for a sum would be a round trip for arithmetic.
  const spendTotal = (spend?.rows ?? []).reduce(
    (a, r) => ({ billed: a.billed + (r.billed ?? 0) }), { billed: 0 });
  const spendMax = Math.max(1, ...(spend?.rows ?? []).map((r) => r.billed ?? 0));
  const fmtInt = (n: number | null) => (n ?? 0).toLocaleString("he-IL");
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

  const pending = (flagged?.length ?? 0) + (feedback?.length ?? 0);

  return (
    <div dir="rtl" className="h-dvh flex flex-col lg:flex-row overflow-hidden">
      {/* Nav rail — a column on desktop, a scrollable strip above the content on mobile. */}
      <aside className="lg:w-60 shrink-0 glass lg:h-full flex lg:flex-col gap-1 p-3 overflow-x-auto lg:overflow-x-visible">
        <header className="hidden lg:flex items-center gap-2 px-2 pb-3 mb-1 border-b border-ink/10">
          <Icon name="admin_panel_settings" className="text-tekhelet text-[24px]" />
          <h1 className="font-serif text-lg font-bold text-tekhelet">פאנל ניהול</h1>
        </header>
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setSection(s.id)}
            className={
              "flex items-center gap-2 px-3 py-2.5 rounded-2xl text-sm font-semibold transition shrink-0 " +
              (section === s.id ? "grad text-white shadow-sm" : "text-ink/70 hover:bg-white/60 hover:text-tekhelet")
            }
          >
            <Icon name={s.icon} className="text-[19px]" />
            <span>{s.label}</span>
            {s.id === "inbox" && pending > 0 && (
              <span className={
                "ms-auto text-[11px] font-bold rounded-full px-1.5 py-0.5 " +
                (section === s.id ? "bg-white/25" : "bg-gold/20 text-gold")
              }>
                {pending}
              </span>
            )}
          </button>
        ))}
        {/* The operator's way into the institution panel. It is NOT a section of this page: the
            school panel is a real product screen that a school administrator sees, and the point of
            reaching it from here is to look at the actual thing rather than a copy of it that could
            drift. It opens the synthetic demo school — /orgs/panel?demo=true, gated on _is_admin
            server-side — so no real school's records are involved.

            Without this there was no route to it at all. The header button that opens /school is
            shown only to org admins and teachers, and the operator belongs to no organisation, so
            their org_role is empty and the button never appeared for them. */}
        <Link
          href="/school"
          className="lg:mt-auto flex items-center gap-2 px-3 py-2.5 rounded-2xl text-sm font-semibold text-ink/70 hover:bg-white/60 hover:text-tekhelet transition shrink-0"
        >
          <Icon name="school" className="text-[19px]" />
          <span>פאנל מוסד (לדוגמה)</span>
        </Link>
        <Link
          href="/"
          className="flex items-center gap-2 px-3 py-2.5 rounded-2xl text-sm font-semibold text-ink/60 hover:bg-white/60 hover:text-tekhelet transition shrink-0"
        >
          <Icon name="chevron_right" className="text-[19px]" />
          <span>חזרה לאפליקציה</span>
        </Link>
      </aside>

      <main className="flex-1 overflow-y-auto p-4 lg:p-8">
        <div className="max-w-4xl mx-auto flex flex-col gap-5">
          {section === "overview" && (
            <>
              <div className="flex items-center justify-between gap-3">
                <h2 className="font-serif text-2xl font-bold text-tekhelet">סקירה</h2>
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

                  {(() => {
                    const all = byOwner ?? [];
                    const dir = ownerAsc ? 1 : -1;
                    const sorted = [...all].sort((a, b) => {
                      if (ownerSort === "owner_id") {
                        return dir * (a.owner_id ?? "").localeCompare(b.owner_id ?? "");
                      }
                      return dir * ((a[ownerSort] ?? 0) - (b[ownerSort] ?? 0));
                    });
                    const pages = Math.max(1, Math.ceil(sorted.length / ownerPageSize));
                    const page = Math.min(ownerPage, pages - 1);
                    const start = page * ownerPageSize;
                    const rows = sorted.slice(start, start + ownerPageSize);
                    const cols: { key: OwnerSortKey; label: string }[] = [
                      { key: "owner_id", label: "משתמש" },
                      { key: "requests", label: "בקשות" },
                      { key: "tokens", label: "טוקנים" },
                      { key: "avg_ms", label: "זמן ממוצע (דק:שנ)" },
                    ];
                    return (
                      <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                          <h3 className="font-serif text-lg font-bold text-tekhelet">
                            משתמשים מובילים לפי שימוש
                          </h3>
                          <label className="flex items-center gap-2 text-xs text-ink/60">
                            שורות בעמוד
                            <select
                              value={ownerPageSize}
                              onChange={(e) => setOwnerPageSize(Number(e.target.value))}
                              className="glass rounded-xl px-2 py-1 text-ink/80"
                            >
                              {OWNER_PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
                            </select>
                          </label>
                        </div>

                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-ink/10">
                                {cols.map((c) => (
                                  <th key={c.key} className="py-2 px-3 text-start">
                                    <button
                                      onClick={() => {
                                        if (ownerSort === c.key) setOwnerAsc((v) => !v);
                                        else { setOwnerSort(c.key); setOwnerAsc(false); }
                                      }}
                                      className="font-semibold text-tekhelet hover:opacity-70 transition inline-flex items-center gap-1"
                                      title="מיון לפי העמודה הזו"
                                    >
                                      {c.label}
                                      <span className={ownerSort === c.key ? "text-tekhelet" : "text-ink/20"}>
                                        {ownerSort === c.key ? (ownerAsc ? "▲" : "▼") : "▽"}
                                      </span>
                                    </button>
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((row) => (
                                <tr key={row.owner_id ?? "unknown"} className="border-b border-ink/5 last:border-0">
                                  <td className="py-2 px-3 font-mono text-xs text-ink/70">{row.owner_id ?? "—"}</td>
                                  <td className="py-2 px-3 text-ink/70">{row.requests}</td>
                                  <td className="py-2 px-3 text-ink/70">{(row.tokens ?? 0).toLocaleString("he-IL")}</td>
                                  <td className="py-2 px-3 text-ink/70">{row.avg_ms ? duration(row.avg_ms) : "—"}</td>
                                </tr>
                              ))}
                              {sorted.length === 0 && (
                                <tr><td colSpan={4} className="py-3 text-center text-ink/40">אין נתונים בחלון הזה</td></tr>
                              )}
                            </tbody>
                          </table>
                        </div>

                        {sorted.length > 0 && (
                          <div className="flex items-center justify-between gap-3 flex-wrap text-xs text-ink/60">
                            <span>
                              מציג {start + 1}–{Math.min(start + ownerPageSize, sorted.length)} מתוך {sorted.length}
                            </span>
                            <div className="flex items-center gap-2">
                              <button
                                disabled={page <= 0}
                                onClick={() => setOwnerPage(page - 1)}
                                className="px-3 py-1.5 rounded-xl glass text-tekhelet font-semibold disabled:opacity-30"
                              >
                                הקודם
                              </button>
                              <span className="tabular-nums">עמוד {page + 1} מתוך {pages}</span>
                              <button
                                disabled={page >= pages - 1}
                                onClick={() => setOwnerPage(page + 1)}
                                className="px-3 py-1.5 rounded-xl glass text-tekhelet font-semibold disabled:opacity-30"
                              >
                                הבא
                              </button>
                            </div>
                          </div>
                        )}
                      </section>
                    );
                  })()}
                </>
              )}

              {/* Token spend over time. Input and output are shown SEPARATELY and on purpose: the
                  measured ratio is ~15:1 in favour of input (6,550 sent per model call against 442
                  returned), so a single "tokens" number would hide the side that both costs the most
                  and is the one that can be reduced without shortening a single answer.

                  `billed` is the normalized unit the quota is metered in (prompt + 3x completion) —
                  what a turn actually costs — so the bar is drawn from that. Money is shown only if
                  CHAVRUTA_COST_PER_M_TOKENS is set; there is no default rate, because a guessed one
                  would render an authoritative-looking figure that is not. */}
              <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <h3 className="font-serif text-lg font-bold text-tekhelet">צריכת טוקנים לאורך זמן</h3>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-ink/50">
                      סה&quot;כ {fmtInt(spendTotal.billed)} מנורמלים
                      {spend?.cost_per_m_billed
                        ? ` · ${money((spendTotal.billed / 1_000_000) * spend.cost_per_m_billed)}`
                        : ""}
                    </span>
                    <select
                      value={spendBucket}
                      onChange={(e) => setSpendBucket(e.target.value as "day" | "week")}
                      aria-label="רזולוציה"
                      className="px-2 py-1 rounded-xl glass text-xs text-ink/70 outline-none"
                    >
                      <option value="day">לפי יום</option>
                      <option value="week">לפי שבוע</option>
                    </select>
                  </div>
                </div>

                {!spend?.rows.length ? (
                  <p className="text-sm text-ink/40 text-center py-2">אין נתונים בחלון הזה.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm min-w-[560px]">
                      <thead>
                        <tr className="text-ink/45 text-xs">
                          <th className="text-right font-normal pb-2">תקופה</th>
                          <th className="text-right font-normal pb-2">בקשות</th>
                          <th className="text-right font-normal pb-2">קריאות למודל</th>
                          <th className="text-right font-normal pb-2">קלט</th>
                          <th className="text-right font-normal pb-2">פלט</th>
                          <th className="text-right font-normal pb-2">מנורמל</th>
                          <th className="text-right font-normal pb-2 w-[22%]"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {spend.rows.map((r) => (
                          <tr key={r.bucket} className="border-t border-ink/5">
                            <td className="py-1.5 text-ink/70 font-mono text-xs">{r.bucket}</td>
                            <td className="py-1.5 text-ink/60">{fmtInt(r.requests)}</td>
                            <td className="py-1.5 text-ink/60">{fmtInt(r.calls)}</td>
                            <td className="py-1.5 text-ink/70">{fmtInt(r.prompt)}</td>
                            <td className="py-1.5 text-ink/50">{fmtInt(r.completion)}</td>
                            <td className="py-1.5 text-tekhelet font-semibold">{fmtInt(r.billed)}</td>
                            <td className="py-1.5">
                              {/* A bar rather than a chart library: no dependency, and it reads at a
                                  glance which day cost what. */}
                              <span className="block h-2 rounded-full bg-tekhelet/15">
                                <span
                                  className="block h-2 rounded-full grad"
                                  style={{ width: `${spendMax ? ((r.billed ?? 0) / spendMax) * 100 : 0}%` }}
                                />
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="text-[11px] text-ink/40 leading-relaxed">
                  &quot;מנורמל&quot; = קלט + פי־3 פלט — היחידה שהמכסה נמדדת בה, ולפיה מחושבת העלות.
                  שים לב ליחס בין הקלט לפלט: הקלט הוא הצד הגדול, והיחיד שאפשר לצמצם בלי לקצר תשובה.
                </p>
              </section>
            </>
          )}

          {section === "inbox" && (
            <>
              <h2 className="font-serif text-2xl font-bold text-tekhelet">משוב ודיווחים</h2>
              <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
                <h3 className="font-serif text-lg font-bold text-tekhelet">הודעות מסומנות לבדיקה</h3>
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
                <h3 className="font-serif text-lg font-bold text-tekhelet">משוב והצעות</h3>
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

          {/* Quality control — what the watching guards caught. These checks deliberately show
              NOTHING to users (src/chavruta/generation/guards.py): none has met real traffic, and a
              warning on a correct answer spends the credit the honest ones earned. This screen is
              how that decision gets revisited on evidence: the counts say whether a guard fires at
              all, the rows say whether what it caught was worth catching. */}
          {section === "guards" && (
            <>
              <h2 className="font-serif text-2xl font-bold text-tekhelet">בקרת איכות</h2>
              <p className="text-xs text-ink/50 leading-relaxed -mt-2">
                שלוש בדיקות שרצות על כל תשובה ואינן מוצגות למשתמש. הן נאספות כאן כדי שנחליט,
                לפי מה שהן תפסו בפועל, אילו מהן ראויות להיות גלויות.
              </p>

              <div className="flex flex-wrap gap-2">
                {[
                  { id: "", label: "הכול" },
                  { id: "misattribution", label: "ייחוס שגוי" },
                  { id: "deontic", label: "סתירה עצמית" },
                  { id: "calendar", label: "תאריך/דף שגוי" },
                ].map((k) => (
                  <button
                    key={k.id}
                    onClick={() => setGuardKind(k.id)}
                    className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
                      guardKind === k.id ? "grad text-white" : "glass text-ink/70 hover:bg-ink/5"
                    }`}
                  >
                    {k.label}
                    {k.id && guards?.counts?.[k.id] ? ` (${guards.counts[k.id]})` : ""}
                  </button>
                ))}
              </div>

              <section className="glass rounded-[24px] p-5 flex flex-col gap-2">
                {(guards?.findings ?? []).map((g) => (
                  <div key={g.id} className="rounded-2xl bg-ink/5 p-3 flex flex-col gap-1.5">
                    <div className="flex items-center justify-between gap-2 text-xs text-ink/50">
                      <span className="font-semibold text-tekhelet">{GUARD_LABELS[g.kind] ?? g.kind}</span>
                      <span>{g.intent || "—"} · {new Date(g.at).toLocaleString("he-IL")}</span>
                    </div>
                    {/* Rendered per kind rather than as one shape: the three guards report genuinely
                        different things, and a shared "detail" column would be a JSON blob. */}
                    {g.kind === "misattribution" && (
                      <p className="text-sm text-ink/80 leading-relaxed">
                        יוחס ל<b>{g.detail.claimed}</b>, והטקסט הוא של <b>{g.detail.found_in}</b>
                        {/* No excerpt: guard_findings has no owner_id and so cannot honour the
                            per-chat review opt-out, which means answer text must not live in it. */}
                        {g.detail.quote_len && (
                          <span className="block text-ink/40 mt-1">ציטוט באורך {g.detail.quote_len} תווים</span>
                        )}
                      </p>
                    )}
                    {g.kind === "deontic" && (
                      <p className="text-sm text-ink/80 leading-relaxed">
                        <b>{g.detail.authority}</b>
                        {g.detail.attribution === "inherited" && (
                          <span className="text-ink/40"> (ללא ייחוס מפורש — אות חלש יותר)</span>
                        )}
                        {g.detail.verdicts && (
                          <span className="block text-ink/60 mt-1">{g.detail.verdicts}</span>
                        )}
                      </p>
                    )}
                    {g.kind === "calendar" && (
                      <p className="text-sm text-ink/80 leading-relaxed">
                        נכתב <b>{g.detail.stated}</b>, ובפועל <b>{g.detail.expected}</b>
                      </p>
                    )}
                  </div>
                ))}
                {(guards?.findings ?? []).length === 0 && (
                  <p className="text-sm text-ink/40 text-center py-2">
                    לא נמצא דבר בחלון הזה — מה שאומר או שהתשובות נקיות, או שהבדיקות שמרניות מדי.
                  </p>
                )}
              </section>
            </>
          )}

          {section === "helpers" && <HelpersSection />}

          {section === "coupons" && <CouponsSection />}
        </div>
      </main>
    </div>
  );
}

// ── Development helpers ─────────────────────────────────────────────────────
// Accounts invited to test the product (app/devhelpers.py). Inviting grants NOTHING — the person has
// to accept — so the status column is the part to read, not the row's existence.
//
// Identified by owner_id because that is the only key that exists here: the app database stores no
// email addresses at all. The overview table above is where one gets copied from.
const HELPER_STATUS_HE: Record<string, string> = {
  invited: "ממתין לאישור",
  accepted: "פעיל",
  declined: "סירב",
  revoked: "בוטל",
};

function HelpersSection() {
  const [rows, setRows] = useState<DevHelper[] | null>(null);
  const [features, setFeatures] = useState<HelperFeature[]>([]);
  const [ownerId, setOwnerId] = useState("");
  const [note, setNote] = useState("");
  const [newFeatures, setNewFeatures] = useState<string[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.admin
      .helpers()
      .then((r) => {
        setRows(r.helpers);
        setFeatures(r.features);
      })
      .catch(() => setRows([]));

  useEffect(() => {
    load();
  }, []);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    setMsg("");
    try {
      await fn();
      setMsg(ok);
      await load();
      return true;
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "הפעולה נכשלה");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];

  return (
    <>
      <h2 className="font-serif text-2xl font-bold text-tekhelet">עוזרי פיתוח</h2>
      <p className="text-xs text-ink/50 leading-relaxed -mt-2">
        חשבונות שהזמנת לעזור בבדיקת המוצר. הזמנה לבדה אינה מעניקה דבר — עד שהאדם מאשר, המכסה
        והיכולות שלו אינן משתנות. &quot;פעיל&quot; פירושו שאישר.
      </p>

      <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
        <h3 className="font-serif text-lg font-bold text-tekhelet">הזמנת עוזר</h3>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            value={ownerId}
            onChange={(e) => setOwnerId(e.target.value)}
            placeholder="מזהה חשבון (owner_id) — מהטבלה בסקירה"
            aria-label="מזהה חשבון"
            className="flex-1 px-3 py-2 rounded-2xl glass text-sm font-mono text-ink/80 outline-none"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="הערה לזיהוי (מוצגת גם לו)"
            aria-label="הערה לזיהוי"
            className="flex-1 px-3 py-2 rounded-2xl glass text-sm text-ink/80 outline-none"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {features.map((f) => (
            <label key={f.id} className="flex items-center gap-1.5 text-xs text-ink/70 cursor-pointer">
              <input
                type="checkbox"
                checked={newFeatures.includes(f.id)}
                onChange={() => setNewFeatures((c) => toggle(c, f.id))}
                className="accent-tekhelet"
              />
              {f.label_he}
            </label>
          ))}
        </div>
        <button
          disabled={busy || !ownerId.trim()}
          onClick={async () => {
            const ok = await run(
              () => api.admin.inviteHelper(ownerId.trim(), note.trim(), newFeatures),
              "ההזמנה נשלחה — היא תופיע אצלו לאישור",
            );
            if (ok) {
              setOwnerId("");
              setNote("");
              setNewFeatures([]);
            }
          }}
          className="self-start px-4 py-2 rounded-2xl grad text-white font-semibold text-sm disabled:opacity-40"
        >
          הזמן
        </button>
      </section>

      <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
        <h3 className="font-serif text-lg font-bold text-tekhelet">שליחת הודעה</h3>
        <p className="text-xs text-ink/50">
          {picked.length ? `נבחרו ${picked.length} נמענים` : "סמן נמענים ברשימה למטה"}
        </p>
        <textarea
          value={notice}
          onChange={(e) => setNotice(e.target.value)}
          rows={3}
          aria-label="תוכן ההודעה"
          placeholder="ההודעה תופיע להם בתוך האפליקציה"
          className="px-3 py-2 rounded-2xl glass text-sm text-ink/80 outline-none resize-y"
        />
        <button
          disabled={busy || !notice.trim() || !picked.length}
          onClick={async () => {
            const n = picked.length;
            const ok = await run(() => api.admin.noticeHelpers(picked, notice.trim()), `נשלח ל-${n}`);
            if (ok) {
              setNotice("");
              setPicked([]);
            }
          }}
          className="self-start px-4 py-2 rounded-2xl grad text-white font-semibold text-sm disabled:opacity-40"
        >
          שלח
        </button>
      </section>

      {msg && <p className="text-sm text-tekhelet/80">{msg}</p>}

      <section className="glass rounded-[24px] p-5 flex flex-col gap-2">
        {(rows ?? []).map((h) => (
          <div key={h.owner_id} className="rounded-2xl bg-ink/5 p-3 flex flex-col gap-2">
            <div className="flex items-start justify-between gap-2">
              <label className="flex items-start gap-2 min-w-0 cursor-pointer">
                <input
                  type="checkbox"
                  checked={picked.includes(h.owner_id)}
                  onChange={() => setPicked((c) => toggle(c, h.owner_id))}
                  aria-label={`בחר נמען ${h.note || h.owner_id}`}
                  className="accent-tekhelet mt-1"
                />
                <span className="min-w-0">
                  <span className="block text-sm text-ink/80 font-semibold truncate">
                    {h.note || "(ללא הערה)"}
                  </span>
                  <span className="block text-[11px] font-mono text-ink/40 truncate">{h.owner_id}</span>
                </span>
              </label>
              <span
                className={`text-xs font-semibold shrink-0 ${h.active ? "text-tekhelet" : "text-ink/40"}`}
              >
                {HELPER_STATUS_HE[h.status] ?? h.status}
                {!!h.unread && <span className="text-gold"> · {h.unread} לא נקראו</span>}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {features.map((f) => (
                <label key={f.id} className="flex items-center gap-1.5 text-xs text-ink/60 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={h.features.includes(f.id)}
                    onChange={() =>
                      run(
                        () => api.admin.setHelperFeatures(h.owner_id, toggle(h.features, f.id)),
                        "היכולות עודכנו",
                      )
                    }
                    className="accent-tekhelet"
                  />
                  {f.label_he}
                </label>
              ))}
              <span className="flex-1" />
              {!h.revoked_at && (
                <button
                  onClick={() => run(() => api.admin.revokeHelper(h.owner_id), "בוטל")}
                  className="px-3 py-1 rounded-full glass text-ink/60 text-xs font-semibold hover:bg-ink/5"
                >
                  בטל
                </button>
              )}
              <button
                onClick={() => {
                  if (window.confirm("להסיר לגמרי? ההודעות שנשלחו אליו יימחקו גם הן.")) {
                    run(() => api.admin.removeHelper(h.owner_id), "הוסר");
                  }
                }}
                className="px-3 py-1 rounded-full glass text-red-500 text-xs font-semibold hover:bg-red-500/10"
              >
                הסר
              </button>
            </div>
          </div>
        ))}
        {(rows ?? []).length === 0 && (
          <p className="text-sm text-ink/40 text-center py-2">אין עוזרי פיתוח עדיין.</p>
        )}
      </section>
    </>
  );
}

function CouponsSection() {
  const [list, setList] = useState<Coupon[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  // create-coupon form
  const [kind, setKind] = useState<"plan" | "credits">("plan");
  const [plan, setPlan] = useState("pro");
  const [days, setDays] = useState(30);
  const [credits, setCredits] = useState(50);
  const [code, setCode] = useState("");
  const [maxRedemptions, setMaxRedemptions] = useState(1);
  const [expiresInDays, setExpiresInDays] = useState("");
  const [note, setNote] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState("");
  const [createErr, setCreateErr] = useState("");

  // grant-to-user form
  const [grantOwner, setGrantOwner] = useState("");
  const [grantKind, setGrantKind] = useState<"plan" | "credits">("plan");
  const [grantPlan, setGrantPlan] = useState("pro");
  const [grantDays, setGrantDays] = useState(30);
  const [grantCredits, setGrantCredits] = useState(50);
  const [granting, setGranting] = useState(false);
  const [grantRes, setGrantRes] = useState<GrantResult | null>(null);
  const [grantErr, setGrantErr] = useState("");

  const reload = () =>
    api.admin.coupons().then(setList).catch(() => setLoadError(true));

  useEffect(() => { reload(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true); setCreateErr(""); setCreated("");
    try {
      const res = await api.admin.createCoupon({
        kind, plan, days, credits, code: code.trim(), max_redemptions: maxRedemptions,
        expires_in_days: expiresInDays.trim() ? Number(expiresInDays) : null,
        note: note.trim(),
      });
      setCreated(res.code);
      setCode(""); setNote("");
      await reload();
    } catch (err) {
      setCreateErr(err instanceof Error ? err.message : "יצירת הקוד נכשלה");
    } finally {
      setCreating(false);
    }
  }

  async function grant(e: React.FormEvent) {
    e.preventDefault();
    setGranting(true); setGrantErr(""); setGrantRes(null);
    try {
      const res = await api.admin.grant({
        owner_id: grantOwner.trim(), kind: grantKind, plan: grantPlan,
        days: grantDays, credits: grantCredits,
      });
      setGrantRes(res);
      await reload();
    } catch (err) {
      setGrantErr(err instanceof Error ? err.message : "ההענקה נכשלה");
    } finally {
      setGranting(false);
    }
  }

  async function remove(c: Coupon) {
    const used = c.redeemed_count > 0;
    const msg = used
      ? `הקוד ${c.code} כבר מומש ${c.redeemed_count} פעמים — הוא יבוטל (לא יימחק) וההטבות שכבר ניתנו יישארו. להמשיך?`
      : `למחוק את הקוד ${c.code}? הוא מעולם לא מומש.`;
    if (!confirm(msg)) return;
    await api.admin.deleteCoupon(c.code);
    await reload();
  }

  const field = "glass rounded-xl px-3 py-2 text-sm outline-none ring-1 ring-transparent focus:ring-tekhelet/30";

  return (
    <>
      <h2 className="font-serif text-2xl font-bold text-tekhelet">קופונים והרשאות</h2>

      <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
        <h3 className="font-serif text-lg font-bold text-tekhelet">יצירת קוד קופון</h3>
        <form onSubmit={create} className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink/55">סוג</span>
              <select value={kind} onChange={(e) => setKind(e.target.value as "plan" | "credits")} className={field}>
                <option value="plan">מנוי</option>
                <option value="credits">קרדיטים</option>
              </select>
            </label>
            {kind === "plan" ? (
              <>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-ink/55">תוכנית</span>
                  <select value={plan} onChange={(e) => setPlan(e.target.value)} className={field}>
                    {PLANS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-ink/55">ימים</span>
                  <input type="number" min={1} value={days} onChange={(e) => setDays(Number(e.target.value))}
                         className={`${field} w-24`} />
                </label>
              </>
            ) : (
              <label className="flex flex-col gap-1">
                <span className="text-xs text-ink/55">כמות קרדיטים</span>
                <input type="number" min={1} value={credits} onChange={(e) => setCredits(Number(e.target.value))}
                       className={`${field} w-28`} />
              </label>
            )}
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink/55">מימושים (0 = ללא הגבלה)</span>
              <input type="number" min={0} value={maxRedemptions}
                     onChange={(e) => setMaxRedemptions(Number(e.target.value))} className={`${field} w-24`} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink/55">תפוגה (ימים, ריק = לעולם)</span>
              <input value={expiresInDays} onChange={(e) => setExpiresInDays(e.target.value)}
                     inputMode="numeric" className={`${field} w-28`} />
            </label>
          </div>
          <div className="flex flex-wrap gap-3">
            <label className="flex flex-col gap-1 flex-1 min-w-[12rem]">
              <span className="text-xs text-ink/55">קוד מותאם (ריק = קוד אקראי)</span>
              <input value={code} onChange={(e) => setCode(e.target.value)} dir="ltr"
                     placeholder="CHV-XXXX-XXXX" className={`${field} font-mono`} />
            </label>
            <label className="flex flex-col gap-1 flex-1 min-w-[12rem]">
              <span className="text-xs text-ink/55">הערה (למה הונפק)</span>
              <input value={note} onChange={(e) => setNote(e.target.value)} className={field} />
            </label>
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={creating}
                    className="px-5 py-2.5 rounded-2xl grad text-white font-semibold text-sm hover:opacity-95 transition disabled:opacity-40">
              {creating ? "יוצר…" : "צור קוד"}
            </button>
            {created && (
              <button type="button" onClick={() => navigator.clipboard?.writeText(created)}
                      className="font-mono text-sm text-tekhelet font-bold hover:underline" dir="ltr">
                {created} 📋
              </button>
            )}
            {createErr && <span className="text-xs text-red-500">{createErr}</span>}
          </div>
        </form>
      </section>

      <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
        <h3 className="font-serif text-lg font-bold text-tekhelet">הענקה ישירה לפי מזהה משתמש</h3>
        <p className="text-xs text-ink/55 leading-relaxed">
          מנפיק קוד חד-פעמי ומממש אותו עבור המשתמש — כך ההענקה עוברת באותו מסלול בדוק שלא דורס מנוי
          פעיל בתשלום, ונשאר תיעוד מלא. המזהה מופיע למשתמש בהגדרות, מתחת לכתובת המייל.
        </p>
        <form onSubmit={grant} className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <label className="flex flex-col gap-1 flex-1 min-w-[16rem]">
              <span className="text-xs text-ink/55">מזהה משתמש (owner id)</span>
              <input value={grantOwner} onChange={(e) => setGrantOwner(e.target.value)} dir="ltr"
                     placeholder="5c70afec-c5d5-…" className={`${field} font-mono`} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-ink/55">סוג</span>
              <select value={grantKind} onChange={(e) => setGrantKind(e.target.value as "plan" | "credits")} className={field}>
                <option value="plan">מנוי</option>
                <option value="credits">קרדיטים</option>
              </select>
            </label>
            {grantKind === "plan" ? (
              <>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-ink/55">תוכנית</span>
                  <select value={grantPlan} onChange={(e) => setGrantPlan(e.target.value)} className={field}>
                    {PLANS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-ink/55">ימים</span>
                  <input type="number" min={1} value={grantDays} onChange={(e) => setGrantDays(Number(e.target.value))}
                         className={`${field} w-24`} />
                </label>
              </>
            ) : (
              <label className="flex flex-col gap-1">
                <span className="text-xs text-ink/55">כמות קרדיטים</span>
                <input type="number" min={1} value={grantCredits}
                       onChange={(e) => setGrantCredits(Number(e.target.value))} className={`${field} w-28`} />
              </label>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button type="submit" disabled={granting || !grantOwner.trim()}
                    className="px-5 py-2.5 rounded-2xl grad text-white font-semibold text-sm hover:opacity-95 transition disabled:opacity-40">
              {granting ? "מעניק…" : "הענק למשתמש"}
            </button>
            {grantRes && (
              <span className="text-xs text-tekhelet">
                בוצע ({grantRes.mode}){grantRes.plan ? ` · ${grantRes.plan}` : ""}
                {grantRes.credits_added ? ` · +${grantRes.credits_added} קרדיטים` : ""}
              </span>
            )}
            {grantErr && <span className="text-xs text-red-500">{grantErr}</span>}
          </div>
        </form>
      </section>

      <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
        <h3 className="font-serif text-lg font-bold text-tekhelet">קודים קיימים</h3>
        {loadError ? (
          <p className="text-sm text-ink/50">שגיאה בטעינת הקודים.</p>
        ) : list === null ? (
          <p className="text-sm text-ink/50">טוען…</p>
        ) : list.length === 0 ? (
          <p className="text-sm text-ink/40 text-center py-2">עוד לא הונפקו קודים.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink/10">
                  <th className="py-2 px-3 font-semibold text-tekhelet text-start">קוד</th>
                  <th className="py-2 px-3 font-semibold text-tekhelet text-start">מעניק</th>
                  <th className="py-2 px-3 font-semibold text-tekhelet text-start">מימושים</th>
                  <th className="py-2 px-3 font-semibold text-tekhelet text-start">תפוגה</th>
                  <th className="py-2 px-3 font-semibold text-tekhelet text-start">הערה</th>
                  <th className="py-2 px-3"></th>
                </tr>
              </thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.code} className="border-b border-ink/5 last:border-0">
                    <td className="py-2 px-3 font-mono text-xs" dir="ltr">
                      <span className={c.active ? "text-ink/80" : "text-ink/35 line-through"}>{c.code}</span>
                      {!c.active && <span className="ms-2 text-[11px] text-red-500">מבוטל</span>}
                    </td>
                    <td className="py-2 px-3 text-ink/70">
                      {c.kind === "credits" ? `${c.credits} קרדיטים` : `${c.plan} · ${c.days} ימים`}
                    </td>
                    <td className="py-2 px-3 text-ink/70">
                      {c.redeemed_count}/{c.max_redemptions === 0 ? "∞" : c.max_redemptions}
                    </td>
                    <td className="py-2 px-3 text-ink/70">
                      {c.expires_at ? new Date(c.expires_at).toLocaleDateString("he-IL") : "—"}
                    </td>
                    <td className="py-2 px-3 text-ink/60 max-w-[14rem] truncate">{c.note || "—"}</td>
                    <td className="py-2 px-3 text-end">
                      {c.active && (
                        <button onClick={() => remove(c)}
                                className="px-3 py-1 rounded-full glass text-xs font-semibold text-red-500 hover:bg-red-50">
                          {c.redeemed_count > 0 ? "בטל" : "מחק"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
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
