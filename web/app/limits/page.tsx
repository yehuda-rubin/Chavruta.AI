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
}

interface LimitsResponse {
  tiers: LimitTier[];
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
    <div dir={lang === "he" ? "rtl" : "ltr"} className="h-screen overflow-y-auto py-10 px-4">
      <article className="glass rounded-[28px] max-w-2xl mx-auto p-8 flex flex-col gap-5">
        <div className="flex items-center justify-between gap-3">
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold inline-flex items-center gap-1">
            <Icon name={lang === "he" ? "chevron_right" : "chevron_left"} className="text-[16px]" />
            {tr(lang, "backToApp")}
          </Link>
          <button
            onClick={() => setLang(lang === "he" ? "en" : "he")}
            className="px-3 py-1.5 rounded-full glass text-ink/70 text-xs font-semibold"
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
                      {tr(lang, "limitsTableTokensDay")}
                    </th>
                    <th className="py-2 px-3 font-semibold text-tekhelet">
                      {tr(lang, "limitsTableTokensWeek")}
                    </th>
                    <th className="py-2 px-3 font-semibold text-tekhelet">
                      {tr(lang, "limitsTableLessonsWeek")}
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
                      <td className="py-2 px-3 text-ink/70">{formatNumber(tier.daily_tokens)}</td>
                      <td className="py-2 px-3 text-ink/70">{formatNumber(tier.weekly_tokens)}</td>
                      <td className="py-2 px-3 text-ink/70">{tier.weekly_lessons}</td>
                      <td className="py-2 px-3 text-ink/70">₪{tier.price_ils}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
