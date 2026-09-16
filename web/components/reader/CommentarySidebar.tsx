"use client";

import { useEffect, useState } from "react";
import type { CommentaryItem, ReaderLinksResponse, ReaderSegment } from "@/lib/reader";
import { fetchReaderLinks, formatHebrewRef } from "@/lib/reader";
import { Icon } from "@/components/Icon";

export interface CommentarySidebarProps {
  activeSegment: ReaderSegment | null;
  open: boolean;
  onClose: () => void;
  initialTab?: "commentary" | "parallels";
  onAskChavrutaAboutCommentary?: (commentary: CommentaryItem) => void;
  onCopy?: (text: string, label: string) => void;
}

export function CommentarySidebar({
  activeSegment,
  open,
  onClose,
  initialTab = "commentary",
  onAskChavrutaAboutCommentary,
  onCopy,
}: CommentarySidebarProps) {
  const [activeTab, setActiveTab] = useState<"commentary" | "parallels">(initialTab);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ReaderLinksResponse | null>(null);
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});

  // Sync initialTab when provided
  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  // Fetch commentaries when active segment changes
  useEffect(() => {
    if (!open || !activeSegment) return;

    let isMounted = true;
    setLoading(true);

    fetchReaderLinks(activeSegment.ref)
      .then((res) => {
        if (isMounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [open, activeSegment]);

  // Handle escape key
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const commentaries = data?.commentaries ?? [];
  const parallels = data?.parallels ?? [];
  const activeList = activeTab === "commentary" ? commentaries : parallels;

  const toggleExpand = (id: string) => {
    setExpandedCards((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const segmentLabel = activeSegment ? formatHebrewRef(activeSegment.ref) : "";

  return (
    <>
      {/* Backdrop for mobile */}
      <div
        className="fixed inset-0 bg-ink/25 backdrop-blur-xs z-40 lg:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sidebar Drawer Panel */}
      <aside
        aria-label="סרגל מפרשים ומקבילות"
        className="fixed top-0 bottom-0 left-0 lg:left-auto lg:right-0 w-full sm:w-[420px] lg:w-[460px] glass bg-cream/95 backdrop-blur-xl border-r lg:border-r-0 lg:border-l border-white/60 shadow-2xl z-50 flex flex-col transition-transform duration-300 ease-in-out select-text"
      >
        {/* Top Header */}
        <div className="p-4 sm:p-5 border-b border-line/60 flex items-start justify-between gap-3 shrink-0 bg-white/40">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold text-tekhelet/70 uppercase tracking-wider">
              מפרשים ומקורות מקבילים
            </span>
            <h2 className="font-serif text-lg sm:text-xl font-bold text-tekhelet">
              {segmentLabel || "קטע נבחר"}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="סגור סרגל מפרשים"
            className="h-8 w-8 rounded-full glass grid place-items-center text-ink/60 hover:text-tekhelet hover:bg-white/80 transition cursor-pointer shrink-0"
          >
            <Icon name="close" className="text-[18px]" />
          </button>
        </div>

        {/* Selected Segment Excerpt Quote */}
        {activeSegment && (
          <div className="px-4 py-2.5 bg-gold/5 border-b border-gold/15 text-xs text-ink/80 leading-relaxed font-serif line-clamp-2 italic">
            &quot;{activeSegment.text_he}&quot;
          </div>
        )}

        {/* Tabs: מפרשים vs קשרים ומקבילות */}
        <div className="flex items-center border-b border-line/60 shrink-0 bg-white/30 px-2 pt-2 gap-1">
          <button
            type="button"
            onClick={() => setActiveTab("commentary")}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-t-xl text-xs sm:text-sm font-semibold transition border-b-2 cursor-pointer ${
              activeTab === "commentary"
                ? "border-tekhelet text-tekhelet bg-white/60 shadow-xs"
                : "border-transparent text-ink/65 hover:text-tekhelet hover:bg-white/30"
            }`}
          >
            <span>מפרשים</span>
            <span
              className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                activeTab === "commentary"
                  ? "bg-tekhelet/15 text-tekhelet"
                  : "bg-ink/10 text-ink/60"
              }`}
            >
              {commentaries.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("parallels")}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-t-xl text-xs sm:text-sm font-semibold transition border-b-2 cursor-pointer ${
              activeTab === "parallels"
                ? "border-indigo text-indigo bg-white/60 shadow-xs"
                : "border-transparent text-ink/65 hover:text-indigo hover:bg-white/30"
            }`}
          >
            <span>קשרים ומקבילות</span>
            <span
              className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                activeTab === "parallels"
                  ? "bg-indigo/15 text-indigo"
                  : "bg-ink/10 text-ink/60"
              }`}
            >
              {parallels.length}
            </span>
          </button>
        </div>

        {/* List of Commentaries or Parallels */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 flex flex-col gap-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-tekhelet">
              <Icon name="hourglass_top" className="text-[28px] animate-spin" />
              <span className="text-sm font-medium">טוען מפרשים ומקבילות…</span>
            </div>
          ) : activeList.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-ink/50 gap-2">
              <Icon name="library_books" className="text-[32px] text-ink/30" />
              <p className="text-sm font-medium">
                {activeTab === "commentary"
                  ? "לא נמצאו מפרשים עבור קטע זה."
                  : "לא נמצאו מקבילות ישירות עבור קטע זה."}
              </p>
            </div>
          ) : (
            activeList.map((item) => {
              const isExpanded = !!expandedCards[item.id];
              const isLongText = item.text_he.length > 240;
              const displayText =
                isLongText && !isExpanded
                  ? item.text_he.slice(0, 240) + "…"
                  : item.text_he;

              return (
                <article
                  key={item.id}
                  className="glass rounded-2xl p-4 sm:p-5 border border-white/70 shadow-sm flex flex-col gap-3 transition hover:shadow-md"
                >
                  {/* Card Header: Commentator + Type */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-col">
                      <h3 className="font-serif text-base sm:text-lg font-bold text-tekhelet">
                        {item.commentator}
                      </h3>
                      {item.ref && (
                        <span className="text-[11px] text-ink/50 font-mono">
                          {item.ref}
                        </span>
                      )}
                    </div>

                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gold/10 text-gold border border-gold/20 shrink-0">
                      {item.type === "commentary"
                        ? "מפרש"
                        : item.type === "halacha"
                        ? "הלכה"
                        : item.type === "midrash"
                        ? "מדרש"
                        : "מקבילה"}
                    </span>
                  </div>

                  {/* Commentary Text (Rashi Script / Traditional Serif style) */}
                  <div className="font-serif text-sm sm:text-base leading-relaxed text-ink/90 bg-white/45 p-3 sm:p-3.5 rounded-xl border border-line/40 whitespace-pre-wrap selection:bg-gold/20">
                    {displayText}
                  </div>

                  {/* Truncation toggle */}
                  {isLongText && (
                    <button
                      type="button"
                      onClick={() => toggleExpand(item.id)}
                      className="self-start text-xs font-semibold text-indigo hover:text-tekhelet transition cursor-pointer flex items-center gap-1"
                    >
                      <Icon
                        name={isExpanded ? "expand_less" : "expand_more"}
                        className="text-[16px]"
                      />
                      <span>{isExpanded ? "הצג פחות" : "קרא עוד"}</span>
                    </button>
                  )}

                  {/* Bottom Footer: License + Actions */}
                  <div className="flex items-center justify-between gap-2 pt-2 border-t border-line/40 text-xs">
                    <span className="text-[11px] text-ink/50 truncate">
                      {item.license || "נחלת הכלל"}
                      {item.version ? ` · ${item.version}` : ""}
                    </span>

                    <div className="flex items-center gap-1 shrink-0">
                      {onAskChavrutaAboutCommentary && (
                        <button
                          type="button"
                          onClick={() => onAskChavrutaAboutCommentary(item)}
                          className="px-2 py-1 rounded-lg text-xs font-semibold text-tekhelet hover:bg-gold/15 transition cursor-pointer flex items-center gap-1"
                          title="שאל את חברותא על פירוש זה"
                        >
                          <span>🤖</span>
                          <span className="hidden sm:inline">שאל</span>
                        </button>
                      )}

                      {onCopy && (
                        <button
                          type="button"
                          onClick={() =>
                            onCopy(
                              `${item.text_he}\n(${item.commentator}, ${item.ref})`,
                              item.commentator
                            )
                          }
                          className="h-7 w-7 rounded-lg glass grid place-items-center text-ink/60 hover:text-tekhelet transition cursor-pointer"
                          title="העתק פירוש"
                        >
                          <Icon name="content_copy" className="text-[14px]" />
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </div>
      </aside>
    </>
  );
}
