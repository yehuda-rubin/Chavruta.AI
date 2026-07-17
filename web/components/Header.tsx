import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

// Ported from the static UI <header> — same classes, same layout.
export function Header({ lang, onToggleLang }: { lang: Lang; onToggleLang: () => void }) {
  return (
    <header className="h-[70px] flex items-center justify-between px-8 shrink-0">
      <div className="flex items-center gap-3">
        <div className="h-11 w-11 rounded-2xl grad grid place-items-center text-white font-serif text-xl font-black shadow-lg shadow-tekhelet/20">
          ח
        </div>
        <h1 className="font-serif text-2xl font-bold text-tekhelet">{tr(lang, "brand")}</h1>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onToggleLang}
          className="px-4 py-2 rounded-full glass text-ink/70 text-sm"
          title="עברית · EN"
        >
          עברית · EN
        </button>
        <button
          className="h-10 w-10 rounded-full glass grid place-items-center"
          title={tr(lang, "settings")}
        >
          <Icon name="settings" />
        </button>
        <div className="h-10 w-10 rounded-full grad grid place-items-center text-white font-bold">א</div>
      </div>
    </header>
  );
}
