"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "@/components/Icon";

interface LimitTier {
  id: string;
  name: string;
  price_ils: number;
  annual_price_ils: number;
  annual_monthly_ils: number;
  daily_tokens: number;
  weekly_tokens: number;
  weekly_lessons: number;
  monthly_credits?: number;
}

interface CreditPack {
  id: string;
  name: string;
  credits: number;
  price_ils: number;
}

interface CreditCosts {
  question: number;
  file_creation: number;
  file_creation_standard: number;
  launch_discount: boolean;
  free_monthly_credits: number;
}

interface LimitsResponse {
  tiers: LimitTier[];
  credit_packs?: CreditPack[];
  credit_costs?: CreditCosts;
}

// No `metadata` export here: this is a Client Component (needs useState/useEffect for the live
// lang toggle + limits fetch), and Next.js only resolves `metadata` on Server Components — exporting
// it from a "use client" file fails the production build outright (found 2026-07-30 while building
// after unrelated changes elsewhere).
export default function Limits() {
  const [lang, setLang] = useState<Lang>("he");
  const [data, setData] = useState<LimitsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const sp = new URLSearchParams(window.location.search);
      const q = sp.get("lang");
      if (q === "en" || q === "he") {
        setLang(q);
        return;
      }
      const saved = localStorage.getItem("chavruta-lang");
      if (saved === "en" || saved === "he") {
        setLang(saved);
      }
    } catch {}
  }, []);

  const toggleLang = () => {
    const next = lang === "he" ? "en" : "he";
    setLang(next);
    try {
      localStorage.setItem("chavruta-lang", next);
    } catch {}
  };

  useEffect(() => {
    async function fetchLimits() {
      try {
        const res = await fetch(`/billing/limits?lang=${lang}`);
        if (res.ok) {
          const json = await res.json();
          setData(json);
        }
      } catch (e) {
        console.error("Failed to fetch limits:", e);
      } finally {
        setLoading(false);
      }
    }
    fetchLimits();
  }, [lang]);

  const formatNumber = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
    return n.toString();
  };

  return (
    <div dir={lang === "he" ? "rtl" : "ltr"} className="h-dvh overflow-y-auto py-10 px-4">
      <article className="glass rounded-[28px] max-w-2xl mx-auto p-8 flex flex-col gap-5">
        <div className="flex items-center justify-between gap-3">
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold inline-flex items-center gap-1">
            <Icon name={lang === "he" ? "chevron_right" : "chevron_left"} className="text-[16px]" />
            {tr(lang, "backToApp")}
          </Link>
          <button
            onClick={toggleLang}
            className="px-3 py-1.5 rounded-full glass text-ink/70 text-xs font-semibold hover:text-tekhelet transition cursor-pointer"
          >
            עברית · EN
          </button>
        </div>

        <header className="flex flex-col gap-1">
          <h1 className="font-serif text-3xl font-bold text-tekhelet">
            {tr(lang, "limitsTitle")}
          </h1>
          <p className="text-sm text-ink/70 leading-relaxed">
            {tr(lang, "limitsSubtitle")}
          </p>
        </header>

        {loading ? (
          <p className="text-sm text-ink/50">{lang === "he" ? "טוען…" : "Loading…"}</p>
        ) : data ? (
          <div className="flex flex-col gap-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-ink/10">
                    <th className="py-2 px-3 font-semibold text-tekhelet">
                      {tr(lang, "limitsTablePlan")}
                    </th>
                    <th className="py-2 px-3 font-semibold text-tekhelet">
                      {lang === "he" ? "קרדיטים לחודש" : "Monthly credits"}
                    </th>
                    <th className="py-2 px-3 font-semibold text-tekhelet">
                      {tr(lang, "limitsTableTokensDay")}
                    </th>
                    <th className="py-2 px-3 font-semibold text-tekhelet">
                      {tr(lang, "limitsTableTokensWeek")}
                    </th>
                    <th className="py-2 px-3 font-semibold text-tekhelet">
                      {tr(lang, "limitsTableMonthly")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.tiers.map((tier) => (
                    <tr key={tier.id} className="border-b border-ink/5 last:border-0">
                      <td className="py-2 px-3 font-medium">{tier.name}</td>
                      <td className="py-2 px-3 text-ink/70">{tier.monthly_credits ?? (tier.id === "free" ? 20 : "—")}</td>
                      <td className="py-2 px-3 text-ink/70">{formatNumber(tier.daily_tokens)}</td>
                      <td className="py-2 px-3 text-ink/70">{formatNumber(tier.weekly_tokens)}</td>
                      <td className="py-2 px-3 text-ink/70">₪{tier.price_ils}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {data.credit_packs && data.credit_packs.length > 0 && (
              <div className="flex flex-col gap-2 pt-2 border-t border-ink/10">
                <h2 className="font-semibold text-tekhelet text-base">
                  {tr(lang, "creditPacksHeading")}
                </h2>
                <p className="text-xs text-ink/70">
                  {tr(lang, "creditPacksSub")}
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-1">
                  {data.credit_packs.map((pack) => (
                    <div key={pack.id} className="p-3 rounded-2xl border border-ink/10 bg-white/40 flex flex-col gap-1 text-center">
                      <span className="font-semibold text-sm text-ink">{pack.name}</span>
                      <span className="text-xs text-tekhelet font-medium">{pack.credits} {tr(lang, "creditsLabel")}</span>
                      <span className="text-sm font-bold text-ink/80 mt-1">₪{pack.price_ils}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="p-3.5 rounded-2xl bg-tekhelet/[0.04] border border-tekhelet/15 flex flex-col gap-1.5 text-xs text-ink/80 leading-relaxed">
              <span className="font-semibold text-tekhelet text-sm">
                {lang === "he" ? "שיטת הקרדיטים והאיפוס החודשי" : "Credits and Reset Policy"}
              </span>
              <p>{tr(lang, "creditCostExplainer")}</p>
              <p>
                {lang === "he"
                  ? "• מכסת 20 הקרדיטים החינמיים מתאפסת בכל חודש בתאריך פתיחת החשבון (Rolling Month), ולא ב-1 לחודש הקלנדרי."
                  : "• The 20 free monthly credits reset each month on the anniversary date of account opening, not on the 1st of the calendar month."}
              </p>
            </div>

            <section className="flex flex-col gap-2 text-sm text-ink/70 leading-relaxed">
              <p>{tr(lang, "limitsExplainer1")}</p>
              <p>{tr(lang, "limitsExplainer2")}</p>
            </section>
          </div>
        ) : (
          <p className="text-sm text-ink/50">
            {lang === "he" ? "שגיאה בטעינת המכסות." : "Failed to load limits."}
          </p>
        )}
      </article>
    </div>
  );
}
