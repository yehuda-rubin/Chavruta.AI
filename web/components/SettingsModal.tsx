"use client";
import type { Lang } from "@/lib/types";
import { IntentId, tr, StringKey } from "@/lib/i18n";
import { Modal } from "./Modal";
import { useAuth } from "@/lib/auth";

export type Theme = "light" | "dark" | "auto";

// Default-mode options match the static UI (lesson / explain / qa / shut).
const MODES: { id: IntentId; key: StringKey }[] = [
  { id: "lesson", key: "lesson" },
  { id: "explain", key: "explain" },
  { id: "qa", key: "qa" },
  { id: "shut", key: "shutMode" },
];

function Seg<T extends string>({
  value,
  options,
  onPick,
  wrap,
}: {
  value: T;
  options: { v: T; label: string }[];
  onPick: (v: T) => void;
  wrap?: boolean;
}) {
  return (
    <div className={`flex bg-white/50 rounded-2xl p-1 text-sm font-semibold gap-1 ${wrap ? "flex-wrap" : ""}`}>
      {options.map((o) => (
        <button
          key={o.v}
          onClick={() => onPick(o.v)}
          className={"flex-1 px-3 py-1.5 rounded-full transition " + (value === o.v ? "grad text-white" : "text-ink/60 hover:text-tekhelet")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-bold text-ink/55">{label}</label>
      {children}
    </div>
  );
}

// Settings — full parity with the static UI: interface language, default mode, theme (light/dark/
// auto), sources default (collapsed/expanded), clear history, and an about/version footer.
export function SettingsModal({
  open,
  lang,
  theme,
  defaultIntent,
  srcDefaultOpen,
  onClose,
  onLang,
  onTheme,
  onDefaultIntent,
  onSrcDefaultOpen,
  onClearHistory,
}: {
  open: boolean;
  lang: Lang;
  theme: Theme;
  defaultIntent: IntentId;
  srcDefaultOpen: boolean;
  onClose: () => void;
  onLang: (l: Lang) => void;
  onTheme: (t: Theme) => void;
  onDefaultIntent: (i: IntentId) => void;
  onSrcDefaultOpen: (v: boolean) => void;
  onClearHistory: () => void;
}) {
  const auth = useAuth();
  return (
    <Modal open={open} title={tr(lang, "settingsHeading")} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto">
        <Field label={tr(lang, "setLanguage")}>
          <Seg<Lang>
            value={lang}
            onPick={onLang}
            options={[
              { v: "he", label: "עברית" },
              { v: "en", label: "English" },
            ]}
          />
        </Field>

        <Field label={tr(lang, "setDefaultMode")}>
          <Seg<IntentId>
            value={defaultIntent}
            onPick={onDefaultIntent}
            wrap
            options={MODES.map((m) => ({ v: m.id, label: tr(lang, m.key) }))}
          />
        </Field>

        <Field label={tr(lang, "setTheme")}>
          <Seg<Theme>
            value={theme}
            onPick={onTheme}
            options={[
              { v: "light", label: tr(lang, "themeLight") },
              { v: "dark", label: tr(lang, "themeDark") },
              { v: "auto", label: tr(lang, "themeAuto") },
            ]}
          />
        </Field>

        <Field label={tr(lang, "setSourcesDefault")}>
          <Seg<"collapsed" | "expanded">
            value={srcDefaultOpen ? "expanded" : "collapsed"}
            onPick={(v) => onSrcDefaultOpen(v === "expanded")}
            options={[
              { v: "collapsed", label: tr(lang, "srcCollapsed") },
              { v: "expanded", label: tr(lang, "srcExpanded") },
            ]}
          />
        </Field>

        <Field label={tr(lang, "setHistory")}>
          <button
            onClick={onClearHistory}
            className="w-full py-2.5 rounded-2xl glass text-red-500 font-semibold text-sm hover:bg-red-500/10 transition"
          >
            {tr(lang, "clearAll")}
          </button>
        </Field>

        {/* Account — only in Supabase mode (auth.enabled). Shows who's signed in + a sign-out. */}
        {auth.enabled && auth.user && (
          <Field label={tr(lang, "account")}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-ink/60 truncate">{auth.user.email}</span>
              <button
                onClick={() => auth.signOut()}
                className="px-4 py-2 rounded-2xl glass text-red-500 font-semibold text-sm hover:bg-red-500/10 transition shrink-0"
              >
                {tr(lang, "signOut")}
              </button>
            </div>
          </Field>
        )}

        <div className="pt-3 border-t border-white/60">
          <p className="text-xs text-ink/55 leading-relaxed">{tr(lang, "aboutText")}</p>
          <p className="text-[11px] text-ink/40 mt-1">{tr(lang, "appVersion")}</p>
        </div>
      </div>
    </Modal>
  );
}
