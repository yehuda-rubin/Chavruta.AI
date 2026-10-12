"use client";

import { useEffect, useState } from "react";
import type { Citation, Lang } from "@/lib/types";

/** One-language citation labels from /reader/labels (corpus/cite_labels.py): the work, chapter and section in
 *  the reader's language only — never the corpus's internal line index, never English inside a Hebrew label. */
export interface CiteLabels {
  he: string;
  en: string;
  who_he: string;
  who_en: string;
}

const cache = new Map<string, CiteLabels>();

export function useCiteLabels(refs: string[]): Record<string, CiteLabels> {
  const [, bump] = useState(0);
  const key = refs.join("\n");
  useEffect(() => {
    const missing = refs.filter((r) => r && !cache.has(r));
    if (!missing.length) return;
    let alive = true;
    const sp = new URLSearchParams();
    missing.slice(0, 80).forEach((r) => sp.append("ref", r));
    fetch(`/reader/labels?${sp.toString()}`, { headers: { Accept: "application/json" } })
      .then((res) => (res.ok ? res.json() : {}))
      .then((data: Record<string, CiteLabels>) => {
        for (const [r, v] of Object.entries(data)) cache.set(r, v);
        if (alive) bump((n) => n + 1);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return Object.fromEntries(refs.filter((r) => cache.has(r)).map((r) => [r, cache.get(r)!]));
}

const LATIN = /[A-Za-z]/;

/** The label to print for a citation and the name of its author/work, in `lang` only. */
export function citeText(c: Citation, lang: Lang, labels: Record<string, CiteLabels>): { title: string; who: string } {
  const l = labels[c.ref];
  if (lang === "en") return { title: l?.en || c.ref, who: l?.who_en || "" };
  // Hebrew: the server label; before it arrives, the stored Hebrew ref only if it carries no Latin letters
  const stored = c.ref_he && !LATIN.test(c.ref_he) ? c.ref_he : "";
  return { title: l?.he || stored || c.ref_he || c.ref, who: l?.who_he || "" };
}
