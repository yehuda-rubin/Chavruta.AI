"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { Lang, SearchResponse } from "@/lib/types";
import { api } from "@/lib/api";
import { Icon } from "@/components/Icon";
import { ResultCard } from "@/components/search/ResultCard";
import { Pagination } from "@/components/search/Pagination";
import { fetchSearch } from "@/lib/search";
import {
  bookTitle,
  buildTree,
  ERA_CHIPS,
  fetchCatalog,
  fetchSources,
  fetchToc,
  bookPathLabels,
  searchBooks,
  searchIndex,
  sourceLabel,
  unitLabel,
  type Catalog,
  type CatalogBook,
  type CategoryNode,
  type SourceMatch,
  type Toc,
} from "@/lib/library";

// Beta: the page is for the admin account only, like the beta chat modes. The gate is UX — the
// catalogue is the public corpus's book list and /reader/catalog is not secret.
// No `metadata` export: Client Component (see limits/page.tsx).
//
// One search box, two clearly different searches:
//   • "ספר או מקור" — find a book by name or jump to a citation ("בראשית א א", "ברכות ב ע״ב"). Instant.
//   • "תוכן"        — full-text search inside the books (FTS5), with category filters.

type Mode = "book" | "content";
const PAGE_SIZE = 20;

const T: Record<Lang, Record<string, string>> = {
  he: {
    title: "ספריית הספרים",
    back: "חזרה",
    modeBook: "ספר או מקור",
    modeContent: "תוכן",
    phBook: "שם ספר, או מקור — למשל בראשית א א, ברכות ב ע״ב",
    phContent: "מילה או ביטוי בתוך הטקסטים…",
    none: "לא נמצאו ספרים",
    noneContent: "לא נמצאו תוצאות",
    loading: "טוען…",
    error: "הפעולה נכשלה",
    denied: "העמוד הזה זמין כרגע במצב בטא בלבד.",
    books: "ספרים",
    results: "תוצאות",
    expand: "פתח הכול",
    collapse: "סגור הכול",
    source: "מקור",
    booksHeading: "ספרים",
    looksLikeSource: "נראה כמו מקור",
    open: "פתח",
    all: "הכול",
    hintContent: "חיפוש בתוך הטקסט של כל הספרים. לחץ Enter.",
    suggested: "הצעות",
    start: "התחל לקרוא",
    inBook: "חיפוש בתוך הספר…",
    inside: "בתוך",
    toLibrary: "לספרייה",
    chapters: "פרקים",
    dapim: "דפים",
    noToc: "אין רשימת פרקים לספר הזה",
  },
  en: {
    title: "Book library",
    back: "Back",
    modeBook: "Book or source",
    modeContent: "Content",
    phBook: "A book name, or a source — e.g. Genesis 1:1, Berakhot 2b",
    phContent: "A word or phrase inside the texts…",
    none: "No books found",
    noneContent: "No results",
    loading: "Loading…",
    error: "Something went wrong",
    denied: "This page is in beta and not available yet.",
    books: "books",
    results: "results",
    expand: "Expand all",
    collapse: "Collapse all",
    source: "Source",
    booksHeading: "Books",
    looksLikeSource: "Looks like a source",
    open: "Open",
    all: "All",
    hintContent: "Searches the text of every book. Press Enter.",
    suggested: "Suggestions",
    start: "Start reading",
    inBook: "Search inside this book…",
    inside: "In",
    toLibrary: "Library",
    chapters: "Chapters",
    dapim: "Folios",
    noToc: "No chapter list for this book",
  },
};

const SUGGESTED: Record<Lang, string[]> = {
  he: ["פיקוח נפש", "שמיטה", "שניים אוחזין בטלית", "נר חנוכה", "תלמוד תורה"],
  en: ["Pikuach Nefesh", "Shmita", "Two holding a garment", "Chanukah candles", "Torah study"],
};

const readUrl = (ref: string) => `/search/read/${encodeURIComponent(ref)}`;

function Branch({
  node,
  lang,
  open,
  depth,
  onOpen,
}: {
  node: CategoryNode;
  lang: Lang;
  open: boolean;
  depth: number;
  onOpen: (b: CatalogBook) => void;
}) {
  return (
    <details open={open} className="group" key={`${node.path}-${open}`}>
      <summary
        className="flex items-center gap-2 cursor-pointer select-none py-2 px-2 rounded-xl hover:bg-black/5 list-none"
        style={{ paddingInlineStart: `${depth * 16 + 8}px` }}
      >
        <Icon name="chevron_left" className="text-[18px] text-ink/50 transition-transform group-open:-rotate-90 rtl:group-open:rotate-90" />
        <span className="font-semibold text-tekhelet">{node.name}</span>
        <span className="text-xs text-ink/50">{node.total}</span>
      </summary>
      <div>
        {node.children.map((c) => (
          <Branch key={c.path} node={c} lang={lang} open={open} depth={depth + 1} onOpen={onOpen} />
        ))}
        {node.books.map((b) => (
          <Link
            key={b.first_ref}
            href={bookUrl(b)}
            onClick={(e) => {
              e.preventDefault();
              onOpen(b);
            }}
            className="block py-1.5 px-2 rounded-lg hover:bg-black/5 text-ink"
            style={{ paddingInlineStart: `${(depth + 1) * 16 + 34}px` }}
          >
            {bookTitle(b, lang)}
          </Link>
        ))}
      </div>
    </details>
  );
}

const bookUrl = (b: CatalogBook) => `/library?book=${encodeURIComponent(b.title_en)}`;

/** A book's page: where it sits, a way in at the start, search inside it, and its chapters / dapim. */
function BookView({
  book,
  catalog,
  lang,
  onBack,
  onSearchInside,
}: {
  book: CatalogBook;
  catalog: Catalog;
  lang: Lang;
  onBack: () => void;
  onSearchInside: (q: string) => void;
}) {
  const t = T[lang];
  const [toc, setToc] = useState<Toc | null | undefined>(undefined);
  const [q, setQ] = useState("");

  useEffect(() => {
    const ctl = new AbortController();
    setToc(undefined);
    fetchToc(book.title_en, ctl.signal).then(setToc).catch(() => {});
    return () => ctl.abort();
  }, [book.title_en]);

  // Units grouped by the section they sit in (most books have a single, unnamed group).
  const groups = useMemo(() => {
    const m = new Map<string, Toc["units"]>();
    for (const u of toc?.units ?? []) m.set(u.section, [...(m.get(u.section) ?? []), u]);
    return [...m.entries()];
  }, [toc]);

  return (
    <div className="flex flex-col gap-4">
      <button onClick={onBack} className="self-start text-sm text-ink/60 hover:text-ink flex items-center gap-1">
        <Icon name="arrow_back" className="text-[18px] rtl:rotate-180" />
        {t.toLibrary}
      </button>
      <div>
        <h2 className="text-2xl font-bold text-tekhelet">{bookTitle(book, lang)}</h2>
        <div className="text-sm text-ink/50 mt-1">{bookPathLabels(catalog, book, lang).join(" › ")}</div>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <Link href={readUrl(book.first_ref)} className="px-5 py-2 rounded-xl grad text-white text-sm font-semibold shadow-md">
          {t.start}
        </Link>
        <form
          className="flex-1 min-w-[200px] flex items-center gap-2 rounded-xl border border-line bg-white/70 px-3 py-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (q.trim()) onSearchInside(q.trim());
          }}
        >
          <Icon name="search" className="text-[18px] text-ink/50" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t.inBook}
            className="flex-1 bg-transparent outline-none text-sm text-ink"
          />
        </form>
      </div>
      {toc === undefined && <p className="text-ink/60">{t.loading}</p>}
      {toc === null && <p className="text-ink/60">{t.noToc}</p>}
      {toc &&
        groups.map(([section, units]) => (
          <div key={section} className="flex flex-col gap-2">
            <div className="text-sm font-semibold text-ink/70">
              {section || (toc.kind === "daf" ? t.dapim : t.chapters)}
              <span className="text-ink/40 font-normal"> · {units.length}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {units.map((u) => (
                <Link
                  key={u.ref}
                  href={readUrl(u.ref)}
                  title={`${u.count}`}
                  className="min-w-[2.6rem] text-center px-2.5 py-1.5 rounded-lg bg-black/5 hover:bg-tekhelet hover:text-white text-sm text-ink"
                >
                  {unitLabel(u, toc.kind, lang)}
                </Link>
              ))}
            </div>
          </div>
        ))}
    </div>
  );
}

function SourceRows({ sources, lang, label }: { sources: SourceMatch[]; lang: Lang; label: string }) {
  if (!sources.length) return null;
  return (
    <ul className="flex flex-col gap-1">
      {sources.map((m) => (
        <li key={m.ref}>
          <Link
            href={readUrl(m.ref)}
            className="flex items-center gap-3 py-2.5 px-3 rounded-xl bg-tekhelet/5 hover:bg-tekhelet/10 text-tekhelet font-semibold"
          >
            <Icon name="auto_stories" className="text-[20px]" />
            <span className="flex-1">{sourceLabel(m, lang)}</span>
            <span className="text-xs font-normal text-ink/50">{label}</span>
            <Icon name="arrow_back" className="text-[18px] ltr:rotate-180" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function LibraryPage() {
  const [lang, setLang] = useState<Lang>("he");
  const [admin, setAdmin] = useState<boolean | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [failed, setFailed] = useState(false);
  const [mode, setMode] = useState<Mode>("book");
  const [input, setInput] = useState("");          // what is typed
  const [submitted, setSubmitted] = useState("");  // what content search ran for
  const [openAll, setOpenAll] = useState(false);
  const [sources, setSources] = useState<SourceMatch[]>([]);
  const [content, setContent] = useState<SearchResponse | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [era, setEra] = useState("");
  const [bookFilter, setBookFilter] = useState("");          // content search inside one book (English title)
  const [openBook, setOpenBook] = useState<CatalogBook | null>(null);
  const [pendingBook, setPendingBook] = useState("");        // ?book= from the URL, until the catalogue loads
  const booted = useRef(false);

  // Language, admin gate, and the state carried in the URL (also what /search redirects to).
  useEffect(() => {
    try {
      const saved = localStorage.getItem("chavruta-lang");
      if (saved === "en" || saved === "he") setLang(saved);
      const sp = new URLSearchParams(window.location.search);
      const content = sp.get("mode") === "content";
      if (content) setMode("content");
      const q = sp.get("q") || "";
      setInput(q);
      if (content) setSubmitted(q);
      setEra(sp.get("era") || "");
      if (content) setBookFilter(sp.get("book") || "");
      else setPendingBook(sp.get("book") || "");
      const p = parseInt(sp.get("page") || "1", 10);
      setPage(Number.isNaN(p) || p < 1 ? 1 : p);
    } catch {}
    booted.current = true;
    api.me().then((m) => setAdmin(!!m.is_admin)).catch(() => setAdmin(false));
  }, []);

  useEffect(() => {
    if (!admin) return;
    fetchCatalog().then(setCatalog).catch(() => setFailed(true));
  }, [admin]);

  useEffect(() => {
    if (!catalog || !pendingBook) return;
    setOpenBook(catalog.books.find((b) => b.title_en === pendingBook) ?? null);
    setPendingBook("");
  }, [catalog, pendingBook]);

  const openBookPage = useCallback((b: CatalogBook) => {
    setOpenBook(b);
    setMode("book");
    try {
      window.scrollTo({ top: 0 });
    } catch {}
  }, []);

  const searchInsideBook = useCallback((b: CatalogBook, q: string) => {
    setBookFilter(b.title_en);
    setEra("");
    setInput(q);
    setSubmitted(q);
    setPage(1);
    setMode("content");
  }, []);

  // Keep the URL shareable without a navigation.
  useEffect(() => {
    if (!booted.current) return;
    const sp = new URLSearchParams();
    if (mode === "content") sp.set("mode", "content");
    const q = mode === "content" ? submitted : input;
    if (q.trim()) sp.set("q", q.trim());
    if (mode === "content" && era) sp.set("era", era);
    if (mode === "content" && bookFilter) sp.set("book", bookFilter);
    if (mode === "book" && openBook) sp.set("book", openBook.title_en);
    if (mode === "content" && page > 1) sp.set("page", String(page));
    const qs = sp.toString();
    try {
      window.history.replaceState(null, "", qs ? `/library?${qs}` : "/library");
    } catch {}
  }, [mode, input, submitted, era, page, bookFilter, openBook]);

  const tree = useMemo(() => (catalog ? buildTree(catalog, lang) : []), [catalog, lang]);
  const index = useMemo(() => (catalog ? searchIndex(catalog.books) : null), [catalog]);
  const bookHits = useMemo(
    () => (mode === "book" && catalog && index && input.trim() ? searchBooks(catalog.books, index, input) : null),
    [mode, catalog, index, input],
  );

  // Source lookup: live in book mode, and as a "this looks like a source" hint in content mode.
  const sourceQuery = mode === "book" ? input : submitted;
  useEffect(() => {
    if (!admin || !sourceQuery.trim()) {
      setSources([]);
      return;
    }
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      fetchSources(sourceQuery, ctl.signal).then(setSources).catch(() => {});
    }, mode === "book" ? 200 : 0);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [admin, sourceQuery, mode]);

  // Content search runs on submit (full-text is heavier than a title match).
  useEffect(() => {
    if (!admin || mode !== "content" || !submitted.trim()) {
      setContent(null);
      return;
    }
    let live = true;
    setContentLoading(true);
    setContentError(null);
    fetchSearch({
      q: submitted,
      offset: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
      era: era || undefined,
      book: bookFilter || undefined,
    })
      .then((r) => live && setContent(r))
      .catch((e) => live && setContentError(e?.message === "RATE_LIMITED" ? "429" : "error"))
      .finally(() => live && setContentLoading(false));
    return () => {
      live = false;
    };
  }, [admin, mode, submitted, page, era, bookFilter]);

  const runContent = useCallback(() => {
    setSubmitted(input.trim());
    setPage(1);
  }, [input]);

  const t = T[lang];
  const filterBook = catalog?.books.find((b) => b.title_en === bookFilter);
  const insideTitle = filterBook ? bookTitle(filterBook, lang) : bookFilter;
  const totalPages = content ? Math.max(1, Math.ceil(content.total / PAGE_SIZE)) : 1;

  return (
    <div dir={lang === "he" ? "rtl" : "ltr"} className="h-dvh overflow-y-auto py-8 px-4">
      <div className="glass rounded-[28px] max-w-3xl mx-auto p-6 sm:p-8 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold text-tekhelet">{t.title}</h1>
          <Link href="/" className="text-sm text-ink/70 hover:text-ink flex items-center gap-1">
            <Icon name="arrow_back" className="text-[18px] rtl:rotate-180" />
            {t.back}
          </Link>
        </div>

        {admin === null && <p className="text-ink/60">{t.loading}</p>}
        {admin === false && <p className="text-ink/70">{t.denied}</p>}

        {admin && (
          <>
            <div role="tablist" className="grid grid-cols-2 gap-1 p-1 rounded-2xl bg-black/5 text-sm font-semibold">
              {(["book", "content"] as Mode[]).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={mode === m}
                  onClick={() => {
                    setMode(m);
                    if (m === "content" && input.trim()) {
                      setSubmitted(input.trim());
                      setPage(1);
                    }
                  }}
                  className={`py-2 rounded-xl transition ${
                    mode === m ? "bg-white text-tekhelet shadow-sm" : "text-ink/60 hover:text-ink"
                  }`}
                >
                  {m === "book" ? t.modeBook : t.modeContent}
                </button>
              ))}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (mode === "content") runContent();
              }}
              className="flex items-center gap-2 rounded-2xl border border-line bg-white/70 px-3 py-2"
            >
              <Icon name="search" className="text-[20px] text-ink/50" />
              <input
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  if (e.target.value.trim()) setOpenBook(null); // typing a new search leaves the book page
                }}
                placeholder={mode === "book" ? t.phBook : t.phContent}
                className="flex-1 bg-transparent outline-none text-ink"
                autoFocus
              />
              {input && (
                <button
                  type="button"
                  onClick={() => {
                    setInput("");
                    setSubmitted("");
                    setPage(1);
                  }}
                  aria-label="clear"
                  className="text-ink/50 hover:text-ink"
                >
                  <Icon name="close" className="text-[18px]" />
                </button>
              )}
            </form>

            {failed && mode === "book" && <p className="text-red-700">{t.error}</p>}

            {/* ───────────── book page ───────────── */}
            {mode === "book" && openBook && catalog && (
              <BookView
                book={openBook}
                catalog={catalog}
                lang={lang}
                onBack={() => setOpenBook(null)}
                onSearchInside={(q) => searchInsideBook(openBook, q)}
              />
            )}

            {/* ───────────── book / source ───────────── */}
            {mode === "book" && !openBook && (
              <>
                {!catalog && !failed && <p className="text-ink/60">{t.loading}</p>}

                {catalog && bookHits === null && (
                  <>
                    <div className="flex items-center justify-between text-sm text-ink/60">
                      <span>
                        {catalog.books.length} {t.books}
                      </span>
                      <button onClick={() => setOpenAll((v) => !v)} className="hover:text-ink underline">
                        {openAll ? t.collapse : t.expand}
                      </button>
                    </div>
                    <div>
                      {tree.map((n) => (
                        <Branch key={n.path} node={n} lang={lang} open={openAll} depth={0} onOpen={openBookPage} />
                      ))}
                    </div>
                  </>
                )}

                {catalog && bookHits !== null && (
                  <>
                    <SourceRows sources={sources} lang={lang} label={t.source} />
                    {sources.length === 0 && bookHits.length === 0 && <p className="text-ink/70">{t.none}</p>}
                    {bookHits.length > 0 && (
                      <>
                        <div className="text-sm text-ink/60">
                          {t.booksHeading} · {bookHits.length}
                        </div>
                        <ul className="flex flex-col">
                          {bookHits.map((b) => (
                            <li key={b.first_ref}>
                              <Link
                                href={bookUrl(b)}
                                onClick={(e) => {
                                  e.preventDefault();
                                  openBookPage(b);
                                }}
                                className="block py-2 px-2 rounded-lg hover:bg-black/5"
                              >
                                <div className="text-ink font-medium">{bookTitle(b, lang)}</div>
                                <div className="text-xs text-ink/50">{bookPathLabels(catalog, b, lang).join(" › ")}</div>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </>
                )}
              </>
            )}

            {/* ───────────── content ───────────── */}
            {mode === "content" && (
              <>
                {!submitted.trim() && (
                  <div className="flex flex-col gap-3">
                    <p className="text-sm text-ink/60">{t.hintContent}</p>
                    <div className="text-xs text-ink/50">{t.suggested}</div>
                    <div className="flex flex-wrap gap-2">
                      {SUGGESTED[lang].map((s) => (
                        <button
                          key={s}
                          onClick={() => {
                            setInput(s);
                            setSubmitted(s);
                            setPage(1);
                          }}
                          className="px-3 py-1.5 rounded-full bg-black/5 hover:bg-black/10 text-sm text-ink"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {bookFilter && (
                  <button
                    onClick={() => {
                      setBookFilter("");
                      setPage(1);
                    }}
                    className="self-start flex items-center gap-2 px-3 py-1 rounded-full bg-tekhelet/10 text-tekhelet text-sm"
                  >
                    {t.inside}: {insideTitle}
                    <Icon name="close" className="text-[16px]" />
                  </button>
                )}

                {submitted.trim() && sources.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <div className="text-xs text-ink/50">{t.looksLikeSource}</div>
                    <SourceRows sources={sources} lang={lang} label={t.open} />
                  </div>
                )}

                {submitted.trim() && content && (
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => {
                        setEra("");
                        setPage(1);
                      }}
                      className={`px-3 py-1 rounded-full text-sm ${!era ? "bg-tekhelet text-white" : "bg-black/5 hover:bg-black/10 text-ink"}`}
                    >
                      {t.all}
                    </button>
                    {ERA_CHIPS.filter((c) => (content.eras?.[c.id] ?? 0) > 0 || era === c.id).map((c) => (
                      <button
                        key={c.id}
                        onClick={() => {
                          setEra(c.id);
                          setPage(1);
                        }}
                        className={`px-3 py-1 rounded-full text-sm ${era === c.id ? "bg-tekhelet text-white" : "bg-black/5 hover:bg-black/10 text-ink"}`}
                      >
                        {lang === "he" ? c.he : c.en} <span className="opacity-60">{content.eras?.[c.id] ?? 0}</span>
                      </button>
                    ))}
                  </div>
                )}

                {contentLoading && <p className="text-ink/60">{t.loading}</p>}
                {contentError && <p className="text-red-700">{contentError === "429" ? "429" : t.error}</p>}
                {content && !contentLoading && (
                  <>
                    <div className="text-sm text-ink/60">
                      {content.total} {t.results}
                    </div>
                    {content.hits.length === 0 && <p className="text-ink/70">{t.noneContent}</p>}
                    <div className="flex flex-col gap-3">
                      {content.hits.map((h, i) => (
                        <ResultCard key={`${h.ref}-${i}`} hit={h} lang={lang} />
                      ))}
                    </div>
                    <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} lang={lang} />
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
