import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

// Ported from the static UI <header>. On mobile it also carries the toggles that open the side panels
// (which are inline on desktop and drawers on mobile).
export function Header({
  lang,
  theme,
  dayLeft,
  weekLeft,
  onToggleLang,
  onToggleTheme,
  onOpenSessions,
  onOpenSources,
  onNewChat,
  isAdmin = false,
}: {
  lang: Lang;
  theme: "light" | "dark";
  dayLeft?: number | null;     // fraction of today's conversation allowance left; null = uncapped
  weekLeft?: number | null;    // fraction of the week's left — the gauge shows whichever is lower
  onToggleLang: () => void;
  onToggleTheme: () => void;
  onOpenSessions?: () => void;  // mobile only — opens the sessions drawer
  onOpenSources?: () => void;   // mobile only — opens the sources drawer
  onNewChat?: () => void;       // mobile only — starts a new chat directly, no drawer detour
  isAdmin?: boolean;            // from me.is_admin (app/api.py::_is_admin) — hidden entirely, not
                                // just disabled, for the near-everyone who isn't the admin account.
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
        {/* Starting a new chat used to take two taps on mobile (open the sessions drawer, then tap
            "+ new chat" inside it) — this puts the same action one tap away, right in the header. */}
        <button
          onClick={onNewChat}
          className="lg:hidden h-10 w-10 rounded-2xl grad text-white grid place-items-center shadow-lg shadow-tekhelet/20"
          title={tr(lang, "newChatShort")}
        >
          <Icon name="add" />
        </button>
        <div className="h-11 w-11 rounded-2xl grad grid place-items-center text-white font-serif text-xl font-black shadow-lg shadow-tekhelet/20">
          ח
        </div>
        <h1 className="font-serif text-2xl font-bold text-tekhelet hidden sm:block">{tr(lang, "brand")}</h1>
      </div>
      <div className="flex items-center gap-2">
        {/* A gauge of whichever pool is closest to empty — no absolute figure, by design (see
            app/plans.py). The daily fraction alone would read as "plenty left" right up to the
            moment the WEEK runs out, which is the one thing a user needs to see coming. */}
        {(() => {
          const pools = [dayLeft, weekLeft].filter((v): v is number => typeof v === "number");
          if (!pools.length) return null;
          const left = Math.min(...pools);
          const pct = Math.round(left * 100);
          const tone = left === 0 ? "text-red-500" : left <= 0.15 ? "text-amber-600" : "text-ink/60";
          const bar = left === 0 ? "bg-red-500" : left <= 0.15 ? "bg-amber-500" : "bg-tekhelet/60";
          return (
            <span
              className={"px-3 py-1.5 rounded-full glass text-xs font-semibold flex items-center gap-2 " + tone}
              title={`${tr(lang, "usageLeft")} — ${pct}%`}
              role="img"
              aria-label={`${tr(lang, "usageLeft")}: ${pct}%`}
            >
              <span className="hidden sm:inline">{tr(lang, "usageLeft")}</span>
              <span className="w-12 h-1.5 rounded-full bg-ink/10 overflow-hidden" aria-hidden="true">
                <span className={"block h-full rounded-full " + bar} style={{ width: `${pct}%` }} />
              </span>
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
          className="px-4 py-2 rounded-full glass text-ink/70 text-sm whitespace-nowrap"
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
        {isAdmin && (
          <Link
            href="/admin"
            className="h-10 w-10 rounded-full glass grid place-items-center text-tekhelet"
            title="דשבורד ניהול"
          >
            <Icon name="admin_panel_settings" />
          </Link>
        )}
        <div className="hidden sm:grid h-10 w-10 rounded-full grad place-items-center text-white font-bold">א</div>
      </div>
    </header>
  );
}
