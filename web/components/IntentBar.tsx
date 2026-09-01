import { useEffect, useState } from "react";
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

// Beta-gated modes
const BETA_CALENDAR_INTENTS: ReadonlySet<IntentId> = new Set(["parsha", "dafyomi"]);
const BETA_SOURCESHEET_INTENTS: ReadonlySet<IntentId> = new Set(["sourcesheet"]);

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
  const visible = INTENTS.filter((i) => {
    if (BETA_CALENDAR_INTENTS.has(i)) return calendarModesEnabled;
    if (BETA_SOURCESHEET_INTENTS.has(i)) return sourcesheetModesEnabled;
    return true;
  });

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  return (
    <div className="relative shrink-0">
      <button
        onClick={(e) => {
          e.stopPropagation();
          if (!locked) setOpen((o) => !o);
        }}
        disabled={locked}
        title={locked ? "" : tr(lang, "chooseMode")}
        className={
          "flex items-center gap-1 font-bold text-sm px-3 py-1.5 rounded-full whitespace-nowrap transition " +
          (locked ? "text-gold/60 cursor-not-allowed"
                  : "text-gold hover:bg-gold/10 cursor-pointer")
        }
      >
        <span>{tr(lang, LABEL_KEY[intent])}</span>
        {!locked && (
          <Icon name={open ? "expand_less" : "expand_more"} className="text-[18px]" />
        )}
      </button>
      {open && !locked && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute start-0 bottom-full mb-1 z-10 w-48 glass rounded-2xl shadow-lg ring-1 ring-black/5 py-1.5 flex flex-col"
        >
          {visible.map((i) => {
            const active = i === intent;
            return (
              <button
                key={i}
                onClick={() => {
                  onPick(i);
                  setOpen(false);
                }}
                className={
                  "text-start px-3 py-2 text-sm rounded-xl mx-1.5 transition " +
                  (active ? "grad text-white" : "text-ink/75 hover:bg-white/60 hover:text-tekhelet")
                }
              >
                {tr(lang, LABEL_KEY[i])}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
