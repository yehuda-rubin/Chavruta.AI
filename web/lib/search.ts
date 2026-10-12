import type { Lang, SearchResponse } from "./types";

export interface SearchQueryParams {
  q: string;
  offset?: number;
  limit?: number;
  work_id?: string;
  /** Time period: tanakh | chazal | geonim | rishonim | acharonim | modern | other (comma-separated). */
  era?: string;
  /** Search inside one book (its English title). */
  book?: string;
}

export const CANONICAL_CATEGORIES = [
  "tanakh",
  "mishnah",
  "tosefta",
  "gemara",
  "yerushalmi",
  "midrash",
  "halacha",
  "shut",
  "kabbalah",
  "chasidut",
  "jewish_thought",
  "musar",
  "liturgy",
  "second_temple",
  "reference",
] as const;

export type CategoryId = (typeof CANONICAL_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<Lang, Record<string, string>> = {
  he: {
    tanakh: 'תנ"ך',
    mishnah: "משנה",
    tosefta: "תוספתא",
    gemara: "תלמוד בבלי",
    yerushalmi: "תלמוד ירושלמי",
    midrash: "מדרש",
    halacha: "הלכה",
    shut: 'שו"ת',
    kabbalah: "קבלה",
    chasidut: "חסידות",
    jewish_thought: "מחשבת ישראל",
    musar: "מוסר",
    liturgy: "תפילה ופיוט",
    second_temple: "בית שני",
    reference: "ספרי יעץ",
  },
  en: {
    tanakh: "Tanakh",
    mishnah: "Mishnah",
    tosefta: "Tosefta",
    gemara: "Talmud Bavli",
    yerushalmi: "Jerusalem Talmud",
    midrash: "Midrash",
    halacha: "Halacha",
    shut: "Responsa",
    kabbalah: "Kabbalah",
    chasidut: "Chasidut",
    jewish_thought: "Jewish Thought",
    musar: "Musar",
    liturgy: "Liturgy",
    second_temple: "Second Temple",
    reference: "Reference",
  },
};

export async function fetchSearch(params: SearchQueryParams): Promise<SearchResponse> {
  const sp = new URLSearchParams();
  sp.set("q", params.q.trim());
  if (params.offset !== undefined && params.offset > 0) {
    sp.set("offset", String(params.offset));
  }
  if (params.limit !== undefined && params.limit > 0) {
    sp.set("limit", String(params.limit));
  }
  if (params.era && params.era.trim()) {
    sp.set("era", params.era.trim());
  }
  if (params.work_id && params.work_id.trim()) {
    sp.set("work_id", params.work_id.trim());
  }
  if (params.book && params.book.trim()) {
    sp.set("book", params.book.trim());
  }

  const res = await fetch(`/search/query?${sp.toString()}`, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!res.ok) {
    if (res.status === 429) {
      throw new Error("RATE_LIMITED");
    }
    const text = await res.text().catch(() => "");
    throw new Error(`SEARCH_FAILED_${res.status}: ${text}`);
  }

  return (await res.json()) as SearchResponse;
}
