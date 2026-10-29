"use client";
import { useState } from "react";
import Link from "next/link";
import type { Tier, CreditPack } from "@/lib/api";
import { tr } from "@/lib/i18n";
import type { Lang } from "@/lib/types";
import { Modal } from "./Modal";

// Same address used by SupportModal and Blocked — one contact channel, not a new one per feature.
const CONTACT_EMAIL = "partners@chavrutaai.org";

export function PlansModal({
  open,
  lang,
  tiers,
  creditPacks,
  currentPlan,
  credits,
  onClose,
  onChoose,
}: {
  open: boolean;
  lang: Lang;
  tiers: Tier[];
  creditPacks?: CreditPack[];
  currentPlan?: string;
  credits?: number;
  onClose: () => void;
  onChoose: (plan: string, cycle: "monthly" | "annual") => void;
}) {
  const [cycle, setCycle] = useState<"monthly" | "annual">("monthly");
  // Institutional tiers (seats > 1) carry price_ils === null — contact-us pricing, not a published
  // number. See app/plans.py::public_catalogue. They never enter the priced grid or the saving-%
  // calculation below.
  const paid = tiers.filter((t) => t.seats === 1 && (t.price_ils ?? 0) > 0);
  const institutional = tiers.filter((t) => t.seats > 1);
  const free = tiers.find((t) => t.seats === 1 && t.price_ils === 0);
  const bestSaving = Math.max(0, ...paid.map((t) => t.annual_saving_pct));

  const packs = creditPacks || [
    { id: "entry", credits: 50, price_ils: 19.0, name: lang === "he" ? "כרטיסיית כניסה" : "Entry Pass" },
    { id: "learner", credits: 120, price_ils: 39.0, name: lang === "he" ? "כרטיסיית לומד" : "Learner Pass" },
    { id: "researcher", credits: 280, price_ils: 79.0, name: lang === "he" ? "כרטיסיית חוקר" : "Researcher Pass" },
  ];

  return (
    <Modal open={open} title={tr(lang, "plansHeading")} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto">
        {/* Subscriptions heading & Monthly / annual switch */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-ink">
              {lang === "he" ? "מנויים חודשיים ושנתיים" : "Monthly & Annual Subscriptions"}
            </h3>
            <div className="flex items-center gap-1 p-1 rounded-2xl glass">
              {(["monthly", "annual"] as const).map((c) => (
                <button
                  key={c}
                  onClick={() => setCycle(c)}
                  aria-pressed={cycle === c}
                  className={
                    "px-3 py-1 rounded-xl text-xs font-semibold transition " +
                    (cycle === c ? "grad text-white" : "text-ink/70 hover:bg-ink/5")
                  }
                >
                  {tr(lang, c === "monthly" ? "cycleMonthly" : "cycleAnnual")}
                  {c === "annual" && bestSaving > 0 && (
                    <span className="ms-1 text-[10px] opacity-90">−{bestSaving}%</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>

        {cycle === "annual" && (
          <p className="text-xs text-ink/60 text-center leading-relaxed">
            {tr(lang, "annualNote")}
          </p>
        )}

        {/* The 2 personal subscription tiers */}
        <div className="grid gap-3 sm:grid-cols-2">
          {paid.map((t) => {
            const isCurrent = t.id === currentPlan;
            const price = (cycle === "annual" ? t.annual_monthly_ils : t.price_ils) ?? 0;
            const annualTotal = t.annual_price_ils ?? 0;
            return (
              <div
                key={t.id}
                className={
                  "flex flex-col gap-2 p-4 rounded-2xl glass ring-1 " +
                  (isCurrent ? "ring-brand/40 shadow-sm" : "ring-ink/10 hover:ring-tekhelet/30")
                }
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-base text-ink">{t.name}</h3>
                  {t.monthly_credits ? (
                    <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-tekhelet/10 text-tekhelet">
                      {t.monthly_credits} {tr(lang, "creditsLabel")}/{lang === "he" ? "חודש" : "mo"}
                    </span>
                  ) : null}
                </div>
                <p className="text-2xl font-bold text-ink">
                  ₪{price}
                  <span className="text-xs font-normal text-ink/50 ms-1">
                    / {tr(lang, "perMonth")}
                  </span>
                </p>
                {cycle === "annual" && (
                  <p className="text-xs text-ink/50">
                    ₪{annualTotal} {tr(lang, "perYear")}
                  </p>
                )}
                <ul className="text-xs text-ink/70 flex flex-col gap-1.5 mt-1">
                  <li>{tr(lang, "timesUsage").replace("{n}", String(t.multiple))}</li>
                  <li className="text-[11px] text-ink/60">
                    {lang === "he" ? "כולל צבירת קרדיטים חודשית שמתחדשת מדי חודש" : "Includes monthly credit refresh"}
                  </li>
                </ul>
                <button
                  onClick={() => onChoose(t.id, cycle)}
                  disabled={isCurrent}
                  className="mt-3 px-4 py-2 rounded-2xl grad text-white font-semibold text-sm
                             hover:opacity-95 transition disabled:opacity-40"
                >
                  {isCurrent ? tr(lang, "currentPlan") : tr(lang, "choosePlan")}
                </button>
              </div>
            );
          })}
        </div>

        {free && (
          <p className="text-xs text-ink/50 text-center">{tr(lang, "freeBaseline")}</p>
        )}

        <hr className="border-ink/10 my-1" />

        {/* Credit Passes section */}
        <div className="flex flex-col gap-2">
          <div>
            <h3 className="font-bold text-sm text-ink">{tr(lang, "creditPacksHeading")}</h3>
            <p className="text-xs text-ink/60">{tr(lang, "creditPacksSub")}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {packs.filter((p) => !p.is_institutional).map((p) => (
              <div
                key={p.id}
                className="flex flex-col gap-2 p-3.5 rounded-2xl glass ring-1 ring-emerald-500/20 hover:ring-emerald-500/40 transition"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm">{p.name}</span>
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-800 dark:text-emerald-300">
                    {p.credits} {tr(lang, "creditsLabel")}
                  </span>
                </div>
                <p className="text-xl font-bold">
                  ₪{p.price_ils}
                  <span className="text-xs font-normal text-ink/50 ms-1">
                    ({(p.price_ils / p.credits).toFixed(2)} ₪/{tr(lang, "creditsLabel")})
                  </span>
                </p>
                <p className="text-[11px] text-ink/60">
                  {lang === "he" ? "ללא הגבלת זמן · צבירה לחשבון" : "No expiration · Rollover"}
                </p>
                <button
                  onClick={() => onChoose(`pack_${p.id}`, "monthly")}
                  className="mt-auto px-3 py-1.5 rounded-xl border border-emerald-600/30 text-emerald-800 dark:text-emerald-300 font-semibold text-xs hover:bg-emerald-500/10 transition"
                >
                  {tr(lang, "choosePlan")}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Credit costs banner */}
        <div className="p-3 rounded-2xl glass border border-amber-500/20 bg-amber-500/5 text-xs text-ink/80 flex flex-col gap-1 leading-relaxed">
          <p className="font-semibold text-amber-900 dark:text-amber-200">
            {tr(lang, "freeMonthlyNote")}
          </p>
          <p className="text-ink/70">
            {tr(lang, "creditCostExplainer")}
          </p>
        </div>

        {/* Institutional tiers never show a price — see app/plans.py::public_catalogue for why a
            published number here would be a mistake, not just a design choice. */}
        {institutional.length > 0 && (
          <div className="flex flex-col gap-2 p-4 rounded-2xl glass ring-1 ring-transparent text-center">
            <h3 className="font-semibold">{tr(lang, "institutionHeading")}</h3>
            <p className="text-xs text-ink/70 leading-relaxed">{tr(lang, "institutionNote")}</p>
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              dir="ltr"
              className="mt-2 self-center px-4 py-2 rounded-2xl grad text-white font-semibold text-sm
                         hover:opacity-95 transition"
            >
              {tr(lang, "institutionCta")}
            </a>
          </div>
        )}

        <p className="text-xs text-ink/50 leading-relaxed">{tr(lang, "quotaExplainer")}</p>

        <Link
          href="/limits"
          className="text-xs text-tekhelet/80 hover:text-tekhelet text-center block"
        >
          {tr(lang, "limitsLink")}
        </Link>
      </div>
    </Modal>
  );
}
