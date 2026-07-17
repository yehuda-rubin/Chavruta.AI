"use client";
import { useEffect, useRef, useState } from "react";
import type { Lang, Message } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { commentatorTag, isHe, renderText } from "@/lib/format";
import { Icon } from "./Icon";

function Bubble({ m }: { m: Message }) {
  const dir = isHe(m.text) ? "he" : "en";
  if (m.role === "user") {
    return (
      <div className="flex gap-3.5 flex-row-reverse">
        <div className="h-9 w-9 rounded-2xl grad grid place-items-center text-white font-bold shrink-0">א</div>
        <div className="grad text-white rounded-3xl rounded-tl-md p-5 shadow-lg shadow-tekhelet/20 max-w-[80%]">
          <p className={`font-serif text-[17px] leading-loose ${dir}`} style={{ whiteSpace: "pre-wrap" }}>
            {m.text}
          </p>
        </div>
      </div>
    );
  }
  const tags = [...new Set((m.citations || []).map(commentatorTag))].filter(Boolean).slice(0, 4);
  return (
    <div className="flex gap-3.5">
      <div className="h-9 w-9 rounded-2xl bg-white/80 grid place-items-center text-tekhelet font-serif font-black shrink-0 shadow-sm">
        ח
      </div>
      <div className="bg-white/70 rounded-3xl rounded-tr-md p-5 shadow-sm ring-1 ring-white/60">
        <p className={`font-serif text-[18px] leading-loose ${dir}`} style={{ whiteSpace: "pre-wrap" }}>
          {renderText(m.text)}
        </p>
        {m.caveats?.map((c, i) => (
          <p key={i} className="mt-3 text-[13px] text-gold/90 bg-gold/5 rounded-xl px-3 py-2 leading-relaxed">
            {c}
          </p>
        ))}
        {tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {tags.map((t) => (
              <span key={t} className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-tekhelet/8 text-tekhelet">
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ChatPane({
  lang,
  messages,
  loading,
  onSend,
}: {
  lang: Lang;
  messages: Message[];
  loading: boolean;
  onSend: (text: string) => void;
}) {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim();
    if (!t || loading) return;
    onSend(t);
    setInput("");
  };

  return (
    <main className="flex-1 glass rounded-[28px] flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-8 py-8 flex flex-col gap-6 max-w-2xl mx-auto w-full">
        {messages.length === 0 ? (
          <div className="m-auto text-center px-6">
            <div className="h-16 w-16 rounded-3xl grad grid place-items-center text-white font-serif text-3xl font-black mx-auto mb-5 shadow-lg shadow-tekhelet/20">
              ח
            </div>
            <h2 className="font-serif text-3xl font-bold text-tekhelet mb-2">{tr(lang, "welcomeTitle")}</h2>
            <p className="text-ink/55 max-w-md mx-auto leading-relaxed">{tr(lang, "welcomeBody")}</p>
          </div>
        ) : (
          messages.map((m, i) => <Bubble key={m.id ?? i} m={m} />)
        )}
        {loading && (
          <div className="flex gap-3.5">
            <div className="h-9 w-9 rounded-2xl bg-white/80 grid place-items-center text-tekhelet font-serif font-black shrink-0 shadow-sm">
              ח
            </div>
            <div className="bg-white/70 rounded-3xl rounded-tr-md p-5 shadow-sm ring-1 ring-white/60 text-ink/50 font-serif">
              {tr(lang, "thinking")}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="p-5">
        <form
          onSubmit={submit}
          className="max-w-2xl mx-auto flex items-center gap-2 glass rounded-full px-3 py-2 focus-within:ring-2 focus-within:ring-indigo/30"
        >
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) submit(e);
            }}
            className="flex-1 bg-transparent outline-none font-serif text-[16px] placeholder:text-ink/35 resize-none leading-relaxed max-h-32 py-1"
            placeholder={tr(lang, "askPlaceholder")}
          />
          <button
            type="submit"
            disabled={loading}
            className="h-10 w-10 rounded-full grad text-white grid place-items-center hover:opacity-95 shadow-lg shadow-tekhelet/20 disabled:opacity-40"
            title={tr(lang, "send")}
          >
            <Icon name="arrow_upward" className="text-[20px]" />
          </button>
        </form>
        <p className="text-center text-[10px] text-ink/35 mt-2.5">{tr(lang, "footer")}</p>
      </div>
    </main>
  );
}
