"use client";

import { useEffect } from "react";
import type { Lang } from "@/lib/types";
import { Icon } from "@/components/Icon";

export type StudyMode = "clean" | "commentary" | "split" | "bilingual";

export interface StudyModeOption {
  id: StudyMode;
  labelHe: string;
  labelEn: string;
  shortLabelHe: string;
  shortLabelEn: string;
  descHe: string;
  descEn: string;
  icon: string;
}

export const STUDY_MODES: StudyModeOption[] = [
  {
    id: "clean",
    labelHe: "קריאה נקייה",
    labelEn: "Clean Reading",
    shortLabelHe: "נקייה",
    shortLabelEn: "Clean",
    descHe: "עמודת קריאה יחידה, שקטה ורציפה",
    descEn: "Clean single-column distraction-free reading",
    icon: "article",
  },
  {
    id: "commentary",
    labelHe: "מקראות גדולות / צורת הדף",
    labelEn: "Mikraot Gedolot / Commentaries",
    shortLabelHe: "מקראות גדולות",
    shortLabelEn: "Commentary",
    descHe: "טקסט עיקרי במרכז, עמודת מפרשים בצד",
    descEn: "Text in center, commentary column on the side",
    icon: "view_column",
  },
  {
    id: "split",
    labelHe: "חברותא צמודה",
    labelEn: "Side-by-side Chavruta",
    shortLabelHe: "חברותא צמודה",
    shortLabelEn: "Chavruta",
    descHe: "מסך מפוצל: 60% טקסט הספר, 40% צ'אט פעיל עם חברותא",
    descEn: "Split screen: 60% text reader, 40% active Chavruta chat",
    icon: "vertical_split",
  },
  {
    id: "bilingual",
    labelHe: "דו-לשוני",
    labelEn: "Bilingual (Hebrew / English)",
    shortLabelHe: "דו-לשוני",
    shortLabelEn: "Bilingual",
    descHe: "עברית ותרגום אנגלית זה לצד זה",
    descEn: "Hebrew and English translation side-by-side",
    icon: "translate",
  },
];

const STORAGE_KEY = "chavruta_study_mode";

export interface StudyModesBarProps {
  currentMode: StudyMode;
  onModeChange: (mode: StudyMode) => void;
  lang?: Lang;
  className?: string;
  compact?: boolean;
}

export function StudyModesBar({
  currentMode,
  onModeChange,
  lang = "he",
  className = "",
  compact = false,
}: StudyModesBarProps) {
  // Sync with localStorage on initial mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY) as StudyMode | null;
      if (saved && (saved === "clean" || saved === "commentary" || saved === "split" || saved === "bilingual")) {
        if (saved !== currentMode) {
          onModeChange(saved);
        }
      }
    } catch {}
  }, []);

  const handleSelectMode = (mode: StudyMode) => {
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {}
    onModeChange(mode);
  };

  const isRtl = lang === "he";

  return (
    <div
      dir={isRtl ? "rtl" : "ltr"}
      className={`glass rounded-2xl p-1.5 flex items-center gap-1 overflow-x-auto no-scrollbar ring-1 ring-line/50 shadow-xs ${className}`}
      role="tablist"
      aria-label={lang === "he" ? "מצבי לימוד בספרייה" : "Study Modes"}
    >
      <div className="hidden md:flex items-center gap-1 px-2 text-[11px] font-bold text-ink/40 uppercase tracking-wider shrink-0 select-none">
        <Icon name="tune" className="text-[14px]" />
        <span>{lang === "he" ? "מצב תצוגה:" : "View:"}</span>
      </div>

      {STUDY_MODES.map((mode) => {
        const isActive = currentMode === mode.id;
        const label = isRtl
          ? compact ? mode.shortLabelHe : mode.labelHe
          : compact ? mode.shortLabelEn : mode.labelEn;
        const description = isRtl ? mode.descHe : mode.descEn;

        return (
          <button
            key={mode.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => handleSelectMode(mode.id)}
            title={description}
            className={`group relative flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-serif transition-all duration-150 shrink-0 cursor-pointer ${
              isActive
                ? "bg-white/95 text-tekhelet shadow-sm ring-1 ring-gold/40 font-bold"
                : "text-ink/65 hover:text-tekhelet hover:bg-white/50"
            }`}
          >
            <Icon
              name={mode.icon}
              className={`text-[16px] transition-colors ${
                isActive ? "text-tekhelet" : "text-ink/45 group-hover:text-tekhelet"
              }`}
            />
            <span className="whitespace-nowrap">{label}</span>
            {isActive && (
              <span className="w-1.5 h-1.5 rounded-full bg-gold shrink-0 animate-in fade-in zoom-in-50 duration-200" />
            )}
          </button>
        );
      })}
    </div>
  );
}
