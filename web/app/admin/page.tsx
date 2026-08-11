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

type Section = "overview" | "inbox" | "coupons";

const SECTIONS: { id: Section; label: string; icon: string }[] = [
  { id: "overview", label: "סקירה", icon: "monitoring" },
  { id: "inbox", label: "משוב ודיווחים", icon: "inbox" },
  { id: "coupons", label: "קופונים והרשאות", icon: "confirmation_number" },
];

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
        <Link
          href="/"
          className="lg:mt-auto flex items-center gap-2 px-3 py-2.5 rounded-2xl text-sm font-semibold text-ink/60 hover:bg-white/60 hover:text-tekhelet transition shrink-0"
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

                  <section className="glass rounded-[24px] p-5 flex flex-col gap-3">
                    <h3 className="font-serif text-lg font-bold text-tekhelet">משתמשים מובילים לפי שימוש</h3>
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
                </>
              )}
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

          {section === "coupons" && <CouponsSection />}
        </div>
      </main>
    </div>
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
