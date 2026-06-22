import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Lang = 'he' | 'en'

/** UI string table. Every key has a Hebrew and an English form. */
const STRINGS = {
  appName:            { he: 'חברותא AI',                 en: 'Chavruta AI' },
  newDiscussion:      { he: 'דיון חדש',                  en: 'New Discussion' },
  recent:             { he: 'שיחות אחרונות',             en: 'Recent' },
  noSessions:         { he: 'אין שיחות עדיין',           en: 'No conversations yet' },
  settings:           { he: 'הגדרות',                    en: 'Settings' },
  support:            { he: 'תמיכה',                      en: 'Support' },
  discussionTitle:    { he: 'דיון עם חברותא AI',         en: 'Discussion with Chavruta AI' },
  newDiscussionTitle: { he: 'דיון חדש',                  en: 'New discussion' },
  relatedSources:     { he: 'מקורות קשורים',             en: 'Related Sources' },
  noSources:          { he: 'המקורות יופיעו כאן',        en: 'Sources will appear here' },
  addSource:          { he: 'הוסף מקור לדיון',           en: 'Add source' },
  goal:               { he: 'מטרה',                      en: 'Goal' },
  inputPlaceholder:   { he: 'שאל את החברותא על הסוגיא…', en: 'Ask Chavruta about the sugya…' },
  attach:             { he: 'צירוף קובץ (בקרוב)',        en: 'Attach file (coming soon)' },
  send:               { he: 'שלח',                       en: 'Send' },
  retrieving:         { he: 'מאחזר מקורות…',             en: 'Retrieving sources…' },
  you:                { he: 'אתה',                        en: 'You' },
  aiName:             { he: 'Modern Sage AI',             en: 'Modern Sage AI' },
  showSources:        { he: 'הצג מקורות',                en: 'Show sources' },
  hideSources:        { he: 'הסתר מקורות',               en: 'Hide sources' },
  ungrounded:         { he: 'לא נמצא מקור מעוגן — לא הומצאה תשובה', en: 'No grounded source found — nothing was invented' },
  disclaimer:         { he: 'נבנה ביראת שמיים • המידע אינו מהווה פסיקת הלכה למעשה.',
                        en: 'Built with reverence • Not a halachic ruling.' },
  delete:             { he: 'מחק שיחה',                  en: 'Delete conversation' },
  emptyGreeting:      { he: 'ברוך הבא ללימוד. שאל שאלה על הסוגיא והחברותא תשיב ממקורות מצוטטים.',
                        en: 'Welcome. Ask about the sugya and Chavruta will answer from cited sources.' },
  share:              { he: 'שתף',                       en: 'Share' },
  options:            { he: 'אפשרויות',                  en: 'Options' },
  themeLight:         { he: 'מצב בהיר',                  en: 'Light Mode' },
  themeDark:          { he: 'מצב כהה',                   en: 'Dark Mode' },
  // Intents (aligned with the backend: qa / explain / lesson)
  intent_qa:          { he: 'שאלות כלליות',              en: 'Q&A' },
  intent_explain:     { he: 'הסבר',                      en: 'Explain' },
  intent_lesson:      { he: 'שיעור',                     en: 'Lesson' },
} as const

export type StringKey = keyof typeof STRINGS

interface LangCtx {
  lang: Lang
  setLang: (l: Lang) => void
  toggle: () => void
  t: (key: StringKey) => string
  dir: 'rtl' | 'ltr'
}

const LangContext = createContext<LangCtx | null>(null)

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const saved = localStorage.getItem('chavruta-lang')
    return saved === 'en' ? 'en' : 'he'
  })

  const dir: 'rtl' | 'ltr' = lang === 'he' ? 'rtl' : 'ltr'

  useEffect(() => {
    localStorage.setItem('chavruta-lang', lang)
    document.documentElement.lang = lang
    document.documentElement.dir = dir
  }, [lang, dir])

  const value: LangCtx = {
    lang,
    setLang,
    toggle: () => setLang(prev => (prev === 'he' ? 'en' : 'he')),
    t: (key: StringKey) => STRINGS[key][lang],
    dir,
  }

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>
}

export function useLang(): LangCtx {
  const ctx = useContext(LangContext)
  if (!ctx) throw new Error('useLang must be used within LangProvider')
  return ctx
}
