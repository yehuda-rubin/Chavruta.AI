"use client";

import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "@/components/Icon";

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  lang: Lang;
  className?: string;
}

export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  lang,
  className = "",
}: PaginationProps) {
  if (totalPages <= 1) return null;

  // Generate page numbers with ellipsis
  const getPageNumbers = () => {
    const pages: (number | "ellipsis")[] = [];

    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      if (currentPage <= 4) {
        for (let i = 1; i <= 5; i++) {
          pages.push(i);
        }
        pages.push("ellipsis");
        pages.push(totalPages);
      } else if (currentPage >= totalPages - 3) {
        pages.push(1);
        pages.push("ellipsis");
        for (let i = totalPages - 4; i <= totalPages; i++) {
          pages.push(i);
        }
      } else {
        pages.push(1);
        pages.push("ellipsis");
        pages.push(currentPage - 1);
        pages.push(currentPage);
        pages.push(currentPage + 1);
        pages.push("ellipsis");
        pages.push(totalPages);
      }
    }

    return pages;
  };

  const pages = getPageNumbers();
  const hasPrev = currentPage > 1;
  const hasNext = currentPage < totalPages;

  return (
    <nav
      aria-label="Pagination"
      className={`flex items-center justify-center gap-1.5 sm:gap-2 flex-wrap py-6 ${className}`}
    >
      {/* Previous Button */}
      <button
        type="button"
        disabled={!hasPrev}
        onClick={() => onPageChange(currentPage - 1)}
        className="h-10 px-3 sm:px-4 rounded-xl glass flex items-center gap-1 text-sm font-medium text-ink/80 hover:text-tekhelet hover:bg-white/80 transition disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
        aria-label={tr(lang, "pagePrev")}
      >
        <Icon
          name={lang === "he" ? "chevron_right" : "chevron_left"}
          className="text-[20px]"
        />
        <span className="hidden sm:inline">{tr(lang, "pagePrev")}</span>
      </button>

      {/* Page Numbers */}
      {pages.map((p, idx) => {
        if (p === "ellipsis") {
          return (
            <span
              key={`ellipsis-${idx}`}
              className="w-8 sm:w-10 h-10 flex items-center justify-center text-ink/40 font-bold select-none"
            >
              …
            </span>
          );
        }

        const isActive = p === currentPage;

        return (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            aria-current={isActive ? "page" : undefined}
            className={`w-9 sm:w-10 h-10 rounded-xl text-sm font-semibold transition cursor-pointer flex items-center justify-center ${
              isActive
                ? "grad text-white shadow-md shadow-tekhelet/20 scale-105"
                : "glass text-ink/80 hover:text-tekhelet hover:bg-white/80"
            }`}
          >
            {p}
          </button>
        );
      })}

      {/* Next Button */}
      <button
        type="button"
        disabled={!hasNext}
        onClick={() => onPageChange(currentPage + 1)}
        className="h-10 px-3 sm:px-4 rounded-xl glass flex items-center gap-1 text-sm font-medium text-ink/80 hover:text-tekhelet hover:bg-white/80 transition disabled:opacity-30 disabled:pointer-events-none cursor-pointer"
        aria-label={tr(lang, "pageNext")}
      >
        <span className="hidden sm:inline">{tr(lang, "pageNext")}</span>
        <Icon
          name={lang === "he" ? "chevron_left" : "chevron_right"}
          className="text-[20px]"
        />
      </button>
    </nav>
  );
}
