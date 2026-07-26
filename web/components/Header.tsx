import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

// Ported from the static UI <header>. On mobile it also carries the toggles that open the side panels
// (which are inline on desktop and drawers on mobile).
export function Header({
  lang,
  theme,
  remaining,
  remainingWeek,
  onToggleLang,
  onToggleTheme,
  onOpenSessions,
  onOpenSources,
}: {
  lang: Lang;
  theme: "light" | "dark";
  remaining?: number | null;      // questions left today; null/undefined = uncapped (no pill)
  remainingWeek?: number | null;  // left this week — shown instead when it's the tighter of the two
  onToggleLang: () => void;
  onToggleTheme: () => void;
  onOpenSessions?: () => void;  // mobile only — opens the sessions drawer
  onOpenSources?: () => void;   // mobile only — opens the sources drawer
}) {
  return (
    <header className="h-[70px] flex items-center justify-between px-4 lg:px-8 shrink-0">
      <div className="flex items-center gap-2 lg:gap-3">
        <button
          onClick={onOpenSessions}
          className="lg:hidden h-10 w-10 rounded-2xl glass grid place-items-center text-tekhelet"
          title={tr(lang, "openChatsTip")}
        >
          <Icon name="forum" />
        </button>
        <div className="h-11 w-11 rounded-2xl grad grid place-items-center text-white font-serif text-xl font-black shadow-lg shadow-tekhelet/20">
          ח
        </div>
        <h1 className="font-serif text-2xl font-bold text-tekhelet">{tr(lang, "brand")}</h1>
      </div>
      <div className="flex items-center gap-2">
        {/* Show whichever cap is closer to stopping them. Showing only the daily figure would read
            as "38 left" right up to the moment the WEEK runs out, which is the one number that
            would have let them plan. */}
        {(() => {
          const binding =
            typeof remainingWeek === "number" &&
            (typeof remaining !== "number" || remainingWeek < remaining)
              ? { n: remainingWeek, label: tr(lang, "weeklyRemaining") }
              : typeof remaining === "number"
                ? { n: remaining, label: tr(lang, "remainingToday") }
                : null;
          if (!binding) return null;
          return (
            <span
              className={
                "px-3 py-1.5 rounded-full glass text-xs font-semibold " +
                (binding.n === 0 ? "text-red-500" : "text-ink/60")
              }
              title={binding.label}
            >
              {binding.n} {binding.label}
            </span>
          );
        })()}
        <button
          onClick={onOpenSources}
          className="lg:hidden h-10 w-10 rounded-full glass grid place-items-center text-tekhelet"
          title={tr(lang, "openSourcesTip")}
        >
          <Icon name="menu_book" />
        </button>
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
        <div className="hidden sm:grid h-10 w-10 rounded-full grad place-items-center text-white font-bold">א</div>
      </div>
    </header>
  );
}
