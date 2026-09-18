"use client";

import { useEffect, useRef, useState } from "react";
import type { Citation, Lang } from "@/lib/types";
import { api } from "@/lib/api";
import { commentatorTag, isHe } from "@/lib/format";
import { Icon } from "@/components/Icon";

export interface ActiveSourceContext {
  ref: string;
  book?: string;
  chapter?: string | number;
  segment?: string | number;
  text_he?: string;
  text_en?: string;
  snippet?: string;
}

export interface FloatingAskButtonProps {
  activeSource?: ActiveSourceContext;
  lang?: Lang;
  position?: "bottom-left" | "bottom-right";
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  caveats?: string[];
}

const QUICK_PROMPTS = {
  he: [
    "באר לי את הפשט כאן",
    "מה הקושי המרכזי בסוגיה?",
    "איך ההלכה נפסקה מכאן?",
  ],
  en: [
    "Explain the plain meaning here",
    "What is the central difficulty in this passage?",
    "How is the Halakha ruled from here?",
  ],
};

export function FloatingAskButton({
  activeSource,
  lang = "he",
  position = "bottom-right",
  isOpen: controlledIsOpen,
  onOpenChange,
  className = "",
}: FloatingAskButtonProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const isOpen = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen;

  const setOpen = (open: boolean) => {
    if (onOpenChange) {
      onOpenChange(open);
    } else {
      setInternalIsOpen(open);
    }
  };

  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [expandedCitation, setExpandedCitation] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll messages to bottom
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 100);
    }
  }, [isOpen]);

  const handleSend = async (textToSend?: string) => {
    const q = (textToSend !== undefined ? textToSend : input).trim();
    if (!q || loading) return;

    setInput("");
    setError(null);

    const userMessage: ChatMessage = {
      id: "u-" + Date.now(),
      role: "user",
      text: q,
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const attachments = activeSource?.ref
        ? [
            {
              kind: "text" as const,
              name: activeSource.ref,
              content:
                activeSource.text_he ||
                activeSource.snippet ||
                `מקור נלמד: ${activeSource.ref}`,
            },
          ]
        : undefined;

      if (!sessionId) {
        // Create new session via async job pipeline
        const created = await api.createSessionAsync(
          q,
          "chavruta",
          lang,
          undefined,
          attachments,
          (sid) => {
            setSessionId(sid);
          }
        );
        setSessionId(created.id);
        const res = created.result;
        setMessages((prev) => [
          ...prev,
          {
            id: "a-" + Date.now(),
            role: "assistant",
            text: res.answer,
            citations: res.citations || [],
            caveats: res.caveats || [],
          },
        ]);
      } else {
        // Continue existing discussion in this drawer
        const res = await api.sessionQueryAsync(
          sessionId,
          q,
          "chavruta",
          lang,
          undefined,
          attachments
        );
        setMessages((prev) => [
          ...prev,
          {
            id: "a-" + Date.now(),
            role: "assistant",
            text: res.answer,
            citations: res.citations || [],
            caveats: res.caveats || [],
          },
        ]);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : lang === "he"
          ? "אירעה שגיאה בקבלת תשובה מחברותא"
          : "An error occurred while contacting Chavruta";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const resetChat = () => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    setInput("");
  };

  const prompts = QUICK_PROMPTS[lang] || QUICK_PROMPTS.he;
  const isRtl = lang === "he";
  const posClasses =
    position === "bottom-left"
      ? "bottom-5 left-5 md:bottom-7 md:left-7"
      : "bottom-5 right-5 md:bottom-7 md:right-7";

  return (
    <>
      {/* Floating Action Button (FAB) */}
      {!isOpen && (
        <div className={`fixed ${posClasses} z-40 ${className}`}>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="group flex items-center gap-2 px-5 py-3.5 rounded-full grad text-white font-bold shadow-xl shadow-tekhelet/30 hover:shadow-2xl hover:scale-105 active:scale-95 transition-all duration-200 ring-2 ring-gold/40 backdrop-blur-md cursor-pointer"
            aria-label={lang === "he" ? "שאל את חברותא" : "Ask Chavruta"}
          >
            <span className="text-xl">💬</span>
            <span className="font-serif text-base tracking-wide">
              {lang === "he" ? "שאל את חברותא" : "Ask Chavruta"}
            </span>
            {activeSource?.ref && (
              <span className="hidden sm:inline-block max-w-[120px] truncate text-xs bg-white/20 px-2 py-0.5 rounded-full font-sans opacity-90">
                {activeSource.book || activeSource.ref}
              </span>
            )}
          </button>
        </div>
      )}

      {/* Backdrop for Mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 backdrop-blur-xs z-40 md:hidden animate-in fade-in duration-200"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Floating Slide-over Drawer */}
      {isOpen && (
        <aside
          dir={isRtl ? "rtl" : "ltr"}
          className={`fixed z-50 flex flex-col overflow-hidden bg-cream/95 backdrop-blur-xl border border-line/70 shadow-2xl transition-all duration-300 ${posClasses} w-full sm:w-[460px] h-[90vh] sm:h-[640px] max-h-[92vh] rounded-t-[28px] sm:rounded-[28px] animate-in slide-in-from-bottom-6`}
          role="dialog"
          aria-label="Chavruta Study Assistant"
        >
          {/* Header */}
          <div className="p-4 pb-3 border-b border-line/60 flex items-center justify-between bg-white/40">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xl">💬</span>
              <div className="min-w-0">
                <h3 className="font-serif text-lg font-bold text-tekhelet leading-tight">
                  {lang === "he" ? "שאל את חברותא" : "Ask Chavruta"}
                </h3>
                <p className="text-[11px] text-ink/55 truncate">
                  {lang === "he" ? "לימוד מונחה מקורות בזמן קריאה" : "Grounded study companion"}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1 shrink-0">
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={resetChat}
                  className="p-1.5 rounded-xl text-ink/50 hover:text-tekhelet hover:bg-white/60 transition text-xs flex items-center gap-1"
                  title={lang === "he" ? "התחל שיחה חדשה" : "New discussion"}
                >
                  <Icon name="refresh" className="text-[18px]" />
                </button>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-xl text-ink/50 hover:text-tekhelet hover:bg-white/60 transition"
                title={lang === "he" ? "סגור" : "Close"}
              >
                <Icon name="close" className="text-[20px]" />
              </button>
            </div>
          </div>

          {/* Active Source Context Tag */}
          <div className="px-4 py-2 bg-gold/10 border-b border-gold/20 flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-1.5 min-w-0 text-gold font-semibold truncate">
              <Icon name="auto_stories" className="text-[15px] shrink-0" />
              <span className="truncate">
                {activeSource?.ref
                  ? `${lang === "he" ? "הקשר נוכחי:" : "Context:"} ${activeSource.ref}`
                  : lang === "he"
                  ? "הקשר: כללי"
                  : "Context: General"}
              </span>
            </div>
            {activeSource?.book && (
              <span className="px-2 py-0.5 rounded-full bg-gold/15 text-gold text-[10px] font-bold shrink-0">
                {activeSource.book}
                {activeSource.chapter ? ` · ${activeSource.chapter}` : ""}
              </span>
            )}
          </div>

          {/* Messages Scroll Area */}
          <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3.5 text-sm">
            {messages.length === 0 && (
              <div className="flex-1 flex flex-col justify-center items-center text-center p-4 text-ink/60">
                <div className="w-12 h-12 rounded-2xl bg-tekhelet/10 text-tekhelet flex items-center justify-center text-2xl mb-3 shadow-inner">
                  🤝
                </div>
                <h4 className="font-serif text-base font-bold text-tekhelet mb-1">
                  {lang === "he" ? "לומדים יחד את הקטע" : "Studying together"}
                </h4>
                <p className="text-xs text-ink/60 max-w-xs mb-4">
                  {lang === "he"
                    ? "שאלו כל שאלה, קושיה או בקשת ביאור על הטקסט שמופיע כרגע בקריאה."
                    : "Ask any question, objection, or request for clarification on this text."}
                </p>

                {/* Quick Prompt Suggestions */}
                <div className="w-full flex flex-col gap-1.5 text-right">
                  <span className="text-[11px] font-bold text-ink/40 uppercase tracking-wider mb-0.5">
                    {lang === "he" ? "הצעות לשאלות מהירות:" : "Quick suggestions:"}
                  </span>
                  {prompts.map((promptText, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSend(promptText)}
                      className="w-full text-right py-2 px-3 rounded-xl bg-white/70 hover:bg-white hover:ring-1 hover:ring-gold/50 text-ink/85 text-xs font-serif transition flex items-center justify-between gap-2 shadow-xs group"
                    >
                      <span className="truncate">{promptText}</span>
                      <Icon
                        name={isRtl ? "chevron_left" : "chevron_right"}
                        className="text-[16px] text-ink/40 group-hover:text-tekhelet shrink-0"
                      />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, idx) => {
              const isUser = m.role === "user";
              return (
                <div
                  key={m.id || idx}
                  className={`flex flex-col ${
                    isUser ? "items-start" : "items-end"
                  }`}
                >
                  <div
                    className={`max-w-[88%] rounded-2xl px-4 py-3 leading-relaxed font-serif text-[14px] ${
                      isUser
                        ? "bg-tekhelet text-white shadow-md rounded-br-xs self-start"
                        : "bg-white/85 text-ink/90 border border-line/60 shadow-sm rounded-bl-xs self-end"
                    }`}
                    dir={isHe(m.text) ? "rtl" : "ltr"}
                  >
                    <div className="whitespace-pre-wrap">{m.text}</div>

                    {/* Citations List inside Assistant Bubble */}
                    {m.citations && m.citations.length > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-line/40 flex flex-col gap-1.5 font-sans">
                        <span className="text-[11px] font-bold text-gold uppercase tracking-wider flex items-center gap-1">
                          <Icon name="format_quote" className="text-[13px]" />
                          {lang === "he" ? "מקורות שצוטטו:" : "Cited sources:"}
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {m.citations.map((c, cIdx) => {
                            const isExpanded = expandedCitation === `${idx}-${cIdx}`;
                            return (
                              <div
                                key={cIdx}
                                className="w-full flex flex-col bg-white/60 rounded-lg p-2 border border-line/40 text-xs"
                              >
                                <button
                                  type="button"
                                  onClick={() =>
                                    setExpandedCitation(
                                      isExpanded ? null : `${idx}-${cIdx}`
                                    )
                                  }
                                  className="flex items-center justify-between text-tekhelet font-semibold hover:underline"
                                >
                                  <span className="truncate">
                                    {(lang !== "en" && c.ref_he) || c.ref}
                                    {commentatorTag(c) && ` · ${commentatorTag(c)}`}
                                  </span>
                                  <Icon
                                    name={isExpanded ? "expand_less" : "expand_more"}
                                    className="text-[16px] text-ink/50"
                                  />
                                </button>
                                {isExpanded && (
                                  <div className="mt-1.5 pt-1.5 border-t border-line/40 text-[12px] font-serif text-ink/80 leading-relaxed whitespace-pre-wrap">
                                    {c.text_he || c.text_en}
                                    {c.deep_link && (
                                      <div className="mt-1">
                                        <a
                                          href={c.deep_link}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-tekhelet inline-flex items-center gap-0.5 text-[11px] hover:underline"
                                        >
                                          {lang === "he" ? "צפה בספריא" : "View on Sefaria"}
                                          <Icon name="open_in_new" className="text-[11px]" />
                                        </a>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Loading Indicator */}
            {loading && (
              <div className="self-end max-w-[85%] bg-white/80 rounded-2xl px-4 py-3 border border-line/60 flex items-center gap-2.5 text-xs text-ink/60 shadow-sm animate-pulse">
                <span className="inline-block w-2 h-2 rounded-full bg-tekhelet animate-bounce" />
                <span
                  className="inline-block w-2 h-2 rounded-full bg-gold animate-bounce"
                  style={{ animationDelay: "150ms" }}
                />
                <span
                  className="inline-block w-2 h-2 rounded-full bg-tekhelet animate-bounce"
                  style={{ animationDelay: "300ms" }}
                />
                <span className="font-serif mr-1 ml-1">
                  {lang === "he"
                    ? "חברותא מעיין במקורות ומגבש תשובה..."
                    : "Chavruta is searching sources..."}
                </span>
              </div>
            )}

            {/* Error Banner */}
            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 text-xs flex items-center gap-2">
                <Icon name="error" className="text-[16px] shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompts Bar (when messages exist) */}
          {messages.length > 0 && !loading && (
            <div className="px-3 py-1.5 bg-white/30 border-t border-line/40 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
              <span className="text-[10px] text-ink/40 font-bold uppercase shrink-0">
                {lang === "he" ? "הצעות:" : "Quick:"}
              </span>
              {prompts.map((p, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleSend(p)}
                  className="whitespace-nowrap px-2.5 py-1 rounded-full text-[11px] bg-white/70 hover:bg-white hover:text-tekhelet text-ink/75 border border-line/40 transition shrink-0"
                >
                  {p}
                </button>
              ))}
            </div>
          )}

          {/* Chat Input Bar */}
          <div className="p-3 border-t border-line/60 bg-white/50">
            <div className="relative flex items-center bg-white rounded-2xl ring-1 ring-line/70 focus-within:ring-2 focus-within:ring-tekhelet/50 shadow-inner p-1.5">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder={
                  lang === "he"
                    ? "שאלו שאלה על הקטע הנלמד..."
                    : "Ask a question about this passage..."
                }
                disabled={loading}
                className="flex-1 bg-transparent resize-none px-3 py-1.5 text-sm text-ink/90 outline-none max-h-24 min-h-[38px] placeholder:text-ink/40 font-serif leading-normal"
              />
              <button
                type="button"
                onClick={() => handleSend()}
                disabled={!input.trim() || loading}
                className="h-9 w-9 rounded-xl grad text-white flex items-center justify-center shrink-0 hover:opacity-90 active:scale-95 disabled:opacity-40 disabled:hover:opacity-40 transition shadow-sm cursor-pointer"
                title={lang === "he" ? "שלח שאלה" : "Send question"}
              >
                <Icon
                  name={isRtl ? "send" : "send"}
                  className={`text-[18px] ${isRtl ? "rotate-180" : ""}`}
                />
              </button>
            </div>
            <div className="flex items-center justify-between text-[10px] text-ink/40 px-2 pt-1.5">
              <span>{lang === "he" ? "Enter לשליחה · Shift+Enter לשורה חדשה" : "Enter to send · Shift+Enter for newline"}</span>
              <span>{lang === "he" ? "מבוסס מקורות · ללא המצאות" : "Strictly grounded"}</span>
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
