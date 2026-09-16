"use client";

import { useEffect, useRef, useState } from "react";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "@/components/Icon";

export interface SearchBarProps {
  initialQuery?: string;
  onSearch: (q: string) => void;
  lang: Lang;
  autoFocus?: boolean;
  size?: "normal" | "large";
  className?: string;
}

export function SearchBar({
  initialQuery = "",
  onSearch,
  lang,
  autoFocus = false,
  size = "normal",
  className = "",
}: SearchBarProps) {
  const [query, setQuery] = useState(initialQuery);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      onSearch(trimmed);
    }
  };

  const handleClear = () => {
    setQuery("");
    inputRef.current?.focus();
  };

  // Detect whether the query is Hebrew or Latin for direction
  const isHebrew = /[\u0590-\u05FF]/.test(query);
  const inputDir = query ? (isHebrew ? "rtl" : "ltr") : (lang === "he" ? "rtl" : "ltr");

  const isLarge = size === "large";

  return (
    <form
      onSubmit={handleSubmit}
      className={`glass rounded-full flex items-center gap-2 transition-all duration-200 ring-1 ring-white/60 focus-within:ring-2 focus-within:ring-tekhelet/30 shadow-lg shadow-tekhelet/5 ${
        isLarge ? "p-2 sm:p-2.5 max-w-2xl w-full" : "p-1.5 sm:p-2 w-full"
      } ${className}`}
    >
      <div className="flex items-center justify-center pl-3 pr-2 text-tekhelet/50 shrink-0">
        <Icon name="search" className={isLarge ? "text-[24px]" : "text-[20px]"} />
      </div>

      <input
        ref={inputRef}
        type="search"
        value={query}
        dir={inputDir}
        autoFocus={autoFocus}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={tr(lang, "searchPlaceholder")}
        aria-label={tr(lang, "searchPlaceholder")}
        className={`w-full bg-transparent border-none outline-none text-ink placeholder:text-ink/40 font-serif ${
          isLarge ? "text-lg sm:text-xl py-2" : "text-base py-1"
        }`}
      />

      {query && (
        <button
          type="button"
          onClick={handleClear}
          title={tr(lang, "clearSearch")}
          className="p-1.5 rounded-full text-ink/40 hover:text-ink hover:bg-black/5 transition shrink-0"
        >
          <Icon name="close" className="text-[18px]" />
        </button>
      )}

      <button
        type="submit"
        disabled={!query.trim()}
        className={`grad text-white font-medium rounded-full shrink-0 flex items-center justify-center gap-1.5 hover:opacity-95 active:scale-95 transition disabled:opacity-40 disabled:pointer-events-none shadow-md shadow-tekhelet/20 ${
          isLarge
            ? "px-6 py-2.5 text-base sm:text-lg"
            : "px-4 sm:px-5 py-2 text-sm sm:text-base"
        }`}
      >
        <span className="hidden sm:inline">{tr(lang, "searchLibrary")}</span>
        <Icon name="arrow_forward" className={`text-[18px] ${lang === "he" ? "rotate-180" : ""}`} />
      </button>
    </form>
  );
}
