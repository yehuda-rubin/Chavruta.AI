"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/Modal";
import { Icon } from "@/components/Icon";
import { formatHebrewRef } from "@/lib/reader";

export interface AskChavrutaModalProps {
  open: boolean;
  onClose: () => void;
  segmentRef: string;
  segmentText: string;
  selectedText?: string;
  commentatorName?: string;
}

const QUICK_PROMPTS = [
  "הסבר לי קטע זה במילים פשוטות ובהירות",
  "מה הקושי או השאלה המרכזית שמתעוררת כאן?",
  "כיצד המפרשים העיקריים מבארים את העניין?",
  "מה ההשלכה ההלכתית או הרעיונית הנלמדת מכאן?",
];

export function AskChavrutaModal({
  open,
  onClose,
  segmentRef,
  segmentText,
  selectedText,
  commentatorName,
}: AskChavrutaModalProps) {
  const router = useRouter();
  const [customPrompt, setCustomPrompt] = useState("");

  if (!open) return null;

  const quoteText = selectedText || segmentText;
  const hebrewRef = formatHebrewRef(segmentRef);
  const contextLabel = commentatorName
    ? `${commentatorName} על ${hebrewRef}`
    : hebrewRef;

  const handleSubmit = (promptToUse?: string) => {
    const finalPrompt = promptToUse || customPrompt.trim() || QUICK_PROMPTS[0];
    const fullQuery = `במקור ${contextLabel} נאמר: "${quoteText}".\n\nשאלה: ${finalPrompt}`;

    // Store in sessionStorage so home page chat can pick it up or pass via URL
    try {
      sessionStorage.setItem("chavruta_initial_query", fullQuery);
    } catch {}

    const sp = new URLSearchParams();
    sp.set("q", finalPrompt);
    sp.set("context_ref", segmentRef);

    router.push(`/?${sp.toString()}`);
    onClose();
  };

  return (
    <Modal
      open={open}
      title="שאל את חברותא על קטע זה"
      onClose={onClose}
      maxW="max-w-xl"
    >
      <div className="flex flex-col gap-4 text-sm">
        {/* Source Quote Header */}
        <div className="bg-white/50 border border-line/60 rounded-2xl p-4 flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs text-tekhelet font-semibold">
            <span>מקור מצוטט: {contextLabel}</span>
            <span className="text-ink/40 font-mono text-[11px]">{segmentRef}</span>
          </div>
          <p className="font-serif text-base text-ink/90 italic leading-relaxed line-clamp-3">
            &quot;{quoteText}&quot;
          </p>
        </div>

        {/* Quick Suggestion Chips */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold text-ink/60 uppercase tracking-wide">
            שאלות נפוצות לעיון:
          </span>
          <div className="flex flex-col gap-1.5">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => handleSubmit(prompt)}
                className="glass rounded-xl px-3.5 py-2 text-right text-xs sm:text-sm font-medium text-ink/85 hover:text-tekhelet hover:bg-gold/15 transition flex items-center justify-between group cursor-pointer"
              >
                <span>{prompt}</span>
                <Icon
                  name="arrow_forward"
                  className="text-[16px] text-ink/40 group-hover:text-tekhelet group-hover:translate-x-[-2px] transition-transform rtl:rotate-180"
                />
              </button>
            ))}
          </div>
        </div>

        {/* Custom Input */}
        <div className="flex flex-col gap-2 pt-2 border-t border-line/50">
          <label htmlFor="custom-prompt-input" className="text-xs font-bold text-ink/60 uppercase tracking-wide">
            או כתוב שאלה אישית:
          </label>
          <textarea
            id="custom-prompt-input"
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            placeholder="שאל את החברותא כל שאלה על לשון המקור, הסבר, השוואה או הלכה…"
            rows={3}
            className="w-full rounded-xl bg-white/70 border border-line/70 p-3 text-sm text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-tekhelet/30 font-sans resize-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (customPrompt.trim()) handleSubmit();
              }
            }}
          />
        </div>

        {/* Submit & Cancel Buttons */}
        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold text-ink/60 hover:text-ink transition cursor-pointer"
          >
            ביטול
          </button>
          <button
            type="button"
            onClick={() => handleSubmit()}
            className="px-5 py-2 rounded-xl grad text-white font-semibold text-xs sm:text-sm shadow-md hover:opacity-95 transition cursor-pointer flex items-center gap-1.5"
          >
            <span>פתח דיון בחברותא</span>
            <Icon name="arrow_forward" className="text-[16px] rtl:rotate-180" />
          </button>
        </div>
      </div>
    </Modal>
  );
}
