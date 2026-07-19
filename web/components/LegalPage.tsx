"use client";
import { useState } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import {
  termsSections, privacySections,
  TERMS_VERSION, TERMS_EFFECTIVE, PRIVACY_VERSION, PRIVACY_EFFECTIVE,
} from "@/lib/legal";
import { Icon } from "./Icon";

// Full-page renderer for a legal document (its own route: /terms, /privacy). Long legal text reads
// far better as a real, linkable page than a modal-in-modal. Hebrew-first with an he/en toggle.
export function LegalPage({ doc }: { doc: "terms" | "privacy" }) {
  const [lang, setLang] = useState<Lang>("he");
  const isTerms = doc === "terms";
  const sections = isTerms ? termsSections(lang) : privacySections(lang);
  const version = isTerms ? TERMS_VERSION : PRIVACY_VERSION;
  const effective = isTerms ? TERMS_EFFECTIVE : PRIVACY_EFFECTIVE;
  const title = tr(lang, isTerms ? "termsTitle" : "privacyTitle");

  return (
    <div dir={lang === "he" ? "rtl" : "ltr"} className="min-h-screen py-10 px-4">
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
          <h1 className="font-serif text-3xl font-bold text-tekhelet">{title}</h1>
          <p className="text-xs text-ink/50">
            {tr(lang, "termsVersionLabel")} {version} · {tr(lang, "termsEffectiveLabel")} {effective}
          </p>
        </header>

        {sections.map((s, i) => (
          <section key={i}>
            <h2 className="font-serif font-bold text-tekhelet mb-1">{`${i + 1}. ${s.heading}`}</h2>
            <p className="text-sm text-ink/75 leading-relaxed whitespace-pre-line">{s.body}</p>
          </section>
        ))}
      </article>
    </div>
  );
}
