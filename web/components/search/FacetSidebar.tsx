"use client";

import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { CANONICAL_CATEGORIES, CATEGORY_LABELS } from "@/lib/search";
import { Icon } from "@/components/Icon";

export interface FacetSidebarProps {
  facets: Record<string, number>;
  selectedWorkIds: string[];
  onToggleWorkId: (workId: string) => void;
  onClearAll: () => void;
  lang: Lang;
  className?: string;
}

export function FacetSidebar({
  facets,
  selectedWorkIds,
  onToggleWorkId,
  onClearAll,
  lang,
  className = "",
}: FacetSidebarProps) {
  // Filter categories to show those with results or currently selected,
  // ordered canonically.
  const categoriesWithCounts = CANONICAL_CATEGORIES.map((catId) => {
    const count = facets[catId] ?? 0;
    const isSelected = selectedWorkIds.includes(catId);
    const label = CATEGORY_LABELS[lang]?.[catId] || catId;
    return { id: catId, label, count, isSelected };
  });

  // Categories with count > 0 or selected
  const visibleCategories = categoriesWithCounts.filter(
    (c) => c.count > 0 || c.isSelected
  );

  const hasSelected = selectedWorkIds.length > 0;

  return (
    <aside
      className={`glass rounded-[28px] p-5 flex flex-col gap-4 sticky top-6 self-start shadow-sm border border-white/60 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line/60 pb-3">
        <div className="flex items-center gap-2 text-tekhelet font-serif text-lg font-bold">
          <Icon name="filter_list" className="text-[20px]" />
          <span>{tr(lang, "searchFilter")}</span>
        </div>
        {hasSelected && (
          <button
            type="button"
            onClick={onClearAll}
            className="text-xs text-indigo hover:text-tekhelet font-medium transition cursor-pointer"
          >
            {tr(lang, "clearAll")}
          </button>
        )}
      </div>

      {/* Categories Checklist */}
      <div className="flex flex-col gap-1.5 max-h-[70vh] overflow-y-auto pr-1">
        {visibleCategories.length === 0 ? (
          <p className="text-xs text-ink/50 py-2">
            {tr(lang, "noContent")}
          </p>
        ) : (
          visibleCategories.map(({ id, label, count, isSelected }) => {
            return (
              <label
                key={id}
                className={`flex items-center justify-between gap-2 px-3 py-2 rounded-xl cursor-pointer transition text-sm select-none ${
                  isSelected
                    ? "bg-tekhelet/10 text-tekhelet font-semibold"
                    : "hover:bg-white/50 text-ink/80"
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleWorkId(id)}
                    className="w-4 h-4 rounded border-line text-tekhelet focus:ring-tekhelet cursor-pointer accent-tekhelet"
                  />
                  <span className="truncate text-sm">{label}</span>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-mono shrink-0 ${
                    isSelected
                      ? "bg-tekhelet text-white font-bold"
                      : "bg-ink/5 text-ink/60"
                  }`}
                >
                  {count.toLocaleString()}
                </span>
              </label>
            );
          })
        )}
      </div>
    </aside>
  );
}
