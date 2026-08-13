"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Attachment, FileOut, Lang, Message, SavedLesson, Session } from "@/lib/types";
import { api, LessonExtras, Me, Tier } from "@/lib/api";
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
import { PlansModal } from "@/components/PlansModal";
import { SupportModal } from "@/components/SupportModal";
import { FilePreviewModal } from "@/components/FilePreviewModal";
import { SignIn } from "@/components/SignIn";
import { Blocked } from "@/components/Blocked";
import { ConfirmConsent } from "@/components/ConfirmConsent";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const auth = useAuth();
  const [lang, setLang] = useState<Lang>("he");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  // Which chat the in-flight request belongs to (null = a not-yet-created new chat). `loading` alone
  // stays true for the whole round trip even after the user switches away, so the "thinking" bubble
  // must gate on this match, not on `loading` — otherwise it renders in whichever chat is on screen.
  const [loadingTarget, setLoadingTarget] = useState<string | null>(null);
  const [intent, setIntent] = useState<IntentId>("qa");
  const [lessonFields, setLessonFields] = useState<LessonFields>({ audience: "", gradeBand: "", length: "" });
  const [userSources, setUserSources] = useState<Attachment[]>([]);
  const [subtitle, setSubtitle] = useState("");
  const [previewFile, setPreviewFile] = useState<FileOut | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [billingEnabled, setBillingEnabled] = useState(false);
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [plansOpen, setPlansOpen] = useState(false);

  // Preferences (persisted)
  const [theme, setTheme] = useState<Theme>("light");
  const [defaultIntent, setDefaultIntent] = useState<IntentId>("qa");
  const [srcDefaultOpen, setSrcDefaultOpen] = useState(false);

  // UI chrome
  const [sessionsCollapsed, setSessionsCollapsed] = useState(false);
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false);
  // Mobile: the side panels are hidden and open as slide-over drawers (desktop keeps them inline).
  const [mobileSessions, setMobileSessions] = useState(false);
  const [mobileSources, setMobileSources] = useState(false);
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
    const di = (g("chavruta-default-intent") as IntentId) || "qa";
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
  // Clear the open chat whenever the signed-in account changes (sign-out, or a different account
  // signing in on the same tab) — otherwise the previous account's messages stay on screen until the
  // new user happens to click something, briefly leaking one account's chat into another's session.
  useEffect(() => {
    setActiveId(null);
    setMessages([]);
    setSubtitle("");
    setUserSources([]);
  }, [auth.user?.id]);

  const selectSession = useCallback(async (s: Session) => {
    setActiveId(s.id);
    setSubtitle(s.title || s.first_q || "");
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

  const renameSession = useCallback(
    async (id: string, title: string) => {
      try {
        await api.updateSession(id, { title }, lang);
        if (id === activeId) setSubtitle(title);
      } catch {
        /* ignore — a transient failure just leaves the old name; nothing to roll back client-side */
      }
      refreshSessions();
    },
    [lang, activeId, refreshSessions],
  );

  const pinSession = useCallback(
    async (id: string, pinned: boolean) => {
      try {
        await api.updateSession(id, { pinned }, lang);
      } catch {
        // The panel already disables pinning past the cap client-side, so a 409 here is only a rare
        // race (e.g. two tabs); refreshSessions() below re-syncs the true state either way.
      }
      refreshSessions();
    },
    [lang, refreshSessions],
  );

  const excludeSession = useCallback(
    async (id: string, excluded: boolean) => {
      try {
        await api.updateSession(id, { excluded }, lang);
      } catch {
        // Transient failure — refreshSessions() below re-syncs the true state either way.
      }
      refreshSessions();
    },
    [lang, refreshSessions],
  );

  const clearHistory = useCallback(async () => {
    const ids = sessions.map((s) => s.id);
    await Promise.allSettled(ids.map((id) => api.deleteSession(id)));
    setShowSettings(false);
    newDiscussion();
    refreshSessions();
  }, [sessions, newDiscussion, refreshSessions]);

  useEffect(() => {
    api.billingConfig()
      .then((c) => { setBillingEnabled(c.enabled); setTiers(c.tiers || []); })
      .catch(() => { setBillingEnabled(false); setTiers([]); });
  }, [auth.user?.id]);

  // Esc closes an open mobile drawer (keyboard accessibility).
  useEffect(() => {
    if (!mobileSessions && !mobileSources) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setMobileSessions(false); setMobileSources(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileSessions, mobileSources]);

  // Opening the picker is the "upgrade" action now — the tier and the billing cycle are the user's
  // choice, so checkout can't start until they've made it.
  const upgrade = useCallback(() => setPlansOpen(true), []);

  const choosePlan = useCallback(async (plan: string, cycle: "monthly" | "annual") => {
    try {
      const { url } = await api.checkout(auth.user?.email || "", "", plan, cycle);
      window.location.href = url;   // redirect to the hosted payment page
    } catch {
      /* ignore — the modal stays open so they can retry */
    }
  }, [auth.user?.email]);

  const cancelSubscription = useCallback(async () => {
    try {
      await api.cancelSubscription();
    } catch {
      /* ignore */
    }
    refreshMe();
  }, [refreshMe]);

  // Unlike the other billing handlers this one rethrows: the coupon field shows the server's own
  // message (localized there, and specific — "already redeemed" vs "expired"), so swallowing the
  // error would leave the user staring at a field that did nothing.
  const redeemCoupon = useCallback(async (code: string) => {
    const res = await api.redeemCoupon(code);
    refreshMe();
    return res.message;
  }, [refreshMe]);

  // Joining changes both the quota this account spends and whether the header shows the school
  // button, so /me is refreshed the same way a coupon redemption does it.
  const joinOrg = useCallback(async (code: string) => {
    const joined = await api.orgs.join(code);
    refreshMe();
    return `הצטרפת ל${joined.name}`;
  }, [refreshMe]);

  const deleteAccount = useCallback(async (immediate: boolean) => {
    try {
      const res = await api.deleteAccount(immediate);
      if (res.deleted) {
        // Nothing is left to come back to: staying signed in would render a list of chats that no
        // longer exist and 401 on the next call. End the session with the data it belonged to.
        await auth.signOut();
        return;
      }
    } catch {
      /* ignore — /me below re-reads the real state, so a failed request shows as "not scheduled" */
    }
    refreshMe();
  }, [refreshMe, auth]);

  const cancelAccountDeletion = useCallback(async () => {
    try {
      await api.cancelAccountDeletion();
    } catch {
      /* ignore */
    }
    refreshMe();
  }, [refreshMe]);

  const openLesson = useCallback(async (l: SavedLesson) => {
    setShowLessons(false);
    setActiveId(null);
    setIntent("lesson");
    setSubtitle(l.topic);
    // GET /lessons deliberately omits `files` and `citations` — the Word documents are large and
    // would bloat the list. So the row we were handed has neither, and reading them off it showed a
    // lesson with no downloads at all. Fetch the full record; the list stays light.
    setMessages([{ role: "assistant", text: "📚 " + l.topic, files: [], citations: [], caveats: [] }]);
    try {
      const full = await api.getLesson(l.id);
      setMessages([{
        role: "assistant",
        text: "📚 " + full.topic,
        files: full.files || [],
        citations: full.citations || [],
        caveats: [],
      }]);
    } catch {
      // Keep the header we already showed rather than blanking the screen; the lesson is still in
      // My Shiurim and re-opening retries.
      setMessages([{
        role: "assistant",
        text: "📚 " + l.topic + "\n\n" + tr(lang, "lessonLoadFailed"),
        files: [], citations: [], caveats: [],
      }]);
    }
  }, [lang]);

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
      setLoadingTarget(target);
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
            setLoadingTarget(id);
            setActiveId(id);
            setSubtitle(text);
            refreshSessions();
          });
          push(s.result);
          refreshSessions();
        }
        setUserSources([]); // consumed by this turn
      } catch (e) {
        // Friendly errors: a network failure → connection message; a 4xx with a clean server detail
        // (e.g. the bilingual quota/429 message) → show it; 5xx / job failure / timeout → generic
        // (never surface a raw exception or stack to the user).
        const err = e as Error & { status?: number };
        const msg =
          err?.name === "TypeError"
            ? tr(lang, "errNetwork")
            : err?.status && err.status < 500 && err.message
              ? err.message
              : tr(lang, "errGeneric");
        appendIfCurrent({ role: "assistant", text: msg, citations: [], caveats: [] });
      } finally {
        setLoading(false);
        setLoadingTarget(null);
        refreshMe(); // update the remaining-quota pill (incl. after a 429)
      }
    },
    [activeId, intent, lang, lessonFields, userSources, refreshSessions, refreshMe],
  );

  // Auth gate (Supabase mode only). While the initial session check runs, show a minimal splash;
  // if no user, show the sign-in screen. In local mode auth.enabled is false and neither fires.
  if (auth.enabled && auth.loading) {
    return <div className="min-h-dvh grid place-items-center text-ink/50">{tr(lang, "authWorking")}</div>;
  }
  if (auth.enabled && !auth.user) {
    return <SignIn lang={lang} />;
  }
  // An account with no recorded terms/age consent — e.g. created by calling Supabase's own signup
  // API directly, bypassing SignIn.tsx's checkboxes entirely. The backend already 403s every route
  // except /me and /account for it (app/security.py require_auth); this is the self-serve way out.
  if (auth.enabled && auth.user &&
      !(auth.user.user_metadata?.age_confirmed_18 && auth.user.user_metadata?.terms_version)) {
    return <ConfirmConsent lang={lang} />;
  }
  // Blocklisted account — show the block notice instead of the app (the server 403s everything else).
  if (auth.enabled && auth.user && me?.blocked) {
    return <Blocked lang={lang} until={me.blocked_until} reason={me.blocked_reason} />;
  }

  // Panels shared by the desktop-inline layout and the mobile drawers. `mobile` closes the drawer on
  // select/new/collapse so the user lands back on the chat.
  const sessionsPanel = (mobile: boolean) => (
    <SessionsPanel
      lang={lang}
      sessions={sessions}
      activeId={activeId}
      onNew={() => { newDiscussion(); if (mobile) setMobileSessions(false); }}
      onSelect={(id) => {
        const s = sessions.find((x) => x.id === id);
        if (s) selectSession(s);
        if (mobile) setMobileSessions(false);
      }}
      onDelete={deleteSession}
      onRename={renameSession}
      onPin={pinSession}
      onExclude={excludeSession}
      onCollapse={() => (mobile ? setMobileSessions(false) : setSessionsCollapsed(true))}
      onOpenLessons={() => setShowLessons(true)}
      onOpenSettings={() => setShowSettings(true)}
      onOpenSupport={() => setShowSupport(true)}
    />
  );
  const sourcesPanel = (mobile: boolean) => (
    <SourcesPanel
      lang={lang}
      messages={messages}
      userSources={userSources}
      srcDefaultOpen={srcDefaultOpen}
      onRemoveSource={(i) => setUserSources((prev) => prev.filter((_, j) => j !== i))}
      onAddSource={() => setShowAddSource(true)}
      onCollapse={() => (mobile ? setMobileSources(false) : setSourcesCollapsed(true))}
    />
  );

  return (
    <div className="flex flex-col h-dvh">
      <Header
        lang={lang}
        theme={effectiveDark ? "dark" : "light"}
        onToggleLang={() => setLang((l) => (l === "he" ? "en" : "he"))}
        onToggleTheme={() => setTheme(effectiveDark ? "light" : "dark")}
        onOpenSessions={() => setMobileSessions(true)}
        onOpenSources={() => setMobileSources(true)}
        onNewChat={newDiscussion}
        isAdmin={me?.is_admin}
        orgRole={me?.org_role}
      />
      <div className="flex flex-1 overflow-hidden px-4 pb-4 gap-4">
        {/* Sessions — desktop inline only (hidden on mobile, opened as a drawer). lg:contents keeps
            the desktop flex row exactly as before. */}
        <div className="hidden lg:contents">
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
            sessionsPanel(false)
          )}
        </div>

        <ChatPane
          lang={lang}
          messages={messages}
          loading={loading}
          thinkingHere={loading && activeId === loadingTarget}
          intent={intent}
          locked={locked}
          lessonFields={lessonFields}
          subtitle={subtitle}
          onPickIntent={setIntent}
          onLessonChange={setLessonFields}
          onSend={send}
          onPreviewFile={setPreviewFile}
          calendarModesEnabled={me?.calendar_modes_enabled}
        />

        <div className="hidden lg:contents">
          {sourcesCollapsed ? (
            <Rail side="end" icon="menu_book" title={tr(lang, "openSourcesTip")} onExpand={() => setSourcesCollapsed(false)} />
          ) : (
            sourcesPanel(false)
          )}
        </div>
      </div>

      {/* Mobile drawers — slide-over panels with a tap-to-close backdrop (start=sessions, end=sources;
          both respect RTL). Hidden on lg where the panels are inline. */}
      {mobileSessions && (
        <div className="lg:hidden fixed inset-0 z-50" onClick={() => setMobileSessions(false)}>
          <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={tr(lang, "recentChats")}
            className="absolute inset-y-0 start-0 p-3 flex max-w-[90vw]"
            onClick={(e) => e.stopPropagation()}
          >
            {sessionsPanel(true)}
          </div>
        </div>
      )}
      {mobileSources && (
        <div className="lg:hidden fixed inset-0 z-50" onClick={() => setMobileSources(false)}>
          <div className="absolute inset-0 bg-ink/30 backdrop-blur-sm" />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={tr(lang, "relatedSources")}
            className="absolute inset-y-0 end-0 p-3 flex max-w-[90vw]"
            onClick={(e) => e.stopPropagation()}
          >
            {sourcesPanel(true)}
          </div>
        </div>
      )}

      <AddSourceModal
        open={showAddSource}
        lang={lang}
        onClose={() => setShowAddSource(false)}
        onAdd={(items) => setUserSources((prev) => [...prev, ...items])}
      />
      <LessonsModal open={showLessons} lang={lang} onClose={() => setShowLessons(false)} onOpenLesson={openLesson} />
      <PlansModal
        open={plansOpen}
        lang={lang}
        tiers={tiers}
        currentPlan={me?.plan}
        onClose={() => setPlansOpen(false)}
        onChoose={choosePlan}
      />

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
        deletionGraceDays={me?.deletion_grace_days}
        onDeleteAccount={deleteAccount}
        onCancelDeletion={cancelAccountDeletion}
        plan={me?.plan}
        planName={me?.plan_name}
        planUntil={me?.plan_until}
        credits={me?.credits}
        cycle={me?.cycle}
        cancelAtPeriodEnd={me?.cancel_at_period_end}
        dayLeft={me?.day_left ?? null}
        weekLeft={me?.week_left ?? null}
        lessonsLeft={me?.lessons_left ?? null}
        billingEnabled={billingEnabled}
        onUpgrade={upgrade}
        onCancelSubscription={cancelSubscription}
        onRedeemCoupon={me?.authenticated ? redeemCoupon : undefined}
        byokSupported={me?.byok_supported}
      />
      <SupportModal open={showSupport} lang={lang} onClose={() => setShowSupport(false)} />
      <FilePreviewModal file={previewFile} lang={lang} onClose={() => setPreviewFile(null)} />
    </div>
  );
}
