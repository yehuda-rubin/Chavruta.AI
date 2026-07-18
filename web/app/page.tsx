"use client";
import { useCallback, useEffect, useState } from "react";
import type { Attachment, Lang, Message, SavedLesson, Session } from "@/lib/types";
import { api, LessonExtras } from "@/lib/api";
import { IntentId } from "@/lib/i18n";
import { tr } from "@/lib/i18n";
import { LessonFields } from "@/components/LessonOptions";
import { Header } from "@/components/Header";
import { SessionsPanel } from "@/components/SessionsPanel";
import { ChatPane } from "@/components/ChatPane";
import { SourcesPanel } from "@/components/SourcesPanel";
import { Rail } from "@/components/Rail";
import { AddSourceModal } from "@/components/AddSourceModal";
import { LessonsModal } from "@/components/LessonsModal";
import { SettingsModal } from "@/components/SettingsModal";

export default function Home() {
  const [lang, setLang] = useState<Lang>("he");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<IntentId>("lesson");
  const [lessonFields, setLessonFields] = useState<LessonFields>({ audience: "", gradeBand: "", length: "" });
  const [userSources, setUserSources] = useState<Attachment[]>([]);

  // Preferences (persisted)
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [defaultIntent, setDefaultIntent] = useState<IntentId>("lesson");
  const [srcDefaultOpen, setSrcDefaultOpen] = useState(false);

  // UI chrome
  const [sessionsCollapsed, setSessionsCollapsed] = useState(false);
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false);
  const [showAddSource, setShowAddSource] = useState(false);
  const [showLessons, setShowLessons] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const locked = !!activeId && messages.length > 0;

  // Load persisted prefs once.
  useEffect(() => {
    const g = (k: string) => localStorage.getItem(k);
    const t = (g("chavruta-theme") as "light" | "dark") || "light";
    setTheme(t);
    const di = (g("chavruta-default-intent") as IntentId) || "lesson";
    setDefaultIntent(di);
    setIntent(di);
    setSrcDefaultOpen(g("chavruta-src-open") === "1");
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
  }, [lang]);
  useEffect(() => {
    document.body.classList.toggle("theme-dark", theme === "dark");
    localStorage.setItem("chavruta-theme", theme);
  }, [theme]);
  useEffect(() => {
    localStorage.setItem("chavruta-default-intent", defaultIntent);
  }, [defaultIntent]);
  useEffect(() => {
    localStorage.setItem("chavruta-src-open", srcDefaultOpen ? "1" : "0");
  }, [srcDefaultOpen]);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await api.listSessions());
    } catch {
      /* backend down in dev — shell still renders */
    }
  }, []);
  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const selectSession = useCallback(async (s: Session) => {
    setActiveId(s.id);
    if (s.mode) setIntent(s.mode as IntentId);
    try {
      setMessages(await api.sessionMessages(s.id));
    } catch {
      setMessages([]);
    }
  }, []);

  const newDiscussion = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setIntent(defaultIntent);
  }, [defaultIntent]);

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

  const openLesson = useCallback((l: SavedLesson) => {
    setShowLessons(false);
    setActiveId(null);
    setIntent("lesson");
    setMessages([{ role: "assistant", text: "📚 " + l.topic, files: l.files || [], citations: l.citations || [], caveats: [] }]);
  }, []);

  const send = useCallback(
    async (text: string) => {
      const extras: LessonExtras | undefined =
        intent === "lesson"
          ? { audience: lessonFields.audience, grade_band: lessonFields.gradeBand, length: lessonFields.length }
          : undefined;
      const att = userSources.length ? userSources : undefined;
      setLoading(true);
      setMessages((prev) => [...prev, { role: "user", text, citations: [], caveats: [] }]);
      const push = (r: { answer: string; citations?: Message["citations"]; caveats?: string[]; grounded?: boolean; files?: Message["files"] }) =>
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: r.answer, citations: r.citations || [], caveats: r.caveats || [], grounded: r.grounded, files: r.files },
        ]);
      try {
        if (activeId) {
          push(await api.sessionQuery(activeId, text, intent, lang, extras, att));
        } else {
          const s = await api.createSession(text, intent, lang, extras, att);
          setActiveId(s.id);
          push(s.result);
          refreshSessions();
        }
        setUserSources([]); // consumed by this turn
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: String(e instanceof Error ? e.message : e), citations: [], caveats: [] },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [activeId, intent, lang, lessonFields, userSources, refreshSessions],
  );

  return (
    <div className="flex flex-col h-screen">
      <Header
        lang={lang}
        theme={theme}
        onToggleLang={() => setLang((l) => (l === "he" ? "en" : "he"))}
        onToggleTheme={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
      />
      <div className="flex flex-1 overflow-hidden px-4 pb-4 gap-4">
        {sessionsCollapsed ? (
          <Rail
            side="start"
            icon="forum"
            title={tr(lang, "openChatsTip")}
            onExpand={() => setSessionsCollapsed(false)}
            extra={
              <button
                onClick={newDiscussion}
                className="h-10 w-10 rounded-2xl grad text-white grid place-items-center hover:opacity-95 transition"
                title={tr(lang, "newChatShort")}
              >
                <span className="material-symbols-outlined">add</span>
              </button>
            }
          />
        ) : (
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
            onCollapse={() => setSessionsCollapsed(true)}
            onOpenLessons={() => setShowLessons(true)}
            onOpenSettings={() => setShowSettings(true)}
          />
        )}

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

        {sourcesCollapsed ? (
          <Rail side="end" icon="menu_book" title={tr(lang, "openSourcesTip")} onExpand={() => setSourcesCollapsed(false)} />
        ) : (
          <SourcesPanel
            lang={lang}
            messages={messages}
            userSources={userSources}
            srcDefaultOpen={srcDefaultOpen}
            onRemoveSource={(i) => setUserSources((prev) => prev.filter((_, j) => j !== i))}
            onAddSource={() => setShowAddSource(true)}
            onCollapse={() => setSourcesCollapsed(true)}
          />
        )}
      </div>

      <AddSourceModal
        open={showAddSource}
        lang={lang}
        onClose={() => setShowAddSource(false)}
        onAdd={(items) => setUserSources((prev) => [...prev, ...items])}
      />
      <LessonsModal open={showLessons} lang={lang} onClose={() => setShowLessons(false)} onOpenLesson={openLesson} />
      <SettingsModal
        open={showSettings}
        lang={lang}
        theme={theme}
        defaultIntent={defaultIntent}
        srcDefaultOpen={srcDefaultOpen}
        onClose={() => setShowSettings(false)}
        onTheme={setTheme}
        onDefaultIntent={setDefaultIntent}
        onSrcDefaultOpen={setSrcDefaultOpen}
      />
    </div>
  );
}
