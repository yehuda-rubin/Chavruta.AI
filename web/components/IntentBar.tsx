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
};

// Beta-gated modes (see app/api.py::_calendar_modes_enabled) — hidden from the picker entirely
// unless the account has calendar_modes_enabled, so most users never see an unavailable option.
const BETA_INTENTS: ReadonlySet<IntentId> = new Set(["parsha", "dafyomi"]);

// A single "current mode" trigger + gear icon, opening a dropdown with every mode — replaces the
// old segmented row of buttons, which ran out of room once parsha/daf-yomi were added. Follows the
// same pattern as SessionsPanel's "⋮" actions menu: a relative wrapper, a boolean open state, a
// document click-outside listener, and an absolutely-positioned glass panel.
export function IntentBar({
  lang,
  intent,
  locked,
  onPick,
  calendarModesEnabled = false,
}: {
  lang: Lang;
  intent: IntentId;
  locked: boolean;
  onPick: (i: IntentId) => void;
  calendarModesEnabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const visible = INTENTS.filter((i) => calendarModesEnabled || !BETA_INTENTS.has(i));

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
          "flex items-center gap-1.5 bg-white/50 rounded-full px-3 py-1.5 text-xs font-semibold transition " +
          (locked ? "opacity-60 cursor-not-allowed" : "hover:bg-white/70 cursor-pointer")
        }
      >
        <span className="grad bg-clip-text text-transparent">{tr(lang, LABEL_KEY[intent])}</span>
        {!locked && <Icon name="settings" className="text-[15px] text-ink/50" />}
      </button>
      {open && !locked && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute end-0 top-full mt-1 z-10 w-48 glass rounded-2xl shadow-lg ring-1 ring-black/5 py-1.5 flex flex-col"
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
