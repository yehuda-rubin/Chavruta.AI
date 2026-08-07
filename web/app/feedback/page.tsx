"use client";
import { useState } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api";

// No `metadata` export: this is a Client Component (needs useState for the lang toggle + form
// state), same constraint documented in limits/page.tsx.
export default function Feedback() {
  const [lang, setLang] = useState<Lang>("he");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || status === "sending") return;
    setStatus("sending");
    try {
      await api.submitFeedback(t);
      setText("");
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  };

  return (
    <div dir={lang === "he" ? "rtl" : "ltr"} className="h-screen overflow-y-auto py-10 px-4">
      <article className="glass rounded-[28px] max-w-2xl mx-auto p-8 flex flex-col gap-5">
        <div className="flex items-center justify-between gap-3">
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold inline-flex items-center gap-1">
            <Icon name={lang === "he" ? "chevron_right" : "chevron_left"} className="text-[16px]" />
            {tr(lang, "backToApp")}
          </Link>
          <button
            onClick={() => setLang(lang === "he" ? "en" : "he")}
            className="px-3 py-1.5 rounded-full glass text-ink/70 text-xs font-semibold"
          >
            עברית · EN
          </button>
        </div>

        <header className="flex flex-col gap-1">
          <h1 className="font-serif text-3xl font-bold text-tekhelet">
            {tr(lang, "feedbackTitle")}
          </h1>
          <p className="text-sm text-ink/70 leading-relaxed">
            {tr(lang, "feedbackSubtitle")}
          </p>
        </header>

        {status === "sent" ? (
          <div className="rounded-2xl bg-tekhelet/5 ring-1 ring-tekhelet/15 p-4 text-sm text-tekhelet">
            {tr(lang, "feedbackThanks")}
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              maxLength={4000}
              placeholder={tr(lang, "feedbackPlaceholder")}
              className="w-full rounded-2xl glass px-4 py-3 text-sm font-serif outline-none ring-1 ring-transparent focus:ring-tekhelet/30 resize-none"
            />
            {status === "error" && (
              <p className="text-xs text-red-500">{tr(lang, "feedbackError")}</p>
            )}
            <button
              type="submit"
              disabled={!text.trim() || status === "sending"}
              className="self-start px-5 py-2.5 rounded-2xl grad text-white font-semibold text-sm hover:opacity-95 transition disabled:opacity-40"
            >
              {status === "sending" ? tr(lang, "feedbackSending") : tr(lang, "feedbackSend")}
            </button>
          </form>
        )}
      </article>
    </div>
  );
}
