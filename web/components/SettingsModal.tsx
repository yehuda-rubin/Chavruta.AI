"use client";
import type { Lang } from "@/lib/types";
import { INTENTS, IntentId, tr, StringKey } from "@/lib/i18n";
import { Modal } from "./Modal";

const MODE_KEY: Record<IntentId, StringKey> = {
  lesson: "lesson",
  explain: "explain",
  qa: "qa",
  shut: "shutMode",
  chavruta: "chavrutaMode",
};

// Settings — theme, default mode, and whether source cards open by default. Matches the static UI.
export function SettingsModal({
  open,
  lang,
  theme,
  defaultIntent,
  srcDefaultOpen,
  onClose,
  onTheme,
  onDefaultIntent,
  onSrcDefaultOpen,
}: {
  open: boolean;
  lang: Lang;
  theme: "light" | "dark";
  defaultIntent: IntentId;
  srcDefaultOpen: boolean;
  onClose: () => void;
  onTheme: (t: "light" | "dark") => void;
  onDefaultIntent: (i: IntentId) => void;
  onSrcDefaultOpen: (v: boolean) => void;
}) {
  const seg = (active: boolean) =>
    "px-3 py-1.5 rounded-full text-sm font-semibold transition " + (active ? "grad text-white" : "text-ink/60 hover:text-tekhelet");

  return (
    <Modal open={open} title={tr(lang, "settingsHeading")} onClose={onClose}>
      <div className="flex flex-col gap-5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-semibold text-ink/70">{tr(lang, "theme")}</span>
          <div className="flex bg-white/50 rounded-full p-1">
            <button className={seg(theme === "light")} onClick={() => onTheme("light")}>
              {tr(lang, "themeLight")}
            </button>
            <button className={seg(theme === "dark")} onClick={() => onTheme("dark")}>
              {tr(lang, "themeDark")}
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-semibold text-ink/70">{tr(lang, "defaultMode")}</span>
          <div className="flex flex-wrap justify-end gap-1 bg-white/50 rounded-2xl p-1">
            {INTENTS.map((i) => (
              <button key={i} className={seg(defaultIntent === i)} onClick={() => onDefaultIntent(i)}>
                {tr(lang, MODE_KEY[i])}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-semibold text-ink/70">{tr(lang, "sourcesDefaultOpen")}</span>
          <div className="flex bg-white/50 rounded-full p-1">
            <button className={seg(srcDefaultOpen)} onClick={() => onSrcDefaultOpen(true)}>
              {tr(lang, "on")}
            </button>
            <button className={seg(!srcDefaultOpen)} onClick={() => onSrcDefaultOpen(false)}>
              {tr(lang, "off")}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
