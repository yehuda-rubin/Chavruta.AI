"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import type { ReaderSegment, ReaderUnit } from "@/lib/reader";
import {
  fetchReaderUnit,
  formatHebrewRef,
  stripHebrewVowels,
} from "@/lib/reader";
import { Icon } from "@/components/Icon";
import { ContextMenu } from "@/components/reader/ContextMenu";
import { CommentarySidebar } from "@/components/reader/CommentarySidebar";
import { AskChavrutaModal } from "@/components/reader/AskChavrutaModal";
import { FloatingAskButton } from "@/components/reader/FloatingAskButton";

type StudyMode = "text_only" | "bilingual" | "with_commentary";
type FontSizeLevel = "sm" | "md" | "lg" | "xl";

const FONT_SIZES: Record<FontSizeLevel, { text: string; label: string }> = {
  sm: { text: "text-lg sm:text-xl leading-relaxed", label: "קטן" },
  md: { text: "text-xl sm:text-2xl leading-loose", label: "רגיל" },
  lg: { text: "text-2xl sm:text-3xl leading-loose", label: "גדול" },
  xl: { text: "text-3xl sm:text-4xl leading-loose", label: "מוגדל" },
};

function ReaderInner() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const { user, loading: authLoading } = useAuth();

  // ── Access Gate: Admin or Private Beta Check ──────────────────────────────
  const [accessAllowed, setAccessAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    // 1. Check URL query parameter `?beta=true`
    if (searchParams.get("beta") === "true") {
      try {
        localStorage.setItem("chavruta_beta_tester", "true");
      } catch {}
      setAccessAllowed(true);
      return;
    }

    // 2. Check localStorage flag
    try {
      if (localStorage.getItem("chavruta_beta_tester") === "true") {
        setAccessAllowed(true);
        return;
      }
    } catch {}

    // 3. Check user admin status from /me API
    let isMounted = true;
    api
      .me()
      .then((me) => {
        if (isMounted) {
          if (me.is_admin) {
            setAccessAllowed(true);
          } else {
            setAccessAllowed(false);
          }
        }
      })
      .catch(() => {
        if (isMounted) {
          setAccessAllowed(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [searchParams]);

  // ── URL & Ref Resolution ──────────────────────────────────────────────────
  const refParts = Array.isArray(params?.ref)
    ? params.ref
    : params?.ref
    ? [params.ref]
    : [];

  const rawRef = decodeURIComponent(refParts.join("."))
    .replace(/\//g, ".")
    .trim() || "Genesis.1";

  // ── Reader State ──────────────────────────────────────────────────────────
  const [lang, setLang] = useState<Lang>("he");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [unit, setUnit] = useState<ReaderUnit | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Reader Settings
  const [studyMode, setStudyMode] = useState<StudyMode>("text_only");
  const [fontSize, setFontSize] = useState<FontSizeLevel>("md");

  // Active Segment & Interaction
  const [activeSegmentRef, setActiveSegmentRef] = useState<string | null>(null);

  // Context Menu State
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean;
    x: number;
    y: number;
    segment: ReaderSegment | null;
    selectedText?: string;
  }>({
    visible: false,
    x: 0,
    y: 0,
    segment: null,
  });

  // Long press timer ref for mobile
  const longPressTimer = useRef<NodeJS.Timeout | null>(null);

  // Commentary Sidebar State
  const [commentaryOpen, setCommentaryOpen] = useState(false);
  const [commentaryTab, setCommentaryTab] = useState<"commentary" | "parallels">("commentary");

  // Ask Chavruta Modal State
  const [askModalOpen, setAskModalOpen] = useState(false);
  const [askModalTarget, setAskModalTarget] = useState<{
    segmentRef: string;
    segmentText: string;
    selectedText?: string;
    commentatorName?: string;
  } | null>(null);

  // Toast Notification
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const showToast = (msg: string) => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setToastMessage(msg);
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 2500);
  };

  // Sync lang and theme from localStorage
  useEffect(() => {
    try {
      const savedLang = localStorage.getItem("chavruta-lang");
      if (savedLang === "en" || savedLang === "he") setLang(savedLang);
      const isDark = document.body.classList.contains("theme-dark");
      setTheme(isDark ? "dark" : "light");
    } catch {}
  }, []);

  // Fetch unit when rawRef changes
  useEffect(() => {
    if (!accessAllowed) return;

    let isMounted = true;
    setLoading(true);
    setError(null);

    fetchReaderUnit(rawRef)
      .then((data) => {
        if (isMounted) {
          setUnit(data);
          setLoading(false);
          // Auto-select first segment or specific segment if ref had 3 parts
          if (data.segments && data.segments.length > 0) {
            const matchSeg = data.segments.find((s) => s.ref === rawRef);
            if (matchSeg) {
              setActiveSegmentRef(matchSeg.ref);
            } else {
              setActiveSegmentRef(data.segments[0].ref);
            }
          }
        }
      })
      .catch((err) => {
        if (isMounted) {
          setLoading(false);
          setError("UNIT_LOAD_ERROR");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [rawRef, accessAllowed]);

  // If studyMode is "with_commentary", keep commentary sidebar open
  useEffect(() => {
    if (studyMode === "with_commentary") {
      setCommentaryOpen(true);
    }
  }, [studyMode]);

  // ── Context Menu Triggers ─────────────────────────────────────────────────
  const openContextMenuAt = (
    clientX: number,
    clientY: number,
    segment: ReaderSegment,
    selectedText?: string
  ) => {
    setActiveSegmentRef(segment.ref);
    setContextMenu({
      visible: true,
      x: clientX,
      y: clientY,
      segment,
      selectedText,
    });
  };

  const handleSegmentContextMenu = (
    e: React.MouseEvent,
    segment: ReaderSegment
  ) => {
    e.preventDefault();
    const selection = window.getSelection()?.toString().trim();
    openContextMenuAt(e.clientX, e.clientY, segment, selection || undefined);
  };

  const handleTouchStart = (
    e: React.TouchEvent,
    segment: ReaderSegment
  ) => {
    const touch = e.touches[0];
    if (!touch) return;
    const clientX = touch.clientX;
    const clientY = touch.clientY;

    longPressTimer.current = setTimeout(() => {
      openContextMenuAt(clientX, clientY, segment);
    }, 500);
  };

  const handleTouchEndOrMove = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  // ── Context Menu Actions ──────────────────────────────────────────────────
  const handleAskChavruta = (
    segment: ReaderSegment,
    selectedText?: string
  ) => {
    setAskModalTarget({
      segmentRef: segment.ref,
      segmentText: segment.text_he,
      selectedText,
    });
    setAskModalOpen(true);
  };

  const handleOpenCommentary = (
    segment: ReaderSegment,
    tab: "commentary" | "parallels"
  ) => {
    setActiveSegmentRef(segment.ref);
    setCommentaryTab(tab);
    setCommentaryOpen(true);
  };

  const handleSearchPhrase = (phrase: string) => {
    const clean = phrase.trim().slice(0, 80);
    router.push(`/search?q=${encodeURIComponent(clean)}`);
  };

  const handleCopyCitation = (
    segment: ReaderSegment,
    selectedText?: string
  ) => {
    const textToCopy = selectedText || segment.text_he;
    const citation = `${textToCopy}\n(${formatHebrewRef(segment.ref)})`;

    if (navigator.clipboard) {
      navigator.clipboard
        .writeText(citation)
        .then(() => showToast("📋 הועתק ללוח עם מראה מקום"))
        .catch(() => showToast("📋 הטקסט הועתק"));
    } else {
      showToast("📋 הטקסט הועתק");
    }
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

  // ── 1. Gating State: Private Beta Check ───────────────────────────────────
  if (accessAllowed === null) {
    return (
      <div className="h-dvh flex items-center justify-center bg-cream selection:bg-gold/20">
        <div className="flex flex-col items-center gap-3 text-tekhelet">
          <Icon name="hourglass_top" className="text-[32px] animate-spin" />
          <span className="text-sm font-medium font-sans">מאמת הרשאות גישה…</span>
        </div>
      </div>
    );
  }

  if (accessAllowed === false) {
    return (
      <div
        dir="rtl"
        className="h-dvh flex flex-col items-center justify-center p-6 bg-cream selection:bg-gold/20"
      >
        <div className="glass rounded-3xl p-8 sm:p-10 max-w-lg w-full text-center flex flex-col items-center gap-6 shadow-2xl border border-white/70">
          <div className="w-16 h-16 rounded-3xl grad text-white grid place-items-center shadow-lg shadow-tekhelet/20">
            <Icon name="lock" className="text-[32px]" />
          </div>

          <div className="flex flex-col gap-2">
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-tekhelet">
              הספרייה נמצאת כעת בבדיקות בטא פרטיות
            </h1>
            <p className="text-sm sm:text-base text-ink/75 leading-relaxed font-sans">
              מוצר הספרייה והקריאה הרציפה פתוח כעת למנהלים ולבודקי בטא מורשים בלבד. בקרוב הספרייה תיפתח לכלל לומדי חברותא.
            </p>
          </div>

          <div className="pt-2 w-full flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/"
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl grad text-white font-semibold text-sm shadow-md hover:opacity-95 transition text-center flex items-center justify-center gap-2"
            >
              <Icon name="arrow_forward" className="text-[18px] rtl:rotate-180" />
              <span>חזרה לדף הבית</span>
            </Link>

            <Link
              href="/search"
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl glass text-ink/80 hover:text-tekhelet font-semibold text-sm transition text-center flex items-center justify-center gap-2"
            >
              <Icon name="search" className="text-[18px]" />
              <span>חיפוש בספרייה</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // ── 2. Full Reader View ───────────────────────────────────────────────────
  const activeSegment =
    unit?.segments.find((s) => s.ref === activeSegmentRef) ||
    unit?.segments[0] ||
    null;

  return (
    <div
      dir="rtl"
      className="min-h-dvh flex flex-col bg-cream text-ink selection:bg-gold/25"
    >
      {/* Sticky Reader Navigation Header */}
      <header className="sticky top-0 z-30 glass border-b border-white/60 backdrop-blur-xl shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-[64px] flex items-center justify-between gap-4">
          {/* Left / Start: Back Button, Brand & Breadcrumb */}
          <div className="flex items-center gap-2 sm:gap-3 overflow-hidden">
            {/* Back Button */}
            <button
              type="button"
              onClick={() => {
                if (typeof window !== "undefined" && window.history.length > 1) {
                  router.back();
                } else {
                  router.push("/search");
                }
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl glass hover:bg-tekhelet/10 text-xs sm:text-sm font-bold text-tekhelet border border-tekhelet/20 transition shrink-0 cursor-pointer shadow-xs"
              title={lang === "he" ? "חזרה אחורה" : "Go back"}
            >
              <span className="text-sm font-bold">←</span>
              <span>{lang === "he" ? "חזרה" : "Back"}</span>
            </button>

            <Link
              href="/"
              className="flex items-center gap-2 shrink-0 hover:opacity-85 transition"
              title="חזרה לחברותא"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo.png"
                alt="חברותא"
                className="h-8 w-auto object-contain"
              />
            </Link>

            <span className="text-ink/25 font-light shrink-0">/</span>

            {/* Breadcrumbs: חטיבה > ספר > פרק/דף */}
            <nav
              aria-label="פירורי לחם לניווט"
              className="flex items-center gap-1.5 text-xs sm:text-sm font-serif truncate"
            >
              <Link
                href="/search"
                className="text-ink/65 hover:text-tekhelet transition shrink-0"
              >
                ספרייה
              </Link>
              <span className="text-ink/30 text-xs">›</span>

              {unit?.category && (
                <>
                  <Link
                    href={`/search?work_id=${encodeURIComponent(unit.category)}`}
                    className="text-ink/65 hover:text-tekhelet transition shrink-0 hidden sm:inline"
                  >
                    {unit.category === "tanakh"
                      ? 'תנ"ך'
                      : unit.category === "gemara"
                      ? "תלמוד בבלי"
                      : unit.category}
                  </Link>
                  <span className="text-ink/30 text-xs hidden sm:inline">›</span>
                </>
              )}

              <span className="font-bold text-tekhelet truncate">
                {unit?.book_he || unit?.book || rawRef.split(".")[0]}
              </span>

              {unit?.section_name && (
                <>
                  <span className="text-ink/30 text-xs">›</span>
                  <span className="font-semibold text-gold truncate">
                    {unit.section_name}
                  </span>
                </>
              )}
            </nav>
          </div>

          {/* Center: Prev / Next Chapter Navigation */}
          <div className="flex items-center gap-1 shrink-0">
            {unit?.prev_ref ? (
              <Link
                href={`/search/read/${unit.prev_ref}`}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl glass hover:bg-white/80 text-xs sm:text-sm font-semibold text-tekhelet transition cursor-pointer"
                title="פרק / דף קודם"
              >
                <Icon name="chevron_right" className="text-[18px]" />
                <span className="hidden md:inline">קודם</span>
              </Link>
            ) : (
              <button
                type="button"
                disabled
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-xs sm:text-sm font-semibold text-ink/30 opacity-40 cursor-not-allowed"
              >
                <Icon name="chevron_right" className="text-[18px]" />
                <span className="hidden md:inline">קודם</span>
              </button>
            )}

            {unit?.next_ref ? (
              <Link
                href={`/search/read/${unit.next_ref}`}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl glass hover:bg-white/80 text-xs sm:text-sm font-semibold text-tekhelet transition cursor-pointer"
                title="פרק / דף הבא"
              >
                <span className="hidden md:inline">הבא</span>
                <Icon name="chevron_left" className="text-[18px]" />
              </Link>
            ) : (
              <button
                type="button"
                disabled
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-xs sm:text-sm font-semibold text-ink/30 opacity-40 cursor-not-allowed"
              >
                <span className="hidden md:inline">הבא</span>
                <Icon name="chevron_left" className="text-[18px]" />
              </button>
            )}
          </div>

          {/* Right: Study Modes & Controls */}
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            {/* Study Mode Selector Pills */}
            <div className="hidden md:flex items-center p-1 rounded-full glass border border-line/60 gap-1 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setStudyMode("text_only")}
                className={`px-3 py-1 rounded-full transition cursor-pointer ${
                  studyMode === "text_only"
                    ? "grad text-white shadow-xs"
                    : "text-ink/70 hover:text-tekhelet"
                }`}
              >
                טקסט בלבד
              </button>
              <button
                type="button"
                onClick={() => setStudyMode("bilingual")}
                className={`px-3 py-1 rounded-full transition cursor-pointer ${
                  studyMode === "bilingual"
                    ? "grad text-white shadow-xs"
                    : "text-ink/70 hover:text-tekhelet"
                }`}
              >
                דו-לשוני
              </button>
              <button
                type="button"
                onClick={() => {
                  setStudyMode("with_commentary");
                  setCommentaryOpen(true);
                }}
                className={`px-3 py-1 rounded-full transition cursor-pointer ${
                  studyMode === "with_commentary"
                    ? "grad text-white shadow-xs"
                    : "text-ink/70 hover:text-tekhelet"
                }`}
              >
                טקסט ומפרשים
              </button>
            </div>

            {/* Font Size Selector */}
            <div className="flex items-center glass rounded-xl p-0.5 border border-line/50">
              <button
                type="button"
                onClick={() => {
                  const order: FontSizeLevel[] = ["sm", "md", "lg", "xl"];
                  const idx = order.indexOf(fontSize);
                  if (idx > 0) setFontSize(order[idx - 1]);
                }}
                disabled={fontSize === "sm"}
                className="h-8 w-8 rounded-lg grid place-items-center text-xs font-bold text-ink/70 hover:text-tekhelet disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                title="הקטן גופן"
              >
                א-
              </button>
              <button
                type="button"
                onClick={() => {
                  const order: FontSizeLevel[] = ["sm", "md", "lg", "xl"];
                  const idx = order.indexOf(fontSize);
                  if (idx < order.length - 1) setFontSize(order[idx + 1]);
                }}
                disabled={fontSize === "xl"}
                className="h-8 w-8 rounded-lg grid place-items-center text-xs font-bold text-ink/70 hover:text-tekhelet disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                title="הגדל גופן"
              >
                א+
              </button>
            </div>

            {/* Commentary Drawer Toggle Button */}
            <button
              type="button"
              onClick={() => setCommentaryOpen(!commentaryOpen)}
              className={`h-9 px-3 rounded-xl glass text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                commentaryOpen
                  ? "bg-tekhelet/15 text-tekhelet border-tekhelet/40 font-bold"
                  : "text-ink/70 hover:text-tekhelet"
              }`}
              title="פתח סרגל מפרשים"
            >
              <Icon name="library_books" className="text-[18px]" />
              <span className="hidden sm:inline">מפרשים</span>
            </button>

            {/* Theme Toggle */}
            <button
              type="button"
              onClick={toggleTheme}
              className="h-9 w-9 rounded-full glass grid place-items-center text-ink/70 hover:text-tekhelet transition cursor-pointer"
              title={theme === "dark" ? "מצב בהיר" : "מצב כהה"}
            >
              <Icon
                name={theme === "dark" ? "light_mode" : "dark_mode"}
                className="text-[18px]"
              />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Layout */}
      <div className="flex-1 flex w-full max-w-7xl mx-auto relative">
        {/* Main Text Study Area */}
        <main
          className={`flex-1 flex flex-col px-4 sm:px-8 py-8 sm:py-12 transition-all duration-300 ${
            commentaryOpen ? "lg:mr-0 lg:ml-[460px]" : ""
          }`}
        >
          {loading ? (
            <div className="flex-1 flex flex-col items-center justify-center py-24 gap-3 text-tekhelet">
              <Icon name="hourglass_top" className="text-[36px] animate-spin" />
              <span className="font-serif text-lg">טוען טקסט לימוד…</span>
            </div>
          ) : error ? (
            <div className="flex-1 flex flex-col items-center justify-center py-20 text-center gap-4 max-w-md mx-auto">
              <div className="w-14 h-14 rounded-full bg-red-50 text-red-600 grid place-items-center">
                <Icon name="error" className="text-[28px]" />
              </div>
              <h2 className="font-serif text-2xl font-bold text-tekhelet">
                לא ניתן היה לטעון את היחידה
              </h2>
              <p className="text-sm text-ink/70 font-sans">
                ייתכן שמראה המקום אינו קיים במאגר או שיש שגיאת תקשורת עם השרת.
              </p>
              <Link
                href="/search"
                className="px-5 py-2 rounded-xl grad text-white text-sm font-semibold shadow-md hover:opacity-95 transition"
              >
                חזרה לחיפוש בספרייה
              </Link>
            </div>
          ) : unit ? (
            <article className="max-w-3xl w-full mx-auto flex flex-col gap-6 sm:gap-8">
              {/* Unit Title Header */}
              <div className="text-center pb-6 border-b border-line/60 flex flex-col items-center gap-2">
                <span className="text-xs font-semibold text-tekhelet/70 uppercase tracking-widest">
                  {unit.category_path || unit.category}
                </span>
                <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold text-tekhelet tracking-tight">
                  {unit.book_he || unit.book} · {unit.section_name}
                </h1>
                <p className="text-xs text-ink/40 font-mono">
                  {unit.ref}
                </p>
              </div>

              {/* Continuous Segments Flow */}
              <div className="flex flex-col gap-4 sm:gap-6">
                {unit.segments.map((seg, idx) => {
                  const isActive = activeSegmentRef === seg.ref;
                  const hebrewText = stripHebrewVowels(seg.text_he);

                  return (
                    <div
                      key={seg.ref}
                      id={seg.ref}
                      onClick={() => setActiveSegmentRef(seg.ref)}
                      onContextMenu={(e) => handleSegmentContextMenu(e, seg)}
                      onTouchStart={(e) => handleTouchStart(e, seg)}
                      onTouchEnd={handleTouchEndOrMove}
                      onTouchMove={handleTouchEndOrMove}
                      className={`group relative p-4 sm:p-6 rounded-2xl transition-all duration-200 cursor-pointer ${
                        isActive
                          ? "bg-gold/10 ring-2 ring-gold/40 shadow-sm"
                          : "hover:bg-white/50 hover:shadow-xs"
                      }`}
                    >
                      {/* Segment Header / Meta Line */}
                      <div className="flex items-center justify-between gap-3 mb-2 select-none">
                        <div className="flex items-center gap-2">
                          {/* Verse / Segment Number Badge */}
                          <span
                            className={`w-7 h-7 rounded-full text-xs font-serif font-bold grid place-items-center transition ${
                              isActive
                                ? "grad text-white shadow-xs"
                                : "bg-gold/15 text-gold group-hover:bg-gold/25"
                            }`}
                            title={`קטע ${seg.label}`}
                          >
                            {seg.label}
                          </span>

                          <span className="text-xs font-serif text-ink/40 font-medium">
                            {formatHebrewRef(seg.ref)}
                          </span>
                        </div>

                        {/* Hover Actions & 3-dots Menu Button */}
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {seg.commentary_count ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenCommentary(seg, "commentary");
                              }}
                              className="px-2 py-1 rounded-lg text-xs font-semibold text-tekhelet bg-white/70 hover:bg-white shadow-xs transition flex items-center gap-1"
                              title="פתח מפרשים"
                            >
                              <Icon name="library_books" className="text-[14px]" />
                              <span>{seg.commentary_count}</span>
                            </button>
                          ) : null}

                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openContextMenuAt(e.clientX, e.clientY, seg);
                            }}
                            className="h-7 w-7 rounded-lg glass grid place-items-center text-ink/60 hover:text-tekhelet hover:bg-white transition"
                            title="פעולות נוספות (קליק ימני)"
                          >
                            <Icon name="more_vert" className="text-[16px]" />
                          </button>
                        </div>
                      </div>

                      {/* Hebrew Segment Text */}
                      <p
                        className={`font-serif font-normal text-ink/95 selection:bg-gold/30 ${FONT_SIZES[fontSize].text}`}
                      >
                        {hebrewText}
                      </p>

                      {/* Bilingual Translation (if mode enabled) */}
                      {studyMode === "bilingual" && seg.text_en && (
                        <div
                          dir="ltr"
                          className="mt-3 pt-3 border-t border-line/40 font-sans text-sm sm:text-base text-ink/75 leading-relaxed selection:bg-indigo/20 italic"
                        >
                          {seg.text_en}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* End of Chapter Navigation Bar */}
              <div className="mt-8 pt-8 border-t border-line/60 flex items-center justify-between flex-wrap gap-4">
                {unit.prev_ref ? (
                  <Link
                    href={`/search/read/${unit.prev_ref}`}
                    className="px-5 py-2.5 rounded-xl glass hover:bg-white/80 text-sm font-semibold text-tekhelet transition flex items-center gap-2"
                  >
                    <Icon name="chevron_right" className="text-[20px]" />
                    <span>פרק / דף קודם</span>
                  </Link>
                ) : (
                  <div />
                )}

                {unit.next_ref && (
                  <Link
                    href={`/search/read/${unit.next_ref}`}
                    className="px-5 py-2.5 rounded-xl grad text-white text-sm font-semibold shadow-md hover:opacity-95 transition flex items-center gap-2"
                  >
                    <span>פרק / דף הבא</span>
                    <Icon name="chevron_left" className="text-[20px]" />
                  </Link>
                )}
              </div>
            </article>
          ) : null}
        </main>

        {/* Commentary Sidebar Panel */}
        <CommentarySidebar
          activeSegment={activeSegment}
          open={commentaryOpen}
          onClose={() => setCommentaryOpen(false)}
          initialTab={commentaryTab}
          onAskChavrutaAboutCommentary={(item) => {
            if (activeSegment) {
              setAskModalTarget({
                segmentRef: activeSegment.ref,
                segmentText: item.text_he,
                commentatorName: item.commentator,
              });
              setAskModalOpen(true);
            }
          }}
          onCopy={(text, label) => {
            if (navigator.clipboard) {
              navigator.clipboard
                .writeText(text)
                .then(() => showToast(`📋 פירוש ${label} הועתק ללוח`));
            }
          }}
        />
      </div>

      {/* Floating Context Menu */}
      {contextMenu.visible && contextMenu.segment && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          segment={contextMenu.segment}
          selectedText={contextMenu.selectedText}
          onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
          onAskChavruta={handleAskChavruta}
          onOpenCommentary={handleOpenCommentary}
          onSearchPhrase={handleSearchPhrase}
          onCopyCitation={handleCopyCitation}
        />
      )}

      {/* Ask Chavruta Modal */}
      {askModalOpen && askModalTarget && (
        <AskChavrutaModal
          open={askModalOpen}
          onClose={() => setAskModalOpen(false)}
          segmentRef={askModalTarget.segmentRef}
          segmentText={askModalTarget.segmentText}
          selectedText={askModalTarget.selectedText}
          commentatorName={askModalTarget.commentatorName}
        />
      )}

      {/* Floating Ask Chavruta Button (FAB) */}
      {unit && (
        <FloatingAskButton
          lang={lang}
          position="bottom-right"
          activeSource={(() => {
            const seg = unit.segments.find((s) => s.ref === activeSegmentRef) || unit.segments[0];
            return seg
              ? {
                  ref: seg.ref,
                  book: unit.book,
                  text_he: seg.text_he,
                  text_en: seg.text_en || undefined,
                }
              : {
                  ref: unit.ref,
                  book: unit.book,
                };
          })()}
        />
      )}

      {/* Toast Notification */}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 glass bg-tekhelet/90 text-white px-5 py-2.5 rounded-full text-xs sm:text-sm font-semibold shadow-xl flex items-center gap-2 animate-in fade-in slide-in-from-bottom-3 duration-200"
        >
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}

export default function ReaderPage() {
  return (
    <Suspense
      fallback={
        <div className="h-dvh flex items-center justify-center bg-cream">
          <div className="flex flex-col items-center gap-3 text-tekhelet">
            <Icon name="hourglass_top" className="text-[32px] animate-spin" />
            <span className="text-sm font-medium">טוען ספרייה…</span>
          </div>
        </div>
      }
    >
      <ReaderInner />
    </Suspense>
  );
}
