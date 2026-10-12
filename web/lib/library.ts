import type { Lang } from "@/lib/types";
import { formatTalmudDaf, toGematria } from "@/lib/reader";

/** One work in the library — built by scripts/build_catalog.py, served at /reader/catalog. */
export interface CatalogBook {
  title_en: string;
  title_he: string;
  /** Category path in Sefaria's English names, "/"-joined: "Tanakh/Rishonim on Tanakh/Rashi/Torah". */
  path: string;
  segments: number;
  /** Corpus ref the reader opens the book at. */
  first_ref: string;
  license: string;
  /** Learning-order rank (lower first), added by /reader/catalog from layer_rank.json. */
  rank?: number;
  /** Canonical load order of the book's first chunk (Genesis before Exodus), from /reader/catalog. */
  order?: number;
}

export interface CatalogCategory {
  en: string;
  he: string;
}

export interface Catalog {
  categories: Record<string, CatalogCategory>;
  books: CatalogBook[];
}

/** A node of the browse tree: a category, with sub-categories and the books directly in it. */
export interface CategoryNode {
  path: string;
  name: string;
  children: CategoryNode[];
  books: CatalogBook[];
  /** Books in this node and everything below it. */
  total: number;
}

export async function fetchCatalog(): Promise<Catalog> {
  // ?v= busts the browser cache of an older catalogue (it was cached for an hour without rank/order); bump it when the shape changes
  const res = await fetch("/reader/catalog?v=2", { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`catalog ${res.status}`);
  return (await res.json()) as Catalog;
}

const collator = (lang: Lang) => new Intl.Collator(lang === "he" ? "he" : "en", { numeric: true });

export function bookTitle(b: CatalogBook, lang: Lang): string {
  return lang === "he" ? b.title_he : b.title_en;
}

const ERA_ROOTS: { upTo: number; key: string; he: string; en: string }[] = [
  { upTo: 19, key: "E:tanakh", he: "תנ״ך", en: "Tanakh" },
  { upTo: 199, key: "E:chazal", he: "חז״ל", en: "Chazal (Mishnah, Talmud, Midrash)" },
  { upTo: 299, key: "E:geonim", he: "גאונים", en: "Geonim" },
  { upTo: 399, key: "E:rishonim", he: "ראשונים", en: "Rishonim" },
  { upTo: 499, key: "E:acharonim", he: "אחרונים", en: "Acharonim" },
  { upTo: 799, key: "E:modern", he: "בני זמננו", en: "Contemporary" },
  { upTo: 1e9, key: "E:reference", he: "ספרי עזר", en: "Reference" },
];

/** What a work is, whatever its era: the first part of Sefaria's path, in the reader's words. */
const GENRES: Record<string, { he: string; en: string }> = {
  Tanakh: { he: "פירושים על התנ״ך", en: "Tanakh commentary" },
  Mishnah: { he: "משנה ופירושיה", en: "Mishnah and its commentary" },
  Tosefta: { he: "תוספתא ופירושיה", en: "Tosefta and its commentary" },
  Talmud: { he: "תלמוד ופירושיו", en: "Talmud and its commentary" },
  Midrash: { he: "מדרש", en: "Midrash" },
  Halakhah: { he: "הלכה", en: "Halakhah" },
  Responsa: { he: "שו״ת", en: "Responsa" },
  "Jewish Thought": { he: "מחשבת ישראל", en: "Jewish thought" },
  Musar: { he: "מוסר", en: "Musar" },
  Kabbalah: { he: "קבלה", en: "Kabbalah" },
  Chasidut: { he: "חסידות", en: "Chasidut" },
  Liturgy: { he: "תפילה", en: "Liturgy" },
  "Second Temple": { he: "ספרות בית שני", en: "Second Temple literature" },
  Reference: { he: "מילונים וספרי יעץ", en: "Reference" },
};
/** The period filter of content search, in learning order. */
export const ERA_CHIPS: { id: string; he: string; en: string }[] = [
  { id: "tanakh", he: "תנ״ך", en: "Tanakh" },
  { id: "chazal", he: "חז״ל", en: "Chazal" },
  { id: "geonim", he: "גאונים", en: "Geonim" },
  { id: "rishonim", he: "ראשונים", en: "Rishonim" },
  { id: "acharonim", he: "אחרונים", en: "Acharonim" },
  { id: "modern", he: "בני זמננו", en: "Contemporary" },
  { id: "other", he: "אחר", en: "Other" },
];
const ERA_WORD = /^(Geonim|Rishonim|Acharonim|Modern)( on |$)/;

export interface Place {
  key: string;
  label: string;
}

/** Where a work sits in the library: by TIME, not by Sefaria's shelves. The Tanakh itself first, then Chazal,
 *  then Geonim, Rishonim, Acharonim and today; a commentator stands with his own era, whatever he comments on
 *  (Rashi on the Torah with the Rishonim), and inside an era by genre. */
export function placement(cat: Catalog, b: CatalogBook, lang: Lang): Place[] {
  const rank = b.rank ?? 800;
  const parts = b.path.split("/");
  const label = (i: number) => {
    const meta = cat.categories[parts.slice(0, i + 1).join("/")];
    return (lang === "he" ? meta?.he : meta?.en) || parts[i];
  };
  const root = ERA_ROOTS.find((r) => rank <= r.upTo)!;
  const out: Place[] = [{ key: root.key, label: lang === "he" ? root.he : root.en }];
  const primary = rank < 100;     // the text itself: Torah/Prophets/Writings, Mishnah, Tosefta, Talmud, Midrash
  if (!primary) {
    const g = GENRES[parts[0]];
    out.push({ key: `${root.key}/G:${parts[0]}`, label: g ? (lang === "he" ? g.he : g.en) : parts[0] });
  }
  const base = out[out.length - 1].key;
  // the root already says "Tanakh"; Mishnah, Talmud, Midrash keep their own first part
  for (let i = !primary || root.key === "E:tanakh" ? 1 : 0; i < parts.length; i++) {
    if (ERA_WORD.test(parts[i])) continue;
    out.push({ key: `${base}|${parts.slice(0, i + 1).join("/")}`, label: label(i) });
  }
  return out;
}

/** The breadcrumb of a book in the time-based tree, without the book itself. */
export function bookPathLabels(cat: Catalog, b: CatalogBook, lang: Lang): string[] {
  return placement(cat, b, lang).map((p) => p.label);
}

/** Group the flat book list into the tree, in time order. */
export function buildTree(cat: Catalog, lang: Lang): CategoryNode[] {
  const cmp = collator(lang).compare;
  const nodes = new Map<string, CategoryNode>();
  const roots: CategoryNode[] = [];

  const ensure = (places: Place[], depth: number): CategoryNode => {
    const { key, label } = places[depth];
    let node = nodes.get(key);
    if (node) return node;
    node = { path: key, name: label, children: [], books: [], total: 0 };
    nodes.set(key, node);
    if (depth === 0) roots.push(node);
    else ensure(places, depth - 1).children.push(node);
    return node;
  };

  for (const b of cat.books) {
    const places = placement(cat, b, lang);
    ensure(places, places.length - 1).books.push(b);
    for (const pl of places) nodes.get(pl.key)!.total += 1;
  }

  // Learning order, not alphabetical: books by layer rank then canonical load order; a category sits where
  // its earliest book does (Tanakh, Mishnah, Tosefta, Talmud, Midrash, then the later literature).
  const key = (b: CatalogBook): [number, number] => [b.rank ?? 800, b.order ?? 1e9];
  const byKey = (x: [number, number], y: [number, number]) => x[0] - y[0] || x[1] - y[1];
  const first = new Map<CategoryNode, [number, number]>();
  const firstOf = (n: CategoryNode): [number, number] => {
    let best = first.get(n);
    if (best) return best;
    best = [Infinity, Infinity];
    for (const b of n.books) if (byKey(key(b), best) < 0) best = key(b);
    for (const c of n.children) if (byKey(firstOf(c), best) < 0) best = firstOf(c);
    first.set(n, best);
    return best;
  };
  const sortRec = (list: CategoryNode[]) => {
    list.sort((a, b) => byKey(firstOf(a), firstOf(b)) || cmp(a.name, b.name));
    for (const n of list) {
      n.books.sort((a, b) => byKey(key(a), key(b)) || cmp(bookTitle(a, lang), bookTitle(b, lang)));
      sortRec(n.children);
    }
  };
  sortRec(roots);
  return roots;
}

/** Fold a string for matching: drop niqqud/cantillation, geresh and gershayim, quotes, and
 *  punctuation; map final letters to their regular forms; lowercase. */
export function fold(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/[֑-ׇ]/g, "")
    .replace(/[׳״"'`’‘“”׳״.,;:()\-_]/g, "")
    .replace(/ך/g, "כ")
    .replace(/ם/g, "מ")
    .replace(/ן/g, "נ")
    .replace(/ף/g, "פ")
    .replace(/ץ/g, "צ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** Both-language haystack for one book, folded once. Hebrew and English titles are both searched
 *  whatever the UI language, so "Rashi on Genesis" finds the book from a Hebrew screen and vice versa. */
export function searchIndex(books: CatalogBook[]): Map<CatalogBook, string> {
  return new Map(books.map((b) => [b, fold(`${b.title_he} ${b.title_en}`)]));
}

/** Every word of the query must appear (as a substring) in the book's title. Results follow the
 *  learning order (`rank` from the catalogue), so "בראשית" lists Genesis before "רש"י על בראשית". */
export function searchBooks(
  books: CatalogBook[],
  index: Map<CatalogBook, string>,
  query: string,
  limit = 200,
): CatalogBook[] {
  const words = fold(query).split(" ").filter(Boolean);
  if (!words.length) return [];
  const scored: { b: CatalogBook; rank: number; layer: number }[] = [];
  for (const b of books) {
    const hay = index.get(b) ?? "";
    if (!words.every((w) => hay.includes(w))) continue;
    const starts = hay.startsWith(words[0]) || hay.includes(` ${words[0]}`) ? 0 : 1;
    const exact = hay === fold(query) || fold(b.title_he) === fold(query) || fold(b.title_en) === fold(query);
    scored.push({ b, rank: starts * 1000 + hay.length, layer: exact ? -1 : b.rank ?? 800 });
  }
  // learning order first (Torah, Prophets, Writings, Mishnah, Gemara, then each commentator by his era);
  // an exact title always leads, and inside one layer the closer title match comes first
  scored.sort((x, y) => x.layer - y.layer || x.rank - y.rank || (x.b.order ?? 1e9) - (y.b.order ?? 1e9));
  return scored.slice(0, limit).map((s) => s.b);
}

/** A citation the server could read from the query and found in the reader ("בראשית א א"). */
export interface SourceMatch {
  ref: string;       // what the reader opens: 'Genesis 1:3', 'Genesis.1', 'Berakhot.2a'
  book_he: string;
  book_en: string;
  nums: number[];
}

/** Library source search: a typed citation → readable units (empty when it is not a citation). */
export async function fetchSources(q: string, signal?: AbortSignal): Promise<SourceMatch[]> {
  const res = await fetch(`/reader/resolve?q=${encodeURIComponent(q.trim())}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) return [];
  return ((await res.json()) as { matches: SourceMatch[] }).matches ?? [];
}

export function sourceLabel(m: SourceMatch, lang: Lang): string {
  const daf = /\.(\d+)([ab])$/.exec(m.ref);
  if (lang === "en") return daf ? `${m.book_en} ${daf[1]}${daf[2]}` : `${m.book_en} ${m.nums.join(":")}`;
  if (daf) return `${m.book_he} ${formatTalmudDaf(`${daf[1]}${daf[2]}`)}`;
  return `${m.book_he} ${m.nums.map((n) => toGematria(n)).join(":")}`;
}

/** One chapter / daf / siman of a book, as the reader's index holds it (GET /reader/toc). */
export interface TocUnit {
  ref: string;       // what the reader opens: 'Genesis.1', 'Berakhot.2a'
  section: string;   // for works that name a section before the number ('Chizkuni, Genesis') — else ''
  n: number;
  side: string;      // 'a' | 'b' for dapim, else ''
  count: number;     // segments in the unit
}

export interface Toc {
  book: string;
  kind: "chapter" | "daf";
  units: TocUnit[];
}

export async function fetchToc(book: string, signal?: AbortSignal): Promise<Toc | null> {
  const res = await fetch(`/reader/toc?book=${encodeURIComponent(book)}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  return res.ok ? ((await res.json()) as Toc) : null;
}

export function unitLabel(u: TocUnit, kind: Toc["kind"], lang: Lang): string {
  if (lang === "en") return `${u.n}${u.side}`;
  if (kind === "daf") return `${toGematria(u.n)}${u.side === "a" ? "." : ":"}`;
  return toGematria(u.n);
}
