"use client";
import { useState } from "react";
import Link from "next/link";
import type { Tier } from "@/lib/api";
import { tr } from "@/lib/i18n";
import type { Lang } from "@/lib/types";
import { Modal } from "./Modal";

// Same address used by SupportModal and Blocked — one contact channel, not a new one per feature.
const CONTACT_EMAIL = "rubinyehuda8@gmail.com";

/**
 * Plan picker. Shows both usage caps, not just the price — the daily one is what a user feels day
 * to day, and the weekly one is the number that actually decides whether a plan fits them, so
 * hiding it until they hit it would be a nasty surprise rather than a limit they chose.
 *
 * No tier is unlimited, and the UI never implies otherwise.
 */
export function PlansModal({
  open,
  lang,
  tiers,
  currentPlan,
  onClose,
  onChoose,
}: {
  open: boolean;
  lang: Lang;
  tiers: Tier[];
  currentPlan?: string;
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

  return (
    <Modal open={open} title={tr(lang, "plansHeading")} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto">
        {/* Monthly / annual switch — the discount is stated, not implied. */}
        <div className="flex items-center justify-center gap-1 p-1 rounded-2xl glass self-center">
          {(["monthly", "annual"] as const).map((c) => (
            <button
              key={c}
              onClick={() => setCycle(c)}
              aria-pressed={cycle === c}
              className={
                "px-4 py-2 rounded-xl text-sm font-semibold transition " +
                (cycle === c ? "grad text-white" : "text-ink/70 hover:bg-ink/5")
              }
            >
              {tr(lang, c === "monthly" ? "cycleMonthly" : "cycleAnnual")}
              {c === "annual" && bestSaving > 0 && (
                <span className="ms-1 text-[11px] opacity-90">−{bestSaving}%</span>
              )}
            </button>
          ))}
        </div>

        {cycle === "annual" && (
          <p className="text-xs text-ink/60 text-center leading-relaxed">
            {tr(lang, "annualNote")}
          </p>
        )}

        <div className="grid gap-3 sm:grid-cols-3">
          {paid.map((t) => {
            const isCurrent = t.id === currentPlan;
            // Non-null: `paid` already filtered out institutional (contact-us / null-price) tiers.
            const price = (cycle === "annual" ? t.annual_monthly_ils : t.price_ils) ?? 0;
            const annualTotal = t.annual_price_ils ?? 0;
            return (
              <div
                key={t.id}
                className={
                  "flex flex-col gap-2 p-4 rounded-2xl glass ring-1 " +
                  (isCurrent ? "ring-brand/40" : "ring-transparent")
                }
              >
                <h3 className="font-semibold">{t.name}</h3>
                <p className="text-2xl font-bold">
                  ₪{price}
                  <span className="text-xs font-normal text-ink/50">
                    {" "}
                    / {tr(lang, "perMonth")}
                  </span>
                </p>
                {cycle === "annual" && (
                  <p className="text-xs text-ink/50">
                    ₪{annualTotal} {tr(lang, "perYear")}
                  </p>
                )}
                {/* A ratio, never a token or lesson count. See app/plans.py public_catalogue. */}
                <ul className="text-xs text-ink/70 flex flex-col gap-1 mt-1">
                  <li>{tr(lang, "timesUsage").replace("{n}", String(t.multiple))}</li>
                  <li>{tr(lang, "timesLessons").replace("{n}", String(t.multiple))}</li>
                </ul>
                <button
                  onClick={() => onChoose(t.id, cycle)}
                  disabled={isCurrent}
                  className="mt-auto px-4 py-2 rounded-2xl grad text-white font-semibold text-sm
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
