"use client";

import { useState } from "react";
import Link from "next/link";
import type { Lang, SearchHit } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { CATEGORY_LABELS } from "@/lib/search";
import { Icon } from "@/components/Icon";

const LICENSE_LABEL: Record<Lang, Record<string, string>> = {
  he: {
    "public domain": "נחלת הכלל",
    "public domain mark": "נחלת הכלל",
    cc0: "CC0 (ויתור על זכויות)",
  },
  en: {
    "public domain": "Public Domain",
    "public domain mark": "Public Domain",
    cc0: "CC0 (public domain dedication)",
  },
};

function formatLicense(lic: string | null | undefined, lang: Lang): string {
  if (!lic) return "";
  const trimmed = lic.trim();
  return LICENSE_LABEL[lang]?.[trimmed.toLowerCase()] ?? trimmed;
}

export interface ResultCardProps {
  hit: SearchHit;
  lang: Lang;
}

export function ResultCard({ hit, lang }: { hit: SearchHit; lang: Lang }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const categoryName = CATEGORY_LABELS[lang]?.[hit.work_id] || hit.work_id;
  const license = hit.license_he || hit.license_en || "";
  const version = hit.version_he || hit.version_en || "";

  return (
    <article className="glass rounded-2xl p-5 sm:p-6 transition-all duration-200 hover:shadow-md hover:shadow-tekhelet/5 flex flex-col gap-3">
      {/* Header: Ref + Book/Author + Category Badge */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex flex-col">
          <h2 className="font-serif text-xl sm:text-2xl font-bold text-tekhelet leading-snug">
            {hit.ref}
          </h2>
          {(hit.author_he || hit.book) && (
            <p className="text-sm text-ink/70 font-medium">
              {hit.author_he || hit.book}
              {hit.category_path && (
                <span className="text-ink/40 text-xs mr-2 ml-2">
                  ({hit.category_path})
                </span>
              )}
            </p>
          )}
        </div>

        {categoryName && (
          <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-gold/10 text-gold border border-gold/20 shrink-0">
            {categoryName}
          </span>
        )}
      </div>

      {/* Snippet Preview with Highlighted Mark Tags */}
      <div
        className="font-serif text-base sm:text-lg text-ink/90 leading-relaxed search-snippet"
        dangerouslySetInnerHTML={{ __html: hit.snippet }}
      />

      {/* Attribution / License Metadata */}
      {(license || version) && (
        <div className="flex items-center gap-2 text-xs text-ink/50 pt-1 border-t border-line/50">
          <Icon name="description" className="text-[14px] text-ink/40" />
          <span className="truncate">
            {license ? formatLicense(license, lang) : ""}
            {license && version ? " · " : ""}
            {version ? version : ""}
          </span>
        </div>
      )}

      {/* Action Buttons: Read in Context & Ask Chavruta */}
      {(() => {
        const readUrl = `/search/read/${encodeURIComponent(hit.ref || "")}`;
        const askUrl = `/?ask_source=${encodeURIComponent(hit.ref || "")}`;

        return (
          <div className="flex items-center justify-between gap-2.5 flex-wrap pt-2 border-t border-line/50">
            <div className="flex items-center gap-2 flex-wrap">
              <Link
                href={readUrl}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold glass text-tekhelet hover:bg-tekhelet/10 transition border border-line/60"
                title={lang === "he" ? "פתח ספר וקרא בהקשר מלא" : "Open book and read in full context"}
              >
                <Icon name="auto_stories" className="text-[16px] text-tekhelet" />
                <span>{lang === "he" ? "📖 פתח ספר / קרא בהקשר מלא" : "📖 Open book / Read in context"}</span>
              </Link>

              <Link
                href={askUrl}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold glass text-tekhelet hover:bg-gold/15 transition border border-line/60"
                title={lang === "he" ? "שאל את חברותא על מקור זה" : "Ask Chavruta about this source"}
              >
                <Icon name="smart_toy" className="text-[16px] text-gold" />
                <span>{lang === "he" ? "🤖 שאל את חברותא על מקור זה" : "🤖 Ask Chavruta about this source"}</span>
              </Link>
            </div>

            {/* Expand / Collapse Button */}
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-indigo hover:text-tekhelet transition cursor-pointer py-1.5"
            >
              <Icon
                name={isExpanded ? "expand_less" : "expand_more"}
                className="text-[18px]"
              />
              {isExpanded ? tr(lang, "collapseFullText") : tr(lang, "expandFullText")}
            </button>
          </div>
        );
      })()}

      {/* Expanded Accordion: Full Hebrew and English Text */}
      {isExpanded && (
        <div className="mt-2 pt-4 border-t border-line/60 flex flex-col gap-4 animate-in fade-in duration-200">
          {hit.text_he && (
            <div className="flex flex-col gap-1.5" dir="rtl">
              <span className="text-xs font-bold text-tekhelet uppercase tracking-wide">
                {tr(lang, "hebrewText")}
              </span>
              <div className="font-serif text-lg leading-relaxed text-ink/95 bg-white/40 p-4 rounded-xl ring-1 ring-line/50 whitespace-pre-wrap selection:bg-gold/20">
                {hit.text_he}
              </div>
            </div>
          )}

          {hit.text_en && (
            <div className="flex flex-col gap-1.5" dir="ltr">
              <span className="text-xs font-bold text-tekhelet uppercase tracking-wide">
                {tr(lang, "englishText")}
              </span>
              <div className="font-serif text-base sm:text-lg leading-relaxed text-ink/80 bg-white/40 p-4 rounded-xl ring-1 ring-line/50 whitespace-pre-wrap">
                {hit.text_en}
              </div>
            </div>
          )}

          {/* Full Editions and Licenses Details when expanded */}
          <div className="text-[11px] text-ink/50 flex flex-col gap-1 pt-2 border-t border-line/40">
            {hit.version_he && (
              <div>
                <strong>{tr(lang, "sourceEdition")} (עברית):</strong> {hit.version_he}{" "}
                {hit.license_he && `(${formatLicense(hit.license_he, lang)})`}
              </div>
            )}
            {hit.version_en && (
              <div>
                <strong>{tr(lang, "sourceEdition")} (English):</strong> {hit.version_en}{" "}
                {hit.license_en && `(${formatLicense(hit.license_en, lang)})`}
              </div>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
