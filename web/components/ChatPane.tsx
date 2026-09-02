"use client";
import { useEffect, useRef, useState } from "react";
import type { Attachment, FileOut, Lang, Message } from "@/lib/types";
import { EXAMPLES, IntentId, tr } from "@/lib/i18n";
import { commentatorTag, isHe, renderText } from "@/lib/format";
import { downloadDoc, printHtmlContent } from "@/lib/doc";
import { api } from "@/lib/api";
import { Icon } from "./Icon";
import { HelperPrompt } from "./HelperPrompt";
import { IntentBar } from "./IntentBar";
import { LessonOptions, LessonFields } from "./LessonOptions";

// Flags a specific answer for operator review — the self-serve half of the defamation/quality
// safety net noted in docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md Finding C: grounding reduces but
// does not eliminate the risk of a mischaracterizing answer, so a quick report path is how one
// actually gets noticed. Self-contained state, same pattern as SettingsModal's ChangePasswordField.
function ReportButton({ lang, messageId }: { lang: Lang; messageId: number }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  if (sent) {
    return <span className="mt-3 text-xs text-ink/40 inline-flex items-center gap-1">
      <Icon name="check" className="text-[15px]" />{tr(lang, "reportSent")}
    </span>;
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-3 text-xs text-ink/40 hover:text-tekhelet inline-flex items-center gap-1 transition"
      >
        <Icon name="flag" className="text-[15px]" />
        {tr(lang, "reportAnswer")}
      </button>
    );
  }

  const submit = async () => {
    setBusy(true);
    try {
      await api.reportMessage(messageId, reason);
      setSent(true);
    } catch {
      setSent(true); // don't trap the user in a retry loop over a best-effort report
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 flex flex-col gap-1.5">
      <input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={tr(lang, "reportPlaceholder")}
        className="text-xs bg-white/70 rounded-lg px-2.5 py-1.5 ring-1 ring-line/60 outline-none"
      />
      <div className="flex gap-3">
        <button onClick={submit} disabled={busy} className="text-xs text-tekhelet font-semibold hover:underline disabled:opacity-50">
          {tr(lang, "reportSubmit")}
        </button>
        <button onClick={() => setOpen(false)} className="text-xs text-ink/40 hover:text-tekhelet">
          {tr(lang, "reportCancel")}
        </button>
      </div>
    </div>
  );
}

function LessonFiles({ lang, files, onPreview }: { lang: Lang; files: FileOut[]; onPreview: (f: FileOut) => void }) {
  return (
    <>
      <p className="text-[11px] tracking-widest text-gold font-bold uppercase mb-2">{tr(lang, "lessonThreeFiles")}</p>
      <div className="flex flex-col gap-2">
        {files.map((f, idx) => {
          const isHtml = f.name.toLowerCase().endsWith(".html");
          const isMd = f.name.toLowerCase().endsWith(".md");
          const iconName = isHtml ? "print" : isMd ? "menu_book" : "description";

          return (
            <div
              key={idx}
              onClick={() => onPreview(f)}
              className="fileCard flex items-center gap-3 w-full bg-white/70 hover:bg-white/95 ring-1 ring-line/70 rounded-2xl p-3.5 transition cursor-pointer"
            >
              <span className="h-10 w-10 rounded-xl grad grid place-items-center text-white shrink-0 shadow-sm">
                <Icon name={iconName} className="text-[20px]" />
              </span>
              <span className="flex-1 min-w-0">
                <span className="block font-serif font-bold text-tekhelet truncate">{f.title || f.name}</span>
                <span className="block text-[11px] text-ink/50 truncate">{f.name}</span>
              </span>
              {isHtml && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    printHtmlContent(f.content || "");
                  }}
                  className="h-8 w-8 rounded-lg hover:bg-white grid place-items-center text-tekhelet shrink-0 shadow-xs"
                  title={tr(lang, "printPdf")}
                >
                  <Icon name="print" className="text-[20px]" />
                </button>
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onPreview(f);
                }}
                className="h-8 w-8 rounded-lg hover:bg-white grid place-items-center text-tekhelet shrink-0 shadow-xs"
                title={tr(lang, "view")}
              >
                <Icon name="visibility" className="text-[20px]" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  downloadDoc(f.name, f.title || f.name.replace(/\.docx?$/, ""), f.content || "");
                }}
                className="h-8 w-8 rounded-lg hover:bg-white grid place-items-center text-gold shrink-0 shadow-xs"
                title={tr(lang, "download")}
              >
                <Icon name="download" className="text-[20px]" />
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
}

function Bubble({ lang, m, onPreview, userInitial }: { lang: Lang; m: Message; onPreview: (f: FileOut) => void; userInitial: string }) {
  const dir = isHe(m.text) ? "he" : "en";
  const [copied, setCopied] = useState(false);
  if (m.role === "user") {
    return (
      <div className="flex gap-3.5 flex-row-reverse">
        <div className="h-9 w-9 rounded-2xl grad grid place-items-center text-white font-bold shrink-0">{userInitial}</div>
        <div className="grad text-white rounded-3xl rounded-tl-md p-5 shadow-lg shadow-tekhelet/20 max-w-[80%]">
          <p className={`font-serif text-[17px] leading-loose ${dir}`} style={{ whiteSpace: "pre-wrap" }}>
            {m.text}
          </p>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(m.text).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }).catch(() => {});
            }}
            aria-label={tr(lang, "copy")}
            className="mt-3 text-xs text-white/70 hover:text-white inline-flex items-center gap-1 transition"
          >
            <Icon name={copied ? "check" : "content_copy"} className="text-[15px]" />
            {tr(lang, copied ? "copied" : "copy")}
          </button>
        </div>
      </div>
    );
  }
  const tags = [...new Set((m.citations || []).map(commentatorTag))].filter(Boolean).slice(0, 4);
  const hasFiles = m.files && m.files.length > 0;
  return (
    <div className="flex gap-3.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="חברותא" className="h-8 w-8 object-contain shrink-0 mt-1" />
      <div className={"bg-white/70 rounded-3xl rounded-tr-md p-5 shadow-sm ring-1 ring-white/60 " + (hasFiles ? "max-w-[85%] w-full" : "")}>
        {m.text && (
          <p className={`font-serif text-[18px] leading-loose ${dir} ${hasFiles ? "mb-3" : ""}`} style={{ whiteSpace: "pre-wrap" }}>
            {renderText(m.text)}
          </p>
        )}
        {hasFiles && <LessonFiles lang={lang} files={m.files!} onPreview={onPreview} />}
        {!hasFiles && tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {tags.map((t) => (
              <span key={t} className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-tekhelet/8 text-tekhelet">
                {t}
              </span>
            ))}
          </div>
        )}
        {m.text && (
          <div className="flex items-center gap-4 flex-wrap">
            <button
              onClick={() => {
                navigator.clipboard?.writeText(m.text).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }).catch(() => {});
              }}
              aria-label={tr(lang, "copy")}
              className="mt-3 text-xs text-ink/40 hover:text-tekhelet inline-flex items-center gap-1 transition"
            >
              <Icon name={copied ? "check" : "content_copy"} className="text-[15px]" />
              {tr(lang, copied ? "copied" : "copy")}
            </button>
            {m.id != null && <ReportButton lang={lang} messageId={m.id} />}
          </div>
        )}
      </div>
    </div>
  );
}

function SourceSheetHero({
  lang,
  userSources = [],
  onAddSource,
  onPickExample,
}: {
  lang: Lang;
  userSources?: Attachment[];
  onAddSource?: () => void;
  onPickExample: (ex: string) => void;
}) {
  const examples = [
    tr(lang, "sourcesheetEx1"),
    tr(lang, "sourcesheetEx2"),
    tr(lang, "sourcesheetEx3"),
  ];

  return (
    <div className="m-auto text-center px-4 max-w-xl">
      <div className="inline-flex items-center justify-center h-16 w-16 rounded-3xl grad text-white shadow-lg shadow-tekhelet/20 mb-4">
        <Icon name="description" className="text-3xl" />
      </div>
      <h2 className="font-serif text-3xl font-bold text-tekhelet mb-2">
        {tr(lang, "sourcesheetHeroTitle")}
      </h2>
      <p className="text-ink/65 text-sm leading-relaxed mb-6">
        {tr(lang, "sourcesheetHeroSubtitle")}
      </p>

      {/* 3 Step Instruction flow */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-start mb-6">
        <div className="glass rounded-2xl p-3 bg-white/60">
          <div className="text-[11px] font-bold text-gold uppercase mb-1">
            {tr(lang, "sourcesheetStep1")}
          </div>
          <p className="text-xs text-ink/60">PDF, Word או הדבקת טקסט</p>
        </div>
        <div className="glass rounded-2xl p-3 bg-white/60">
          <div className="text-[11px] font-bold text-gold uppercase mb-1">
            {tr(lang, "sourcesheetStep2")}
          </div>
          <p className="text-xs text-ink/60">סיכום, שאלות, השוואת שיטות</p>
        </div>
        <div className="glass rounded-2xl p-3 bg-white/60">
          <div className="text-[11px] font-bold text-gold uppercase mb-1">
            {tr(lang, "sourcesheetStep3")}
          </div>
          <p className="text-xs text-ink/60">תרשים זרימה וחוברת מלאה</p>
        </div>
      </div>

      {/* Upload action & current sources badge */}
      {userSources.length > 0 ? (
        <div className="mb-6 p-3.5 rounded-2xl bg-emerald-50/80 ring-1 ring-emerald-300/60 flex items-center justify-between gap-3 text-start">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="h-8 w-8 rounded-xl bg-emerald-500 text-white grid place-items-center shrink-0">
              <Icon name="check" className="text-[18px]" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-bold text-emerald-900 truncate">
                {userSources.map((s) => s.name).join(", ")}
              </p>
              <p className="text-[11px] text-emerald-700">
                {tr(lang, "sourcesheetUploadedBadge")} ({userSources.length})
              </p>
            </div>
          </div>
          {onAddSource && (
            <button
              onClick={onAddSource}
              className="text-xs font-semibold text-emerald-800 hover:underline shrink-0"
            >
              + {tr(lang, "addSource")}
            </button>
          )}
        </div>
      ) : (
        onAddSource && (
          <div className="mb-6">
            <button
              onClick={onAddSource}
              className="w-full py-3.5 px-6 rounded-2xl grad text-white font-bold text-base hover:opacity-95 transition shadow-lg shadow-tekhelet/20 flex items-center justify-center gap-2.5 cursor-pointer"
            >
              <Icon name="upload_file" className="text-xl" />
              {tr(lang, "sourcesheetUploadBtn")}
            </button>
          </div>
        )
      )}

      {/* Example Prompt suggestions */}
      <p className="text-xs text-ink/45 mb-2.5 font-medium">
        {tr(lang, "sourcesheetExamplesLabel")}
      </p>
      <div className="flex flex-col gap-2">
        {examples.map((ex, idx) => (
          <button
            key={idx}
            onClick={() => onPickExample(ex)}
            className="text-start text-sm text-ink/75 glass rounded-2xl px-4 py-2.5 hover:text-tekhelet hover:bg-white/70 transition font-serif flex items-center justify-between gap-2"
          >
            <span>{ex}</span>
            <Icon name="arrow_forward" className="text-ink/30 text-sm shrink-0" />
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatPane({
  lang,
  messages,
  loading,
  thinkingHere,
  intent,
  locked,
  lessonFields,
  subtitle,
  onPickIntent,
  onLessonChange,
  onSend,
  onPreviewFile,
  calendarModesEnabled,
  sourcesheetModesEnabled,
  userEmail,
  userSources = [],
  onAddSource,
  onStop,
}: {
  lang: Lang;
  messages: Message[];
  loading: boolean;
  thinkingHere: boolean;
  intent: IntentId;
  locked: boolean;
  lessonFields: LessonFields;
  subtitle: string;
  onPickIntent: (i: IntentId) => void;
  onLessonChange: (v: LessonFields) => void;
  onSend: (text: string) => void;
  onPreviewFile: (f: FileOut) => void;
  calendarModesEnabled?: boolean;
  sourcesheetModesEnabled?: boolean;
  userEmail?: string | null;
  userSources?: Attachment[];
  onAddSource?: () => void;
  onStop?: () => void;
}) {
  const userInitial = userEmail ? userEmail[0].toUpperCase() : "א";
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const lastBubbleRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(messages.length);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const prevCount = prevCountRef.current;
    const currentCount = messages.length;
    prevCountRef.current = currentCount;

    if (currentCount > prevCount) {
      const last = messages[currentCount - 1];
      if (last.role === "user") {
        endRef.current?.scrollIntoView({ behavior: "smooth" });
      } else if (last.role === "assistant") {
        // Scroll to the start/top of the assistant message so the user can read naturally from the top
        lastBubbleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } else if (thinkingHere) {
      endRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, thinkingHere]);

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
      <div className="px-7 py-4 flex items-center gap-3 border-b border-white/40">
        <div className="min-w-0">
          <h2 className="font-serif text-lg font-bold text-tekhelet">{tr(lang, "discussionTitle")}</h2>
          {subtitle && <p className="text-[10px] tracking-widest text-gold font-bold uppercase truncate">{subtitle}</p>}
        </div>
      </div>

      {intent === "lesson" && <LessonOptions lang={lang} value={lessonFields} onChange={onLessonChange} />}

      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        className="flex-1 overflow-y-auto px-8 py-8 flex flex-col gap-6 max-w-2xl mx-auto w-full"
      >
        {/* Dev-helper invitation and notices. Placed at the TOP of the scroller rather than as an
            overlay: an invitation is not urgent enough to interrupt someone mid-question, and a
            modal that blocks the app to ask a favour is the wrong shape for a favour. It renders
            nothing at all for almost every account. */}
        <HelperPrompt lang={lang} />

        {messages.length === 0 ? (
          intent === "sourcesheet" ? (
            <SourceSheetHero
              lang={lang}
              userSources={userSources}
              onAddSource={onAddSource}
              onPickExample={(ex) => {
                setInput(ex);
                taRef.current?.focus();
              }}
            />
          ) : (
            <div className="m-auto text-center px-6">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.png" alt="חברותא" className="h-16 w-auto object-contain mx-auto mb-5" />
              <h2 className="font-serif text-3xl font-bold text-tekhelet mb-2">{tr(lang, "welcomeTitle")}</h2>
              <p className="text-ink/55 max-w-md mx-auto leading-relaxed">{tr(lang, "welcomeBody")}</p>

              {/* Onboarding — clickable example prompts prefill the composer so a new user knows where
                  to start. */}
              <p className="text-xs text-ink/45 mt-7 mb-2.5">{tr(lang, "examplesLabel")}</p>
              <div className="flex flex-col gap-2 max-w-md mx-auto">
                {EXAMPLES[lang].map((ex) => (
                  <button
                    key={ex}
                    onClick={() => {
                      setInput(ex);
                      taRef.current?.focus();
                    }}
                    className="text-start text-sm text-ink/70 glass rounded-2xl px-4 py-2.5 hover:text-tekhelet hover:bg-white/60 transition font-serif"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )
        ) : (
          messages.map((m, i) => {
            const isLast = i === messages.length - 1;
            return (
              <div key={m.id ?? i} ref={isLast ? lastBubbleRef : undefined}>
                <Bubble lang={lang} m={m} onPreview={onPreviewFile} userInitial={userInitial} />
              </div>
            );
          })
        )}
        {thinkingHere && (
          <div className="flex gap-3.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="חברותא" className="h-8 w-8 object-contain shrink-0 mt-1" />
            <div className="bg-white/70 rounded-3xl rounded-tr-md p-5 shadow-sm ring-1 ring-white/60 text-ink/50 font-serif">
              {tr(
                lang,
                intent === "lesson"
                  ? "lessonThinking"
                  : intent === "sourcesheet"
                  ? "sourcesheetThinking"
                  : "thinking"
              )}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="p-3 sm:p-5">
        <form
          onSubmit={submit}
          className="max-w-2xl mx-auto flex items-center gap-2 glass rounded-full px-3 py-1.5 sm:py-2 focus-within:ring-2 focus-within:ring-indigo/30"
        >
          <IntentBar
            lang={lang}
            intent={intent}
            locked={locked}
            onPick={onPickIntent}
            calendarModesEnabled={calendarModesEnabled}
            sourcesheetModesEnabled={sourcesheetModesEnabled}
          />
          <textarea
            ref={taRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) submit(e);
            }}
            className="flex-1 bg-transparent outline-none font-serif text-[16px] placeholder:text-ink/35 resize-none leading-snug sm:leading-relaxed max-h-32 py-1"
            placeholder={tr(lang, "askPlaceholder")}
          />
          {loading || thinkingHere ? (
            <button
              type="button"
              onClick={onStop}
              className="h-10 w-10 rounded-full bg-red-600 hover:bg-red-700 active:scale-95 text-white grid place-items-center shadow-lg shadow-red-900/30 transition-all cursor-pointer shrink-0"
              title={lang === "he" ? "עצור מענה" : "Stop generation"}
            >
              <span className="w-3.5 h-3.5 rounded-[2px] bg-white block shadow-sm" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="h-10 w-10 rounded-full grad text-white grid place-items-center hover:opacity-95 shadow-lg shadow-tekhelet/20 disabled:opacity-40"
              title={tr(lang, "send")}
            >
              <Icon name="arrow_upward" className="text-[20px]" />
            </button>
          )}
        </form>
        <p className="text-center text-[10px] text-ink/35 mt-2.5">{tr(lang, "footer")}</p>
      </div>
    </main>
  );
}
