"use client";
import { useEffect, useRef, useState } from "react";
import type { FileOut, Lang, Message } from "@/lib/types";
import { INTENT_LABEL, IntentId, tr } from "@/lib/i18n";
import { commentatorTag, isHe, renderText } from "@/lib/format";
import { downloadDoc } from "@/lib/doc";
import { Icon } from "./Icon";
import { IntentBar } from "./IntentBar";
import { LessonOptions, LessonFields } from "./LessonOptions";

function LessonFiles({ lang, files, onPreview }: { lang: Lang; files: FileOut[]; onPreview: (f: FileOut) => void }) {
  return (
    <>
      <p className="text-[11px] tracking-widest text-gold font-bold uppercase mb-2">{tr(lang, "lessonThreeFiles")}</p>
      <div className="flex flex-col gap-2">
        {files.map((f, idx) => (
          <div
            key={idx}
            onClick={() => onPreview(f)}
            className="fileCard flex items-center gap-3 w-full bg-white/70 hover:bg-white/95 ring-1 ring-line/70 rounded-2xl p-3.5 transition cursor-pointer"
          >
            <span className="h-10 w-10 rounded-xl grad grid place-items-center text-white shrink-0">
              <Icon name="description" />
            </span>
            <span className="flex-1 min-w-0">
              <span className="block font-serif font-bold text-tekhelet truncate">{f.name}</span>
              <span className="block text-[11px] text-ink/50">{tr(lang, "clickView")}</span>
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPreview(f);
              }}
              className="h-8 w-8 rounded-lg hover:bg-white grid place-items-center text-tekhelet shrink-0"
              title={tr(lang, "view")}
            >
              <Icon name="visibility" className="text-[20px]" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                downloadDoc(f.name, f.title || f.name.replace(/\.docx?$/, ""), f.content || "");
              }}
              className="h-8 w-8 rounded-lg hover:bg-white grid place-items-center text-gold shrink-0"
              title={tr(lang, "download")}
            >
              <Icon name="download" className="text-[20px]" />
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

function Bubble({ lang, m, onPreview }: { lang: Lang; m: Message; onPreview: (f: FileOut) => void }) {
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
  const hasFiles = m.files && m.files.length > 0;
  return (
    <div className="flex gap-3.5">
      <div className="h-9 w-9 rounded-2xl bg-white/80 grid place-items-center text-tekhelet font-serif font-black shrink-0 shadow-sm">
        ח
      </div>
      <div className={"bg-white/70 rounded-3xl rounded-tr-md p-5 shadow-sm ring-1 ring-white/60 " + (hasFiles ? "max-w-[85%] w-full" : "")}>
        {m.text && (
          <p className={`font-serif text-[18px] leading-loose ${dir} ${hasFiles ? "mb-3" : ""}`} style={{ whiteSpace: "pre-wrap" }}>
            {renderText(m.text)}
          </p>
        )}
        {hasFiles && <LessonFiles lang={lang} files={m.files!} onPreview={onPreview} />}
        {m.caveats?.map((c, i) => (
          <p key={i} className="mt-3 text-[13px] text-gold/90 bg-gold/5 rounded-xl px-3 py-2 leading-relaxed">
            {c}
          </p>
        ))}
        {!hasFiles && tags.length > 0 && (
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
  intent,
  locked,
  lessonFields,
  subtitle,
  onPickIntent,
  onLessonChange,
  onSend,
  onPreviewFile,
}: {
  lang: Lang;
  messages: Message[];
  loading: boolean;
  intent: IntentId;
  locked: boolean;
  lessonFields: LessonFields;
  subtitle: string;
  onPickIntent: (i: IntentId) => void;
  onLessonChange: (v: LessonFields) => void;
  onSend: (text: string) => void;
  onPreviewFile: (f: FileOut) => void;
}) {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Auto-grow the composer up to 128px, like the static UI's autogrow().
  useEffect(() => {
    const t = taRef.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 128) + "px";
  }, [input]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim();
    if (!t || loading) return;
    onSend(t);
    setInput("");
  };

  return (
    <main className="flex-1 glass rounded-[28px] flex flex-col overflow-hidden">
      <div className="px-7 py-4 flex items-center justify-between gap-3 border-b border-white/40">
        <div className="min-w-0">
          <h2 className="font-serif text-lg font-bold text-tekhelet">{tr(lang, "discussionTitle")}</h2>
          {subtitle && <p className="text-[10px] tracking-widest text-gold font-bold uppercase truncate">{subtitle}</p>}
        </div>
        <IntentBar lang={lang} intent={intent} locked={locked} onPick={onPickIntent} />
      </div>

      {intent === "lesson" && <LessonOptions lang={lang} value={lessonFields} onChange={onLessonChange} />}

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
          messages.map((m, i) => <Bubble key={m.id ?? i} lang={lang} m={m} onPreview={onPreviewFile} />)
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
          <span className="text-gold font-bold text-sm px-3 py-1.5 rounded-full select-none whitespace-nowrap">
            {INTENT_LABEL[lang][intent]}
          </span>
          <textarea
            ref={taRef}
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
