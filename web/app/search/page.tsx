"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import type { Lang, SearchResponse } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { fetchSearch } from "@/lib/search";
import { Icon } from "@/components/Icon";
import { SearchBar } from "@/components/search/SearchBar";
import { ResultCard } from "@/components/search/ResultCard";
import { FacetSidebar } from "@/components/search/FacetSidebar";
import { Pagination } from "@/components/search/Pagination";

const SUGGESTED_QUERIES: Record<Lang, string[]> = {
  he: [
    "פיקוח נפש",
    "שמיטה",
    "בראשית א:א",
    "שניים אוחזין בטלית",
    "נר חנוכה",
    "תלמוד תורה",
  ],
  en: [
    "Pikuach Nefesh",
    "Shmita",
    "Genesis 1:1",
    "Two holding a garment",
    "Chanukah candles",
    "Torah study",
  ],
};

const PAGE_SIZE = 20;

function SearchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const queryParam = searchParams.get("q") || "";
  const workIdParam = searchParams.get("work_id") || "";
  const pageParam = parseInt(searchParams.get("page") || "1", 10);
  const currentPage = isNaN(pageParam) || pageParam < 1 ? 1 : pageParam;

  const [lang, setLang] = useState<Lang>("he");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchData, setSearchData] = useState<SearchResponse | null>(null);
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  // Sync lang and theme from localStorage / html
  useEffect(() => {
    try {
      const savedLang = localStorage.getItem("chavruta-lang");
      if (savedLang === "en" || savedLang === "he") {
        setLang(savedLang);
      }
      const isDark = document.body.classList.contains("theme-dark");
      setTheme(isDark ? "dark" : "light");
    } catch {}
  }, []);

  // Fetch search results whenever queryParam, workIdParam, or currentPage changes
  useEffect(() => {
    const trimmed = queryParam.trim();
    if (!trimmed) {
      setSearchData(null);
      setLoading(false);
      setError(null);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    const offset = (currentPage - 1) * PAGE_SIZE;

    fetchSearch({
      q: trimmed,
      offset,
      limit: PAGE_SIZE,
      work_id: workIdParam || undefined,
    })
      .then((data) => {
        if (isMounted) {
          setSearchData(data);
          setLoading(false);
          // Auto-adjust page if offset was beyond results
          if (data.total > 0 && offset >= data.total) {
            const maxPage = Math.ceil(data.total / PAGE_SIZE);
            updateUrlParams({ page: maxPage });
          }
        }
      })
      .catch((err) => {
        if (isMounted) {
          setLoading(false);
          if (err.message === "RATE_LIMITED") {
            setError("rate_limit");
          } else {
            setError("generic");
          }
        }
      });

    return () => {
      isMounted = false;
    };
  }, [queryParam, workIdParam, currentPage]);

  const toggleLang = () => {
    const next: Lang = lang === "he" ? "en" : "he";
    setLang(next);
    try {
      localStorage.setItem("chavruta-lang", next);
    } catch {}
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    if (next === "dark") {
      document.body.classList.add("theme-dark");
      try {
        localStorage.setItem("chavruta-theme", "dark");
      } catch {}
    } else {
      document.body.classList.remove("theme-dark");
      try {
        localStorage.setItem("chavruta-theme", "light");
      } catch {}
    }
  };

  const updateUrlParams = (updates: {
    q?: string;
    work_id?: string | null;
    page?: number | null;
  }) => {
    const sp = new URLSearchParams(searchParams.toString());

    if (updates.q !== undefined) {
      if (updates.q.trim()) {
        sp.set("q", updates.q.trim());
      } else {
        sp.delete("q");
      }
      // Reset page and filters when new query is submitted
      sp.delete("page");
      sp.delete("work_id");
    }

    if (updates.work_id !== undefined) {
      if (updates.work_id) {
        sp.set("work_id", updates.work_id);
      } else {
        sp.delete("work_id");
      }
      // Reset page when facet changes
      sp.delete("page");
    }

    if (updates.page !== undefined) {
      if (updates.page && updates.page > 1) {
        sp.set("page", String(updates.page));
      } else {
        sp.delete("page");
      }
    }

    const nextUrl = `/search${sp.toString() ? `?${sp.toString()}` : ""}`;
    router.push(nextUrl);
  };

  const handleSearchSubmit = (newQuery: string) => {
    updateUrlParams({ q: newQuery });
  };

  const selectedWorkIds = workIdParam
    ? workIdParam.split(",").map((s) => s.trim()).filter(Boolean)
    : [];

  const handleToggleWorkId = (workId: string) => {
    let nextWorkIds: string[];
    if (selectedWorkIds.includes(workId)) {
      nextWorkIds = selectedWorkIds.filter((id) => id !== workId);
    } else {
      nextWorkIds = [...selectedWorkIds, workId];
    }
    updateUrlParams({
      work_id: nextWorkIds.length > 0 ? nextWorkIds.join(",") : null,
    });
  };

  const handleClearAllFacets = () => {
    updateUrlParams({ work_id: null });
  };

  const handlePageChange = (newPage: number) => {
    updateUrlParams({ page: newPage });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const totalResults = searchData?.total ?? 0;
  const totalPages = Math.ceil(totalResults / PAGE_SIZE);
  const isLandingState = !queryParam.trim();

  return (
    <div
      dir={lang === "he" ? "rtl" : "ltr"}
      className="h-dvh overflow-y-auto flex flex-col selection:bg-gold/20"
    >
      {/* Top Header */}
      <header className="h-[70px] flex items-center justify-between px-4 lg:px-8 shrink-0 glass border-b border-white/40 sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2 hover:opacity-85 transition"
            title={tr(lang, "backToStudy")}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.png"
              alt={tr(lang, "brand")}
              className="h-9 w-auto object-contain"
            />
            <span className="font-serif text-2xl font-bold text-tekhelet hidden sm:inline">
              {tr(lang, "brand")}
            </span>
          </Link>

          <span className="text-ink/30 font-light hidden sm:inline">|</span>

          <Link
            href="/"
            className="inline-flex items-center gap-1 text-sm font-semibold text-tekhelet/80 hover:text-tekhelet transition px-2.5 py-1 rounded-full hover:bg-white/40"
          >
            <Icon
              name={lang === "he" ? "arrow_forward" : "arrow_back"}
              className="text-[18px]"
            />
            <span>{tr(lang, "backToStudy")}</span>
          </Link>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleLang}
            className="px-3.5 py-1.5 rounded-full glass text-ink/70 text-xs sm:text-sm font-semibold hover:text-tekhelet transition cursor-pointer"
            title="עברית · EN"
          >
            עברית · EN
          </button>

          <button
            type="button"
            onClick={toggleTheme}
            className="h-9 w-9 rounded-full glass grid place-items-center text-ink/70 hover:text-tekhelet transition cursor-pointer"
            title={tr(lang, "setTheme")}
          >
            <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} className="text-[18px]" />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 flex flex-col">
        {isLandingState ? (
          /* State 1: Landing (Hero) */
          <div className="flex-1 flex flex-col items-center justify-center py-12 sm:py-20 text-center max-w-3xl mx-auto w-full gap-8">
            <div className="flex flex-col items-center gap-3">
              <div className="w-16 h-16 rounded-3xl grad text-white grid place-items-center shadow-xl shadow-tekhelet/20 mb-2">
                <Icon name="search" className="text-[36px]" />
              </div>
              <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold text-tekhelet tracking-tight">
                {tr(lang, "searchLandingHero")}
              </h1>
              <p className="text-base sm:text-lg text-ink/75 max-w-xl leading-relaxed">
                {tr(lang, "searchLandingSubtitle")}
              </p>
            </div>

            {/* Central Large Search Bar */}
            <div className="w-full">
              <SearchBar
                initialQuery=""
                onSearch={handleSearchSubmit}
                lang={lang}
                autoFocus={true}
                size="large"
                className="mx-auto shadow-xl"
              />
            </div>

            {/* Suggested Searches Chips */}
            <div className="flex flex-col items-center gap-3 w-full">
              <span className="text-xs font-bold text-ink/45 uppercase tracking-wider">
                {tr(lang, "suggestedSearches")}
              </span>
              <div className="flex flex-wrap items-center justify-center gap-2 max-w-xl">
                {SUGGESTED_QUERIES[lang].map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => handleSearchSubmit(tag)}
                    className="glass rounded-full px-4 py-2 text-sm font-medium text-ink/80 hover:text-tekhelet hover:ring-2 hover:ring-gold/30 hover:scale-105 active:scale-95 transition-all duration-150 cursor-pointer shadow-sm"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* State 2: Results View */
          <div className="flex flex-col gap-6 w-full">
            {/* Search Bar at Top */}
            <div className="w-full max-w-4xl mx-auto flex flex-col gap-3">
              <SearchBar
                initialQuery={queryParam}
                onSearch={handleSearchSubmit}
                lang={lang}
                size="normal"
              />

              {/* Status Line: Results Count & Mobile Filter Button */}
              <div className="flex items-center justify-between gap-4 px-2">
                <div className="text-sm text-ink/70">
                  {loading ? (
                    <span className="inline-flex items-center gap-2 text-tekhelet font-medium">
                      <Icon name="hourglass_top" className="text-[18px] animate-spin" />
                      {tr(lang, "searching")}
                    </span>
                  ) : error === "rate_limit" ? (
                    <span className="text-amber-700 font-semibold">
                      {lang === "he"
                        ? "הגעת למגבלת קצב החיפושים (עד 120 בדקה). אנא המתן מעט ונסה שוב."
                        : "Rate limit reached (120 searches/min). Please wait a moment and try again."}
                    </span>
                  ) : error ? (
                    <span className="text-red-500 font-medium">
                      {tr(lang, "searchError")}
                    </span>
                  ) : totalResults > 0 ? (
                    <span>
                      {tr(lang, "resultsFound")
                        .replace("{count}", totalResults.toLocaleString())
                        .replace("{query}", queryParam)}
                    </span>
                  ) : (
                    <span>
                      {tr(lang, "noSearchResults").replace("{query}", queryParam)}
                    </span>
                  )}
                </div>

                {/* Mobile Filter Toggle Button */}
                <button
                  type="button"
                  onClick={() => setMobileFilterOpen(true)}
                  className="lg:hidden flex items-center gap-1.5 px-3 py-1.5 rounded-full glass text-xs font-semibold text-tekhelet hover:bg-white/80 transition"
                >
                  <Icon name="filter_list" className="text-[16px]" />
                  <span>{tr(lang, "searchFilter")}</span>
                  {selectedWorkIds.length > 0 && (
                    <span className="w-4 h-4 rounded-full bg-tekhelet text-white text-[10px] grid place-items-center font-bold">
                      {selectedWorkIds.length}
                    </span>
                  )}
                </button>
              </div>
            </div>

            {/* Mobile Filters Drawer / Modal */}
            {mobileFilterOpen && (
              <div className="fixed inset-0 z-50 lg:hidden flex flex-col justify-end bg-black/40 backdrop-blur-sm animate-in fade-in">
                <div className="glass rounded-t-[32px] p-6 max-h-[80vh] flex flex-col gap-4 bg-cream/95">
                  <div className="flex items-center justify-between border-b border-line/60 pb-3">
                    <span className="font-serif text-lg font-bold text-tekhelet">
                      {tr(lang, "searchFilter")}
                    </span>
                    <button
                      type="button"
                      onClick={() => setMobileFilterOpen(false)}
                      className="p-1 rounded-full text-ink/60 hover:text-ink"
                    >
                      <Icon name="close" className="text-[20px]" />
                    </button>
                  </div>
                  <FacetSidebar
                    facets={searchData?.facets ?? {}}
                    selectedWorkIds={selectedWorkIds}
                    onToggleWorkId={handleToggleWorkId}
                    onClearAll={handleClearAllFacets}
                    lang={lang}
                    className="border-none shadow-none p-0 sticky-none"
                  />
                  <button
                    type="button"
                    onClick={() => setMobileFilterOpen(false)}
                    className="w-full py-3 rounded-full grad text-white font-bold text-sm shadow-md"
                  >
                    {lang === "he" ? "החל סינון" : "Apply Filters"}
                  </button>
                </div>
              </div>
            )}

            {/* Two-Column Layout (Desktop) */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-start">
              {/* Desktop Sidebar (Right column in RTL, Left in LTR) */}
              <div className="hidden lg:block lg:col-span-1">
                <FacetSidebar
                  facets={searchData?.facets ?? {}}
                  selectedWorkIds={selectedWorkIds}
                  onToggleWorkId={handleToggleWorkId}
                  onClearAll={handleClearAllFacets}
                  lang={lang}
                />
              </div>

              {/* Main Column: Results Cards & Pagination */}
              <div className="col-span-1 lg:col-span-3 flex flex-col gap-4 min-w-0">
                {loading && !searchData ? (
                  /* Loading Skeletons */
                  <div className="flex flex-col gap-4">
                    {[1, 2, 3, 4].map((n) => (
                      <div
                        key={n}
                        className="glass rounded-2xl p-6 flex flex-col gap-3 animate-pulse"
                      >
                        <div className="h-6 bg-tekhelet/10 rounded w-1/3" />
                        <div className="h-4 bg-ink/10 rounded w-full" />
                        <div className="h-4 bg-ink/10 rounded w-5/6" />
                        <div className="h-4 bg-ink/5 rounded w-1/4 pt-2" />
                      </div>
                    ))}
                  </div>
                ) : error === "rate_limit" ? (
                  <div className="glass rounded-2xl p-8 text-center flex flex-col items-center gap-3 text-ink/80">
                    <Icon name="speed" className="text-[40px] text-gold" />
                    <h3 className="font-serif text-xl font-bold text-tekhelet">
                      {lang === "he" ? "חרגת ממגבלת הקצב" : "Rate limit exceeded"}
                    </h3>
                    <p className="text-sm max-w-md">
                      {lang === "he"
                        ? "מערכת החיפוש מאפשרת עד 120 חיפושים בדקה. אנא המתן מספר שניות ונסה שוב."
                        : "The search system permits up to 120 queries per minute. Please wait a few seconds and try again."}
                    </p>
                  </div>
                ) : searchData && searchData.hits.length > 0 ? (
                  /* Results List */
                  <div className="flex flex-col gap-4">
                    {searchData.hits.map((hit, idx) => (
                      <ResultCard
                        key={`${hit.work_id}-${hit.ref}-${idx}`}
                        hit={hit}
                        lang={lang}
                      />
                    ))}

                    {/* Pagination */}
                    <Pagination
                      currentPage={currentPage}
                      totalPages={totalPages}
                      onPageChange={handlePageChange}
                      lang={lang}
                      className="mt-4"
                    />
                  </div>
                ) : (
                  /* Empty State */
                  <div className="glass rounded-2xl p-12 text-center flex flex-col items-center justify-center gap-4 my-8">
                    <div className="w-14 h-14 rounded-2xl bg-tekhelet/5 text-tekhelet/50 grid place-items-center">
                      <Icon name="search_off" className="text-[32px]" />
                    </div>
                    <div className="flex flex-col gap-1 max-w-md">
                      <h3 className="font-serif text-xl font-bold text-tekhelet">
                        {tr(lang, "noSearchResults").replace("{query}", queryParam)}
                      </h3>
                      <p className="text-sm text-ink/60">
                        {lang === "he"
                          ? "נסו לחפש מילים נוספות, לבדוק את איות המילים או להסיר סינונים פעילים."
                          : "Try searching with different keywords, checking spelling, or clearing active filters."}
                      </p>
                    </div>
                    {selectedWorkIds.length > 0 && (
                      <button
                        type="button"
                        onClick={handleClearAllFacets}
                        className="px-4 py-2 rounded-full grad text-white text-xs font-semibold hover:opacity-95 transition shadow-sm"
                      >
                        {tr(lang, "clearAll")}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function SearchFallback() {
  return (
    <div className="h-dvh flex items-center justify-center">
      <div className="glass rounded-2xl p-8 flex items-center gap-3 text-tekhelet font-serif text-lg">
        <Icon name="hourglass_top" className="text-[24px] animate-spin" />
        <span>טוען...</span>
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<SearchFallback />}>
      <SearchContent />
    </Suspense>
  );
}
