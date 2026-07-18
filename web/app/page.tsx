"use client";
import { useCallback, useEffect, useState } from "react";
import type { Lang, Message, Session } from "@/lib/types";
import { api, LessonExtras } from "@/lib/api";
import { IntentId } from "@/lib/i18n";
import { LessonFields } from "@/components/LessonOptions";
import { Header } from "@/components/Header";
import { SessionsPanel } from "@/components/SessionsPanel";
import { ChatPane } from "@/components/ChatPane";
import { SourcesPanel } from "@/components/SourcesPanel";

const DEFAULT_INTENT: IntentId = "lesson";

export default function Home() {
  const [lang, setLang] = useState<Lang>("he");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<IntentId>(DEFAULT_INTENT);
  const [lessonFields, setLessonFields] = useState<LessonFields>({ audience: "", gradeBand: "", length: "" });

  // Sticky mode: once a conversation has messages the intent is locked (server enforces it too).
  const locked = !!activeId && messages.length > 0;

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
  }, [lang]);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.listSessions());
    } catch {
      /* backend may be down in dev — the shell still renders */
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const selectSession = useCallback(async (s: Session) => {
    setActiveId(s.id);
    if (s.mode) setIntent(s.mode as IntentId); // reflect the session's locked mode
    try {
      setMessages(await api.sessionMessages(s.id));
    } catch {
      setMessages([]);
    }
  }, []);

  const newDiscussion = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setIntent(DEFAULT_INTENT);
  }, []);

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await api.deleteSession(id);
      } catch {
        /* ignore */
      }
      if (id === activeId) newDiscussion();
      refreshSessions();
    },
    [activeId, newDiscussion, refreshSessions],
  );

  const send = useCallback(
    async (text: string) => {
      const extras: LessonExtras | undefined =
        intent === "lesson"
          ? { audience: lessonFields.audience, grade_band: lessonFields.gradeBand, length: lessonFields.length }
          : undefined;
      setLoading(true);
      setMessages((prev) => [...prev, { role: "user", text, citations: [], caveats: [] }]);
      const push = (r: { answer: string; citations?: Message["citations"]; caveats?: string[]; grounded?: boolean; files?: Message["files"] }) =>
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: r.answer, citations: r.citations || [], caveats: r.caveats || [], grounded: r.grounded, files: r.files },
        ]);
      try {
        if (activeId) {
          push(await api.sessionQuery(activeId, text, intent, lang, extras));
        } else {
          const s = await api.createSession(text, intent, lang, extras);
          setActiveId(s.id);
          push(s.result);
          refreshSessions();
        }
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: String(e instanceof Error ? e.message : e), citations: [], caveats: [] },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [activeId, intent, lang, lessonFields, refreshSessions],
  );

  return (
    <div className="flex flex-col h-screen">
      <Header lang={lang} onToggleLang={() => setLang((l) => (l === "he" ? "en" : "he"))} />
      <div className="flex flex-1 overflow-hidden px-4 pb-4 gap-4">
        <SessionsPanel
          lang={lang}
          sessions={sessions}
          activeId={activeId}
          onNew={newDiscussion}
          onSelect={(id) => {
            const s = sessions.find((x) => x.id === id);
            if (s) selectSession(s);
          }}
          onDelete={deleteSession}
        />
        <ChatPane
          lang={lang}
          messages={messages}
          loading={loading}
          intent={intent}
          locked={locked}
          lessonFields={lessonFields}
          subtitle=""
          onPickIntent={setIntent}
          onLessonChange={setLessonFields}
          onSend={send}
        />
        <SourcesPanel lang={lang} messages={messages} />
      </div>
    </div>
  );
}
