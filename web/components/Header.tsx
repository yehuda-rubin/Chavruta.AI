import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

// Ported from the static UI <header>. On mobile it also carries the toggles that open the side panels
// (which are inline on desktop and drawers on mobile).
export function Header({
  lang,
  theme,
  onToggleLang,
  onToggleTheme,
  onOpenSessions,
  onOpenSources,
  onNewChat,
  isAdmin = false,
  orgRole = "",
}: {
  lang: Lang;
  theme: "light" | "dark";
  onToggleLang: () => void;
  onToggleTheme: () => void;
  onOpenSessions?: () => void;  // mobile only — opens the sessions drawer
  onOpenSources?: () => void;   // mobile only — opens the sources drawer
  onNewChat?: () => void;       // starts a new chat directly; also the brand mark's click on every
                                 // viewport, not just mobile's dedicated + button
  isAdmin?: boolean;            // from me.is_admin (app/api.py::_is_admin) — hidden entirely, not
                                // just disabled, for the near-everyone who isn't the admin account.
  orgRole?: string;             // from me.org_role. The school button shows for 'admin' and
                                // 'teacher' ONLY: a student belongs to a school but has nothing to
                                // manage there, so a button leading to a page of other people's
                                // usage would be a confusing dead end at best.
}) {
  // The operator belongs to no school, so their org_role is empty and this button never appeared for
  // them — the only way in was a link buried in the admin dashboard's sidebar, which is not where
  // anyone looks for it. The server already lets them in (/orgs/panel?demo=true, gated on _is_admin)
  // and opens the SYNTHETIC school, never a real one, so showing the button costs nothing and the
  // title says which school it is going to open.
  const canManageOrg = orgRole === "admin" || orgRole === "teacher" || !!isAdmin;
  const orgButtonTitle = orgRole ? "פאנל המוסד" : "פאנל מוסד (בית ספר לדוגמה)";
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
        {/* The brand mark doubles as "start a new chat" on every viewport, not just mobile's
            dedicated + button — the same convention as clicking a logo to go home. */}
        <button
          onClick={onNewChat}
          className="flex items-center gap-2 lg:gap-3 hover:opacity-80 transition"
          title={tr(lang, "newChatShort")}
        >
          <div className="h-11 w-11 rounded-2xl grad grid place-items-center text-white font-serif text-xl font-black shadow-lg shadow-tekhelet/20">
            ח
          </div>
          <h1 className="font-serif text-2xl font-bold text-tekhelet hidden sm:block">{tr(lang, "brand")}</h1>
        </button>
      </div>
      <div className="flex items-center gap-2">
        {/* Usage-remaining is Settings-only now (see SettingsModal) — the header stayed crowded at
            narrow widths / larger accessibility text-scale, and this pill was the easiest thing to
            move without losing the information anywhere. */}
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
        {canManageOrg && (
          <Link
            href="/school"
            className="h-10 w-10 rounded-full glass grid place-items-center text-tekhelet"
            title={orgButtonTitle}
          >
            <Icon name="school" />
          </Link>
        )}
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
