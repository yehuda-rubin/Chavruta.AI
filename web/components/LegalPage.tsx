"use client";
import { useState } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import {
  termsSections, privacySections, accessibilitySections,
  TERMS_VERSION, TERMS_EFFECTIVE, PRIVACY_VERSION, PRIVACY_EFFECTIVE,
  ACCESSIBILITY_VERSION, ACCESSIBILITY_EFFECTIVE,
} from "@/lib/legal";
import { Icon } from "./Icon";

// Full-page renderer for a legal document (its own route: /terms, /privacy, /accessibility). Long
// legal text reads far better as a real, linkable page than a modal-in-modal. Hebrew-first with an
// he/en toggle.
export function LegalPage({ doc }: { doc: "terms" | "privacy" | "accessibility" }) {
  const [lang, setLang] = useState<Lang>("he");
  const sections = doc === "terms" ? termsSections(lang)
    : doc === "privacy" ? privacySections(lang) : accessibilitySections(lang);
  const version = doc === "terms" ? TERMS_VERSION
    : doc === "privacy" ? PRIVACY_VERSION : ACCESSIBILITY_VERSION;
  const effective = doc === "terms" ? TERMS_EFFECTIVE
    : doc === "privacy" ? PRIVACY_EFFECTIVE : ACCESSIBILITY_EFFECTIVE;
  const title = tr(lang, doc === "terms" ? "termsTitle"
    : doc === "privacy" ? "privacyTitle" : "accessibilityTitle");

  return (
    <div dir={lang === "he" ? "rtl" : "ltr"} className="h-screen overflow-y-auto py-10 px-4">
      {/* h-screen + overflow-y-auto: the app's <body> is overflow-hidden (fixed chat layout), so the
          page must own its own scroll or long legal text is clipped. */}
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
