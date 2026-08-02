"use client";
import { useEffect, useState } from "react";
import { Icon } from "./Icon";

type A11ySettings = {
  textStep: 0 | 1 | 2 | 3;
  contrast: boolean;
  underline: boolean;
  reduceMotion: boolean;
};

const DEFAULTS: A11ySettings = { textStep: 0, contrast: false, underline: false, reduceMotion: false };
const STORAGE_KEY = "chavruta-a11y";

const STR = {
  he: {
    open: "תפריט נגישות",
    close: "סגור",
    title: "נגישות",
    textSize: "גודל טקסט",
    contrast: "ניגודיות גבוהה",
    underline: "הדגשת קישורים",
    reduceMotion: "עצירת אנימציות",
    reset: "איפוס",
    statement: "הצהרת נגישות",
  },
  en: {
    open: "Accessibility menu",
    close: "Close",
    title: "Accessibility",
    textSize: "Text size",
    contrast: "High contrast",
    underline: "Underline links",
    reduceMotion: "Stop animations",
    reset: "Reset",
    statement: "Accessibility Statement",
  },
} as const;

// html font-size scales every rem-based size in the app (Tailwind included); the rest go on <body>
// as classes, matching the existing theme-dark convention in globals.css.
function apply(settings: A11ySettings) {
  document.documentElement.style.fontSize = settings.textStep === 0 ? "" : `${100 + settings.textStep * 12.5}%`;
  const body = document.body;
  body.classList.toggle("a11y-contrast", settings.contrast);
  body.classList.toggle("a11y-underline", settings.underline);
  body.classList.toggle("a11y-reduce-motion", settings.reduceMotion);
}

// Floating accessibility toolbar — mounted once in the root layout so every route (chat app, legal
// pages, sign-in) gets it. Settings persist in localStorage and apply as soon as this mounts.
// Deliberately tracks <html lang> via a MutationObserver instead of taking a `lang` prop: the widget
// lives above every page's own language state (RootLayout is a server component), and this way no
// page needs to be wired up to hand it a value.
export function AccessibilityWidget() {
  const [open, setOpen] = useState(false);
  const [lang, setLang] = useState<"he" | "en">("he");
  const [settings, setSettings] = useState<A11ySettings>(DEFAULTS);
  const t = STR[lang];

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = { ...DEFAULTS, ...JSON.parse(raw) };
        setSettings(saved);
        apply(saved);
      }
    } catch {}
  }, []);

  useEffect(() => {
    const sync = () => setLang(document.documentElement.lang === "en" ? "en" : "he");
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function update(patch: Partial<A11ySettings>) {
    const next = { ...settings, ...patch };
    setSettings(next);
    apply(next);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
  }

  function reset() {
    setSettings(DEFAULTS);
    apply(DEFAULTS);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  }

  const dir = lang === "he" ? "rtl" : "ltr";
  const corner = dir === "rtl" ? "left-4" : "right-4";

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={t.open}
        aria-expanded={open}
        className={`fixed bottom-4 ${corner} z-40 h-12 w-12 rounded-full grad text-white
                    shadow-lg grid place-items-center hover:opacity-95 transition`}
      >
        <Icon name="accessibility_new" className="text-[26px]" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t.title}
          dir={dir}
          className={`fixed bottom-20 ${corner} z-40 w-72 glass rounded-[24px] p-4 flex flex-col gap-3`}
        >
          <div className="flex items-center justify-between">
            <h3 className="font-serif text-base font-bold text-tekhelet">{t.title}</h3>
            <button
              onClick={() => setOpen(false)}
              aria-label={t.close}
              className="h-7 w-7 rounded-full glass grid place-items-center text-ink/60 hover:text-tekhelet"
            >
              <Icon name="close" className="text-[16px]" />
            </button>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-bold text-ink/55">{t.textSize}</span>
            <div className="flex bg-white/50 rounded-2xl p-1 text-sm font-semibold gap-1">
              {([0, 1, 2, 3] as const).map((step) => (
                <button
                  key={step}
                  onClick={() => update({ textStep: step })}
                  aria-pressed={settings.textStep === step}
                  className={"flex-1 py-1.5 rounded-full transition " +
                    (settings.textStep === step ? "grad text-white" : "text-ink/60 hover:text-tekhelet")}
                >
                  {step === 0 ? "A" : "A" + "+".repeat(step)}
                </button>
              ))}
            </div>
          </div>

          {(
            [
              { key: "contrast", label: t.contrast },
              { key: "underline", label: t.underline },
              { key: "reduceMotion", label: t.reduceMotion },
            ] as const
          ).map((row) => (
            <label key={row.key} className="flex items-center justify-between gap-2 text-sm text-ink/75 cursor-pointer">
              <span>{row.label}</span>
              <input
                type="checkbox"
                checked={settings[row.key]}
                onChange={(e) => update({ [row.key]: e.target.checked })}
                className="accent-tekhelet h-4 w-4"
              />
            </label>
          ))}

          <button
            onClick={reset}
            className="mt-1 py-2 rounded-2xl glass text-red-500 font-semibold text-xs hover:bg-red-500/10 transition"
          >
            {t.reset}
          </button>

          <a
            href="/accessibility"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-center text-tekhelet/70 hover:text-tekhelet hover:underline"
          >
            {t.statement}
          </a>
        </div>
      )}
    </>
  );
}
