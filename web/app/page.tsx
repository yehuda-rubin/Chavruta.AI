"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Attachment, FileOut, Lang, Message, SavedLesson, Session } from "@/lib/types";
import { api, LessonExtras, Me } from "@/lib/api";
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
import { SettingsModal, Theme } from "@/components/SettingsModal";
import { SupportModal } from "@/components/SupportModal";
import { FilePreviewModal } from "@/components/FilePreviewModal";
import { SignIn } from "@/components/SignIn";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const auth = useAuth();
  const [lang, setLang] = useState<Lang>("he");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<IntentId>("lesson");
  const [lessonFields, setLessonFields] = useState<LessonFields>({ audience: "", gradeBand: "", length: "" });
  const [userSources, setUserSources] = useState<Attachment[]>([]);
  const [subtitle, setSubtitle] = useState("");
  const [previewFile, setPreviewFile] = useState<FileOut | null>(null);
  const [me, setMe] = useState<Me | null>(null);

  // Preferences (persisted)
  const [theme, setTheme] = useState<Theme>("light");
  const [defaultIntent, setDefaultIntent] = useState<IntentId>("lesson");
  const [srcDefaultOpen, setSrcDefaultOpen] = useState(false);

  // UI chrome
  const [sessionsCollapsed, setSessionsCollapsed] = useState(false);
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false);
  const [showAddSource, setShowAddSource] = useState(false);
  const [showLessons, setShowLessons] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showSupport, setShowSupport] = useState(false);
  const [systemDark, setSystemDark] = useState(false);
  const effectiveDark = theme === "dark" || (theme === "auto" && systemDark);

  const locked = !!activeId && messages.length > 0;

  // Always-current active session id, readable inside async callbacks. An async generation can take
  // minutes; if the user switches chats before it resolves, we must NOT append its answer onto the
  // now-open conversation. The ref lets the resolve handler check "am I still the active chat?".
  const activeIdRef = useRef<string | null>(null);
  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  // Load persisted prefs once + watch the system theme (for "auto").
  useEffect(() => {
    const g = (k: string) => localStorage.getItem(k);
    setTheme((g("chavruta-theme") as Theme) || "light");
    const di = (g("chavruta-default-intent") as IntentId) || "lesson";
    setDefaultIntent(di);
    setIntent(di);
    setSrcDefaultOpen(g("chavruta-src-open") === "1");
    const saveLang = g("chavruta-lang") as Lang | null;
    if (saveLang) setLang(saveLang);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(mq.matches);
    const onMq = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onMq);
    return () => mq.removeEventListener("change", onMq);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
    localStorage.setItem("chavruta-lang", lang);
  }, [lang]);
  useEffect(() => {
    document.body.classList.toggle("theme-dark", effectiveDark);
    localStorage.setItem("chavruta-theme", theme);
  }, [theme, effectiveDark]);
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

  // Account + remaining daily quota (for the header pill). Refreshed on sign-in and after each turn.
  const refreshMe = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      /* ignore — no quota pill shown */
    }
  }, []);
  useEffect(() => {
    refreshMe();
  }, [refreshMe, auth.user?.id]);
  // Re-fetch when the signed-in user changes too: after sign-in the bearer token is now set, so the
  // list (which 401'd while signed out in Supabase mode) can load. auth.user?.id is null in local mode
  // so this runs exactly once there — unchanged.
  useEffect(() => {
    refreshSessions();
  }, [refreshSessions, auth.user?.id]);

  const selectSession = useCallback(async (s: Session) => {
    setActiveId(s.id);
    setSubtitle(s.first_q || "");
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
    setSubtitle("");
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

  const clearHistory = useCallback(async () => {
    const ids = sessions.map((s) => s.id);
    await Promise.allSettled(ids.map((id) => api.deleteSession(id)));
    setShowSettings(false);
    newDiscussion();
    refreshSessions();
  }, [sessions, newDiscussion, refreshSessions]);

  const deleteAccount = useCallback(async () => {
    try {
      await api.deleteAccount();
    } catch {
      /* ignore */
    }
    refreshMe();
  }, [refreshMe]);

  const cancelAccountDeletion = useCallback(async () => {
    try {
      await api.cancelAccountDeletion();
    } catch {
      /* ignore */
    }
    refreshMe();
  }, [refreshMe]);

  const openLesson = useCallback((l: SavedLesson) => {
    setShowLessons(false);
    setActiveId(null);
    setIntent("lesson");
    setSubtitle(l.topic);
    setMessages([{ role: "assistant", text: "📚 " + l.topic, files: l.files || [], citations: l.citations || [], caveats: [] }]);
  }, []);

  const send = useCallback(
    async (text: string) => {
      const extras: LessonExtras | undefined =
        intent === "lesson"
          ? { audience: lessonFields.audience, grade_band: lessonFields.gradeBand, length: lessonFields.length }
          : undefined;
      const att = userSources.length ? userSources : undefined;
      // The conversation this turn belongs to. For a follow-up it's the current chat; for a brand-new
      // chat it becomes known when onSession fires. Answers are only shown if this is still on screen.
      let target = activeId;
      setLoading(true);
      setMessages((prev) => [...prev, { role: "user", text, citations: [], caveats: [] }]);
      const appendIfCurrent = (msg: Message) =>
        setMessages((prev) => (activeIdRef.current === target ? [...prev, msg] : prev));
      const push = (r: { answer: string; citations?: Message["citations"]; caveats?: string[]; grounded?: boolean; files?: Message["files"] }) =>
        appendIfCurrent({ role: "assistant", text: r.answer, citations: r.citations || [], caveats: r.caveats || [], grounded: r.grounded, files: r.files });
      try {
        if (activeId) {
          push(await api.sessionQueryAsync(activeId, text, intent, lang, extras, att));
        } else {
          // Async create: the session id comes back immediately (onSession) so the new chat attaches
          // to the UI while the (possibly minutes-long) first lesson generates on the job queue.
          const s = await api.createSessionAsync(text, intent, lang, extras, att, (id) => {
            target = id;
            setActiveId(id);
            setSubtitle(text);
            refreshSessions();
          });
          push(s.result);
          refreshSessions();
        }
        setUserSources([]); // consumed by this turn
      } catch (e) {
        appendIfCurrent({ role: "assistant", text: String(e instanceof Error ? e.message : e), citations: [], caveats: [] });
      } finally {
        setLoading(false);
        refreshMe(); // update the remaining-quota pill (incl. after a 429)
      }
    },
    [activeId, intent, lang, lessonFields, userSources, refreshSessions, refreshMe],
  );

  // Auth gate (Supabase mode only). While the initial session check runs, show a minimal splash;
  // if no user, show the sign-in screen. In local mode auth.enabled is false and neither fires.
  if (auth.enabled && auth.loading) {
    return <div className="min-h-screen grid place-items-center text-ink/50">{tr(lang, "authWorking")}</div>;
  }
  if (auth.enabled && !auth.user) {
    return <SignIn lang={lang} />;
  }

  return (
    <div className="flex flex-col h-screen">
      <Header
        lang={lang}
        theme={effectiveDark ? "dark" : "light"}
        remaining={me?.remaining ?? null}
        onToggleLang={() => setLang((l) => (l === "he" ? "en" : "he"))}
        onToggleTheme={() => setTheme(effectiveDark ? "light" : "dark")}
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
            onOpenSupport={() => setShowSupport(true)}
          />
        )}

        <ChatPane
          lang={lang}
          messages={messages}
          loading={loading}
          intent={intent}
          locked={locked}
          lessonFields={lessonFields}
          subtitle={subtitle}
          onPickIntent={setIntent}
          onLessonChange={setLessonFields}
          onSend={send}
          onPreviewFile={setPreviewFile}
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
        onLang={setLang}
        onTheme={setTheme}
        onDefaultIntent={setDefaultIntent}
        onSrcDefaultOpen={setSrcDefaultOpen}
        onClearHistory={clearHistory}
        deletionScheduledFor={me?.deletion_scheduled_for ?? null}
        onDeleteAccount={deleteAccount}
        onCancelDeletion={cancelAccountDeletion}
      />
      <SupportModal open={showSupport} lang={lang} onClose={() => setShowSupport(false)} />
      <FilePreviewModal file={previewFile} lang={lang} onClose={() => setPreviewFile(null)} />
    </div>
  );
}
