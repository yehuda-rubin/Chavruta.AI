"use client";

import { useEffect, useRef, useState } from "react";
import type { ReaderSegment } from "@/lib/reader";
import { formatHebrewRef } from "@/lib/reader";
import { Icon } from "@/components/Icon";

export interface ContextMenuProps {
  x: number;
  y: number;
  segment: ReaderSegment;
  selectedText?: string;
  onClose: () => void;
  onAskChavruta: (segment: ReaderSegment, selectedText?: string) => void;
  onOpenCommentary: (segment: ReaderSegment, tab: "commentary" | "parallels") => void;
  onSearchPhrase: (phrase: string) => void;
  onCopyCitation: (segment: ReaderSegment, selectedText?: string) => void;
}

export function ContextMenu({
  x,
  y,
  segment,
  selectedText,
  onClose,
  onAskChavruta,
  onOpenCommentary,
  onSearchPhrase,
  onCopyCitation,
}: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: y, left: x });

  // Adjust position to stay inside viewport boundaries
  useEffect(() => {
    if (!menuRef.current) return;
    const rect = menuRef.current.getBoundingClientRect();
    const padding = 12;

    let adjustedLeft = x;
    let adjustedTop = y;

    // Check right edge
    if (adjustedLeft + rect.width > window.innerWidth - padding) {
      adjustedLeft = window.innerWidth - rect.width - padding;
    }
    // Check left edge
    if (adjustedLeft < padding) {
      adjustedLeft = padding;
    }
    // Check bottom edge
    if (adjustedTop + rect.height > window.innerHeight - padding) {
      adjustedTop = window.innerHeight - rect.height - padding;
    }
    // Check top edge
    if (adjustedTop < padding) {
      adjustedTop = padding;
    }

    setPos({ top: adjustedTop, left: adjustedLeft });
  }, [x, y]);

  // Clean dismissal on outside click, window blur, scroll, or Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };

    const handleMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    const handleScroll = () => {
      onClose();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("mousedown", handleMouseDown, true);
    window.addEventListener("scroll", handleScroll, true);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("mousedown", handleMouseDown, true);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [onClose]);

  const searchTargetPhrase = (selectedText && selectedText.trim()) || segment.text_he.slice(0, 40);
  const displayLabel = formatHebrewRef(segment.ref);

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label="תפריט קטע"
      style={{
        position: "fixed",
        top: `${pos.top}px`,
        left: `${pos.left}px`,
        zIndex: 60,
      }}
      className="glass rounded-2xl shadow-2xl border border-white/70 py-1.5 px-1 min-w-[240px] max-w-[300px] text-ink animate-in fade-in zoom-in-95 duration-100 select-none"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Segment Header */}
      <div className="px-3 py-1.5 border-b border-line/50 mb-1 flex items-center justify-between">
        <span className="font-serif font-bold text-xs text-tekhelet truncate">
          {displayLabel}
        </span>
        <span className="text-[10px] text-ink/40 font-mono">
          {segment.ref}
        </span>
      </div>

      {/* Menu Actions */}
      <div className="flex flex-col gap-0.5 text-xs sm:text-sm">
        {/* 1. Ask Chavruta */}
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onAskChavruta(segment, selectedText);
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-right hover:bg-gold/15 hover:text-tekhelet transition-colors group cursor-pointer font-medium"
        >
          <span className="text-[16px] leading-none shrink-0 text-gold group-hover:scale-110 transition-transform">
            🤖
          </span>
          <span className="flex-1">שאל את חברותא על קטע זה</span>
        </button>

        {/* 2. Show Commentaries */}
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onOpenCommentary(segment, "commentary");
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-right hover:bg-gold/15 hover:text-tekhelet transition-colors group cursor-pointer font-medium"
        >
          <span className="text-[16px] leading-none shrink-0 text-tekhelet group-hover:scale-110 transition-transform">
            📖
          </span>
          <span className="flex-1">הצג מפרשים על המקום</span>
          {segment.commentary_count ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-tekhelet/10 text-tekhelet font-semibold">
              {segment.commentary_count}
            </span>
          ) : null}
        </button>

        {/* 3. Show Related & Parallels */}
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onOpenCommentary(segment, "parallels");
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-right hover:bg-gold/15 hover:text-tekhelet transition-colors group cursor-pointer font-medium"
        >
          <span className="text-[16px] leading-none shrink-0 text-indigo group-hover:scale-110 transition-transform">
            🔗
          </span>
          <span className="flex-1">מקורות קשורים ומקבילות</span>
        </button>

        <div className="h-px bg-line/60 my-1 mx-2" />

        {/* 4. Search Phrase in Library */}
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onSearchPhrase(searchTargetPhrase);
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-right hover:bg-gold/15 hover:text-tekhelet transition-colors group cursor-pointer font-medium"
        >
          <span className="text-[16px] leading-none shrink-0 text-ink/70 group-hover:scale-110 transition-transform">
            🔍
          </span>
          <span className="flex-1 truncate">חפש ביטוי זה בספרייה</span>
        </button>

        {/* 5. Copy with Citation */}
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            onCopyCitation(segment, selectedText);
            onClose();
          }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-right hover:bg-gold/15 hover:text-tekhelet transition-colors group cursor-pointer font-medium"
        >
          <span className="text-[16px] leading-none shrink-0 text-ink/70 group-hover:scale-110 transition-transform">
            📋
          </span>
          <span className="flex-1">העתק עם מראה מקום</span>
        </button>
      </div>
    </div>
  );
}
