import type { Lang, Session } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

// Ported from the static UI <aside id="sessionsPanel"> — same classes.
export function SessionsPanel({
  lang,
  sessions,
  activeId,
  onNew,
  onSelect,
  onDelete,
}: {
  lang: Lang;
  sessions: Session[];
  activeId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="w-72 shrink-0 glass rounded-[28px] p-4 flex flex-col">
      <div className="flex items-center gap-2 mb-3">
        <button
          onClick={onNew}
          className="flex-1 grad text-white py-3 rounded-2xl font-serif text-lg font-bold hover:opacity-95 transition shadow-lg shadow-tekhelet/20"
        >
          {tr(lang, "newChat")}
        </button>
      </div>
      <p className="text-[11px] tracking-widest text-ink/40 font-bold uppercase mt-3 mb-2 px-2">
        {tr(lang, "recentChats")}
      </p>
      <nav className="flex flex-col gap-1.5 overflow-y-auto flex-1">
        {sessions.map((s) => {
          const active = s.id === activeId;
          return (
            <div
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={
                "group flex items-center gap-1 rounded-2xl px-3 py-2.5 cursor-pointer transition " +
                (active ? "bg-white/80 ring-2 ring-tekhelet/15" : "hover:bg-white/50")
              }
            >
              <span className="min-w-0 flex-1 truncate text-[15px] text-ink/80 font-serif">
                {s.first_q || tr(lang, "newChatShort")}
              </span>
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
            </div>
          );
        })}
      </nav>
      <div className="mt-auto pt-3 flex flex-col gap-2">
        <button className="w-full px-4 py-2.5 rounded-2xl glass text-ink/70 font-semibold text-sm hover:bg-white/60 hover:text-tekhelet transition flex items-center gap-2 cursor-pointer">
          <Icon name="auto_stories" className="text-[19px]" />
          <span>{tr(lang, "myShiurim")}</span>
        </button>
        <button className="w-full px-4 py-2.5 rounded-2xl glass text-ink/70 font-semibold text-sm hover:bg-white/60 hover:text-tekhelet transition flex items-center gap-2 cursor-pointer">
          <Icon name="settings" className="text-[19px]" />
          <span>{tr(lang, "settingsTitle")}</span>
        </button>
        <button className="w-full px-4 py-2.5 rounded-2xl glass text-ink/70 font-semibold text-sm hover:bg-white/60 hover:text-tekhelet transition flex items-center gap-2 cursor-pointer">
          <Icon name="help" className="text-[19px]" />
          <span>{tr(lang, "supportTitle")}</span>
        </button>
      </div>
    </aside>
  );
}
