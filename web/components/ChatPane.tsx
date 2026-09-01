"use client";
import { useEffect, useRef, useState } from "react";
import type { FileOut, Lang, Message } from "@/lib/types";
import { EXAMPLES, IntentId, tr } from "@/lib/i18n";
import { commentatorTag, isHe, renderText } from "@/lib/format";
import { downloadDoc } from "@/lib/doc";
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
}: {
  lang: Lang;
  messages: Message[];
  loading: boolean;
  // Whether the PENDING request belongs to the chat currently on screen — `loading` alone stays true
  // in the background while its owning chat isn't the active one, so the "thinking" bubble must gate
  // on this instead or it renders in whichever chat you happen to switch to.
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
  // The signed-in user's email, when known — used only to derive the avatar initial. In local/dev
  // mode (no Supabase configured) there's no signed-in user at all, so this stays undefined and the
  // avatar falls back to the generic aleph glyph rather than rendering empty.
  userEmail?: string | null;
}) {
  const userInitial = userEmail ? userEmail[0].toUpperCase() : "א";
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
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
        ) : (
          messages.map((m, i) => <Bubble key={m.id ?? i} lang={lang} m={m} onPreview={onPreviewFile} userInitial={userInitial} />)
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
