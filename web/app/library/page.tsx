"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { api } from "@/lib/api";
import { Icon } from "@/components/Icon";
import {
  bookTitle,
  buildTree,
  fetchCatalog,
  pathLabels,
  searchBooks,
  searchIndex,
  type Catalog,
  type CategoryNode,
} from "@/lib/library";

// Beta: the page is for the admin account only, like the beta chat modes. The gate is UX — the
// catalogue is the public corpus's book list and /reader/catalog is not secret.
// No `metadata` export: Client Component (see limits/page.tsx).

const T: Record<Lang, Record<string, string>> = {
  he: {
    title: "ספריית הספרים",
    search: "חיפוש ספר בעברית או באנגלית…",
    back: "חזרה",
    none: "לא נמצאו ספרים",
    loading: "טוען…",
    error: "טעינת הרשימה נכשלה",
    denied: "העמוד הזה זמין כרגע במצב בטא בלבד.",
    books: "ספרים",
    results: "תוצאות",
    expand: "פתח הכול",
    collapse: "סגור הכול",
  },
  en: {
    title: "Book library",
    search: "Search a book in Hebrew or English…",
    back: "Back",
    none: "No books found",
    loading: "Loading…",
    error: "Failed to load the list",
    denied: "This page is in beta and not available yet.",
    books: "books",
    results: "results",
    expand: "Expand all",
    collapse: "Collapse all",
  },
};

function Branch({
  node,
  lang,
  open,
  depth,
}: {
  node: CategoryNode;
  lang: Lang;
  open: boolean;
  depth: number;
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
          <Branch key={c.path} node={c} lang={lang} open={open} depth={depth + 1} />
        ))}
        {node.books.map((b) => (
          <Link
            key={b.first_ref}
            href={`/search/read/${encodeURIComponent(b.first_ref)}`}
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

export default function LibraryPage() {
  const [lang, setLang] = useState<Lang>("he");
  const [admin, setAdmin] = useState<boolean | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [openAll, setOpenAll] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("chavruta-lang");
      if (saved === "en" || saved === "he") setLang(saved);
    } catch {}
    api.me().then((m) => setAdmin(!!m.is_admin)).catch(() => setAdmin(false));
  }, []);

  useEffect(() => {
    if (!admin) return;
    fetchCatalog().then(setCatalog).catch(() => setFailed(true));
  }, [admin]);

  const tree = useMemo(() => (catalog ? buildTree(catalog, lang) : []), [catalog, lang]);
  const index = useMemo(() => (catalog ? searchIndex(catalog.books) : null), [catalog]);
  const hits = useMemo(
    () => (catalog && index && query.trim() ? searchBooks(catalog.books, index, query) : null),
    [catalog, index, query],
  );
  const t = T[lang];

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
            <div className="flex items-center gap-2 rounded-2xl border border-line bg-white/70 px-3 py-2">
              <Icon name="search" className="text-[20px] text-ink/50" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t.search}
                className="flex-1 bg-transparent outline-none text-ink"
                autoFocus
              />
              {query && (
                <button onClick={() => setQuery("")} aria-label="clear" className="text-ink/50 hover:text-ink">
                  <Icon name="close" className="text-[18px]" />
                </button>
              )}
            </div>

            {failed && <p className="text-red-700">{t.error}</p>}
            {!catalog && !failed && <p className="text-ink/60">{t.loading}</p>}

            {catalog && hits === null && (
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
                    <Branch key={n.path} node={n} lang={lang} open={openAll} depth={0} />
                  ))}
                </div>
              </>
            )}

            {catalog && hits !== null && (
              <>
                <div className="text-sm text-ink/60">
                  {hits.length} {t.results}
                </div>
                {hits.length === 0 && <p className="text-ink/70">{t.none}</p>}
                <ul className="flex flex-col">
                  {hits.map((b) => (
                    <li key={b.first_ref}>
                      <Link
                        href={`/search/read/${encodeURIComponent(b.first_ref)}`}
                        className="block py-2 px-2 rounded-lg hover:bg-black/5"
                      >
                        <div className="text-ink font-medium">{bookTitle(b, lang)}</div>
                        <div className="text-xs text-ink/50">
                          {pathLabels(catalog, b.path, lang).join(" › ")}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
