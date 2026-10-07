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
  const res = await fetch("/reader/catalog", { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`catalog ${res.status}`);
  return (await res.json()) as Catalog;
}

const collator = (lang: Lang) => new Intl.Collator(lang === "he" ? "he" : "en", { numeric: true });

export function bookTitle(b: CatalogBook, lang: Lang): string {
  return lang === "he" ? b.title_he : b.title_en;
}

/** Group the flat book list into the category tree, siblings in learning order. */
export function buildTree(cat: Catalog, lang: Lang): CategoryNode[] {
  const cmp = collator(lang).compare;
  const nodes = new Map<string, CategoryNode>();
  const roots: CategoryNode[] = [];

  const ensure = (path: string): CategoryNode => {
    let node = nodes.get(path);
    if (node) return node;
    const i = path.lastIndexOf("/");
    const meta = cat.categories[path];
    node = {
      path,
      name: (lang === "he" ? meta?.he : meta?.en) || path.slice(i + 1),
      children: [],
      books: [],
      total: 0,
    };
    nodes.set(path, node);
    if (i === -1) roots.push(node);
    else ensure(path.slice(0, i)).children.push(node);
    return node;
  };

  for (const b of cat.books) {
    const node = ensure(b.path);
    node.books.push(b);
    for (let p = b.path; ; ) {
      nodes.get(p)!.total += 1;
      const i = p.lastIndexOf("/");
      if (i === -1) break;
      p = p.slice(0, i);
    }
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

/** "Tanakh/Torah" → ["תנ״ך", "תורה"] for a result's breadcrumb. */
export function pathLabels(cat: Catalog, path: string, lang: Lang): string[] {
  const parts = path.split("/");
  return parts.map((part, i) => {
    const meta = cat.categories[parts.slice(0, i + 1).join("/")];
    return (lang === "he" ? meta?.he : meta?.en) || part;
  });
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
