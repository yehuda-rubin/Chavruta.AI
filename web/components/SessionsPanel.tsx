import { useState } from "react";
import type { Lang, Session } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

const MAX_PINNED = 3;

// Ported from the static UI <aside id="sessionsPanel"> — same classes.
export function SessionsPanel({
  lang,
  sessions,
  activeId,
  onNew,
  onSelect,
  onDelete,
  onRename,
  onPin,
  onCollapse,
  onOpenLessons,
  onOpenSettings,
  onOpenSupport,
}: {
  lang: Lang;
  sessions: Session[];
  activeId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onCollapse: () => void;
  onOpenLessons: () => void;
  onOpenSettings: () => void;
  onOpenSupport: () => void;
}) {
  // Which row is mid-rename, and its draft text. Only one at a time — starting a second rename
  // (or navigating away) abandons the first, matching how every other inline edit here behaves.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const pinnedCount = sessions.filter((s) => s.pinned_at).length;

  const startRename = (s: Session) => {
    setEditingId(s.id);
    setDraft(s.title || s.first_q || "");
  };
  const commitRename = () => {
    const title = draft.trim();
    if (editingId && title) onRename(editingId, title);
    setEditingId(null);
  };

  return (
    <aside className="w-72 shrink-0 glass rounded-[28px] p-4 flex flex-col">
      <div className="flex items-center gap-2 mb-3">
        <button
          onClick={onNew}
          className="flex-1 grad text-white py-3 rounded-2xl font-serif text-lg font-bold hover:opacity-95 transition shadow-lg shadow-tekhelet/20"
        >
          {tr(lang, "newChat")}
        </button>
        <button
          onClick={onCollapse}
          className="h-10 w-10 rounded-2xl glass grid place-items-center text-ink/50 hover:text-tekhelet shrink-0 transition"
          title={tr(lang, "collapse")}
        >
          <Icon name="chevron_right" />
        </button>
      </div>
      <p className="text-[11px] tracking-widest text-ink/40 font-bold uppercase mt-3 mb-2 px-2">
        {tr(lang, "recentChats")}
      </p>
      <nav className="flex flex-col gap-1.5 overflow-y-auto flex-1">
        {sessions.map((s) => {
          const active = s.id === activeId;
          const pinned = !!s.pinned_at;
          const editing = editingId === s.id;
          const pinDisabled = !pinned && pinnedCount >= MAX_PINNED;
          return (
            <div
              key={s.id}
              onClick={() => !editing && onSelect(s.id)}
              className={
                "group flex items-center gap-1 rounded-2xl px-3 py-2.5 cursor-pointer transition " +
                (active ? "bg-white/80 ring-2 ring-tekhelet/15" : "hover:bg-white/50")
              }
            >
              {editing ? (
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  placeholder={tr(lang, "renameChatPlaceholder")}
                  className="min-w-0 flex-1 bg-white/70 rounded-lg px-2 py-1 text-[15px] text-ink/80 font-serif outline-none ring-1 ring-tekhelet/30"
                />
              ) : (
                <span
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    startRename(s);
                  }}
                  className="min-w-0 flex-1 truncate text-[15px] text-ink/80 font-serif"
                >
                  {pinned && <Icon name="push_pin" className="text-[13px] align-middle me-1 text-gold" />}
                  {s.title || s.first_q || tr(lang, "newChatShort")}
                </span>
              )}
              {!editing && (
                <>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startRename(s);
                    }}
                    title={tr(lang, "renameChat")}
                    className="opacity-0 group-hover:opacity-100 text-ink/40 hover:text-tekhelet transition shrink-0"
                  >
                    <Icon name="edit" className="text-[16px]" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!pinDisabled) onPin(s.id, !pinned);
                    }}
                    title={pinned ? tr(lang, "unpinChat") : pinDisabled ? tr(lang, "pinLimitTitle") : tr(lang, "pinChat")}
                    disabled={pinDisabled}
                    className={
                      "transition shrink-0 " +
                      (pinned
                        ? "text-gold hover:text-gold/70"
                        : "opacity-0 group-hover:opacity-100 text-ink/40 hover:text-tekhelet " +
                          (pinDisabled ? "cursor-not-allowed" : "")
                      )
                    }
                  >
                    <Icon name="push_pin" className="text-[16px]" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(s.id);
                    }}
                    title={tr(lang, "deleteChat")}
                    className="opacity-0 group-hover:opacity-100 text-ink/40 hover:text-red-500 transition shrink-0"
                  >
                    <Icon name="delete" className="text-[18px]" />
                  </button>
                </>
              )}
            </div>
          );
        })}
      </nav>
      <div className="mt-auto pt-3 flex flex-col gap-2">
        <button
          onClick={onOpenLessons}
          className="w-full px-4 py-2.5 rounded-2xl glass text-ink/70 font-semibold text-sm hover:bg-white/60 hover:text-tekhelet transition flex items-center gap-2 cursor-pointer"
        >
          <Icon name="auto_stories" className="text-[19px]" />
          <span>{tr(lang, "myShiurim")}</span>
        </button>
        <button
          onClick={onOpenSettings}
          className="w-full px-4 py-2.5 rounded-2xl glass text-ink/70 font-semibold text-sm hover:bg-white/60 hover:text-tekhelet transition flex items-center gap-2 cursor-pointer"
        >
          <Icon name="settings" className="text-[19px]" />
          <span>{tr(lang, "settingsTitle")}</span>
        </button>
        <button
          onClick={onOpenSupport}
          className="w-full px-4 py-2.5 rounded-2xl glass text-ink/70 font-semibold text-sm hover:bg-white/60 hover:text-tekhelet transition flex items-center gap-2 cursor-pointer"
        >
          <Icon name="help" className="text-[19px]" />
          <span>{tr(lang, "supportTitle")}</span>
        </button>
      </div>
    </aside>
  );
}
