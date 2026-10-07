import { useEffect, useRef, useState } from "react";
import type { Lang } from "@/lib/types";
import { INTENTS, IntentId, tr, StringKey } from "@/lib/i18n";
import { Icon } from "./Icon";

const LABEL_KEY: Record<IntentId, StringKey> = {
  lesson: "lesson",
  explain: "explain",
  qa: "qa",
  shut: "shutMode",
  chavruta: "chavrutaMode",
  parsha: "parshaMode",
  dafyomi: "dafYomiMode",
  sourcesheet: "sourcesheetMode",
};

// One line under each mode, so the menu explains itself instead of leaving a new user to guess what
// "chavruta" or "source sheet" will do. Kept here (not in lib/i18n.ts) because it is only this menu's.
const HINT: Record<IntentId, { he: string; en: string }> = {
  lesson: { he: "מערך מלא למורים", en: "A full lesson plan for teachers" },
  explain: { he: "פסוק או סוגיה, עם מפרשים", en: "A verse or sugya, with commentaries" },
  qa: { he: "רק מהמקורות", en: "From the sources only" },
  shut: { he: "שולחן ערוך ונושאי כליו", en: "Shulchan Arukh and its commentaries" },
  chavruta: { he: "לימוד בדיאלוג", en: "Learning in dialogue" },
  parsha: { he: "לימוד פרשת השבוע", en: "This week's parsha" },
  dafyomi: { he: "הדף של היום", en: "Today's daf" },
  sourcesheet: { he: "דף מקורות מהחומרים שלך", en: "A source sheet from your materials" },
};

const ICON: Record<IntentId, string> = {
  lesson: "school",
  explain: "lightbulb",
  qa: "chat_bubble",
  shut: "menu_book",
  chavruta: "groups",
  parsha: "auto_stories",
  dafyomi: "calendar_month",
  sourcesheet: "description",
};

// Beta modes (parsha / daf yomi / source sheet) are switched off for everyone while they are in testing:
// the server still allow-lists them per account, but the picker no longer offers them. Set this to true
// to bring them back for the accounts the server enables them for.
const SHOW_BETA_MODES = false;

// Beta-gated modes
const BETA_CALENDAR_INTENTS: ReadonlySet<IntentId> = new Set(["parsha", "dafyomi"]);
const BETA_SOURCESHEET_INTENTS: ReadonlySet<IntentId> = new Set(["sourcesheet"]);

// The mode picker lives inside the composer and opens a menu above it (same pattern as the tools
// menu in other chat apps), so the modes are one tap from the text box and never take a row of their
// own. Disabled while a session is locked to its mode.
export function IntentBar({
  lang,
  intent,
  locked,
  onPick,
  calendarModesEnabled = false,
  sourcesheetModesEnabled = false,
}: {
  lang: Lang;
  intent: IntentId;
  locked: boolean;
  onPick: (i: IntentId) => void;
  calendarModesEnabled?: boolean;
  sourcesheetModesEnabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const visible = INTENTS.filter((i) => {
    if (BETA_CALENDAR_INTENTS.has(i)) return SHOW_BETA_MODES && calendarModesEnabled;
    if (BETA_SOURCESHEET_INTENTS.has(i)) return SHOW_BETA_MODES && sourcesheetModesEnabled;
    return true;
  });
  const isBeta = (i: IntentId) => BETA_CALENDAR_INTENTS.has(i) || BETA_SOURCESHEET_INTENTS.has(i);
  const stable = visible.filter((i) => !isBeta(i));
  const beta = visible.filter(isBeta);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const items = Array.from(rootRef.current?.querySelectorAll<HTMLButtonElement>("[role=menuitemradio]") ?? []);
        if (!items.length) return;
        e.preventDefault();
        const i = items.indexOf(document.activeElement as HTMLButtonElement);
        items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Land focus on the active mode when the menu opens, so arrow keys start from where you are.
  useEffect(() => {
    if (!open) return;
    const active = rootRef.current?.querySelector<HTMLButtonElement>("[aria-checked=true]");
    active?.focus();
  }, [open]);

  const row = (i: IntentId) => {
    const active = i === intent;
    return (
      <button
        type="button"
        role="menuitemradio"
        aria-checked={active}
        key={i}
        onClick={() => {
          onPick(i);
          setOpen(false);
          btnRef.current?.focus();
        }}
        className={
          "w-full flex items-center gap-3 text-start px-3 py-2.5 min-h-12 rounded-[20px] transition-colors " +
          (active ? "bg-cream-2" : "hover:bg-cream focus-visible:bg-cream")
        }
      >
        <span className={"h-9 w-9 rounded-[14px] grid place-items-center shrink-0 " + (active ? "bg-white text-indigo" : "bg-cream text-indigo")}>
          <Icon name={ICON[i]} className="text-[20px]" />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block font-semibold text-[15px] leading-tight text-ink">{tr(lang, LABEL_KEY[i])}</span>
          <span className="block text-xs text-ink/55">{HINT[i][lang]}</span>
        </span>
        {isBeta(i) && (
          <span className="text-[11px] font-semibold rounded-full bg-sun/30 text-ink/70 px-2 py-0.5">
            {lang === "he" ? "בטא" : "beta"}
          </span>
        )}
        <Icon name="check" className={"text-[18px] text-indigo " + (active ? "opacity-100" : "opacity-0")} />
      </button>
    );
  };

  return (
    <div className="shrink-0 self-end" ref={rootRef}>
      <button
        ref={btnRef}
        type="button"
        onClick={() => !locked && setOpen((o) => !o)}
        disabled={locked}
        aria-haspopup="menu"
        aria-expanded={open}
        title={locked ? "" : tr(lang, "chooseMode")}
        className={
          "inline-flex items-center gap-1 min-h-11 ps-3 pe-2.5 rounded-full font-semibold text-[15px] whitespace-nowrap transition-colors " +
          (locked
            ? "text-ink/40 cursor-not-allowed"
            : open
              ? "bg-cream-2 text-indigo cursor-pointer"
              : "text-ink/70 hover:bg-cream-2 hover:text-indigo cursor-pointer")
        }
      >
        <span>{tr(lang, LABEL_KEY[intent])}</span>
        {!locked && (
          <Icon name="expand_less" className={"text-[18px] transition-transform " + (open ? "" : "rotate-180")} />
        )}
      </button>
      {open && !locked && (
        <div
          role="menu"
          aria-label={tr(lang, "chooseMode")}
          className="absolute start-2 bottom-full mb-3 z-20 w-[min(340px,86vw)] max-h-[60vh] overflow-y-auto glass menu-surface rounded-[28px] p-2 shadow-xl"
        >
          {stable.map(row)}
          {beta.length > 0 && (
            <>
              <div className="px-3 pt-3 pb-1 text-xs text-ink/50">{lang === "he" ? "בבדיקה" : "In testing"}</div>
              {beta.map(row)}
            </>
          )}
        </div>
      )}
    </div>
  );
}
