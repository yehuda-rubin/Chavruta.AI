import type { Lang } from "@/lib/types";
import { INTENTS, IntentId, tr, StringKey } from "@/lib/i18n";

const LABEL_KEY: Record<IntentId, StringKey> = {
  lesson: "lesson",
  explain: "explain",
  qa: "qa",
  shut: "shutMode",
  chavruta: "chavrutaMode",
};

// The segmented intent control. Locked once a conversation has started (sticky mode is enforced
// server-side; the UI reflects it), matching the static UI's updateIntentLock.
export function IntentBar({
  lang,
  intent,
  locked,
  onPick,
}: {
  lang: Lang;
  intent: IntentId;
  locked: boolean;
  onPick: (i: IntentId) => void;
}) {
  return (
    <div
      className={"flex bg-white/50 rounded-full p-1 text-xs font-semibold " + (locked ? "opacity-60" : "")}
      title={locked ? "" : undefined}
    >
      {INTENTS.map((i) => {
        const active = i === intent;
        return (
          <button
            key={i}
            disabled={locked}
            onClick={() => !locked && onPick(i)}
            className={
              "px-3 py-1.5 rounded-full transition " +
              (active ? "grad text-white" : "text-ink/60 hover:text-tekhelet") +
              (locked ? " cursor-not-allowed" : "")
            }
          >
            {tr(lang, LABEL_KEY[i])}
          </button>
        );
      })}
    </div>
  );
}
