"use client";
import { useCallback, useEffect, useState } from "react";
import type { Lang, Message, Session } from "@/lib/types";
import { api } from "@/lib/api";
import { Header } from "@/components/Header";
import { SessionsPanel } from "@/components/SessionsPanel";
import { ChatPane } from "@/components/ChatPane";
import { SourcesPanel } from "@/components/SourcesPanel";

export default function Home() {
  const [lang, setLang] = useState<Lang>("he");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  // Reflect language on <html> so RTL/LTR + fonts flip exactly like the static UI.
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

  const selectSession = useCallback(async (id: string) => {
    setActiveId(id);
    try {
      setMessages(await api.sessionMessages(id));
    } catch {
      setMessages([]);
    }
  }, []);

  const newDiscussion = useCallback(() => {
    setActiveId(null);
    setMessages([]);
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
      const intent = "qa"; // sticky mode is enforced server-side; intent selection is a later port
      setLoading(true);
      setMessages((prev) => [...prev, { role: "user", text, citations: [], caveats: [] }]);
      try {
        if (activeId) {
          const r = await api.sessionQuery(activeId, text, intent, lang);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", text: r.answer, citations: r.citations || [], caveats: r.caveats || [], grounded: r.grounded, files: r.files },
          ]);
        } else {
          const s = await api.createSession(text, intent, lang);
          setActiveId(s.id);
          const r = s.result;
          setMessages((prev) => [
            ...prev,
            { role: "assistant", text: r.answer, citations: r.citations || [], caveats: r.caveats || [], grounded: r.grounded, files: r.files },
          ]);
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
    [activeId, lang, refreshSessions],
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
          onSelect={selectSession}
          onDelete={deleteSession}
        />
        <ChatPane lang={lang} messages={messages} loading={loading} onSend={send} />
        <SourcesPanel lang={lang} messages={messages} />
      </div>
    </div>
  );
}
