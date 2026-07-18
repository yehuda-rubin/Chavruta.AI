import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

// Ported from the static UI <header> — same classes, same layout.
export function Header({
  lang,
  theme,
  remaining,
  onToggleLang,
  onToggleTheme,
}: {
  lang: Lang;
  theme: "light" | "dark";
  remaining?: number | null;   // free-tier questions left today; null/undefined = unlimited (no pill)
  onToggleLang: () => void;
  onToggleTheme: () => void;
}) {
  return (
    <header className="h-[70px] flex items-center justify-between px-8 shrink-0">
      <div className="flex items-center gap-3">
        <div className="h-11 w-11 rounded-2xl grad grid place-items-center text-white font-serif text-xl font-black shadow-lg shadow-tekhelet/20">
          ח
        </div>
        <h1 className="font-serif text-2xl font-bold text-tekhelet">{tr(lang, "brand")}</h1>
      </div>
      <div className="flex items-center gap-2">
        {typeof remaining === "number" && (
          <span
            className={
              "px-3 py-1.5 rounded-full glass text-xs font-semibold " +
              (remaining === 0 ? "text-red-500" : "text-ink/60")
            }
            title={tr(lang, "remainingToday")}
          >
            {remaining} {tr(lang, "remainingToday")}
          </span>
        )}
        <button
          onClick={onToggleLang}
          className="px-4 py-2 rounded-full glass text-ink/70 text-sm"
          title="עברית · EN"
        >
          עברית · EN
        </button>
        <button
          onClick={onToggleTheme}
          className="h-10 w-10 rounded-full glass grid place-items-center"
          title={tr(lang, "settings")}
        >
          <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} />
        </button>
        <div className="h-10 w-10 rounded-full grad grid place-items-center text-white font-bold">א</div>
      </div>
    </header>
  );
}
