// i18n — Hebrew-first, matching the strings in the active static UI. Core keys for the shell,
// chat, and source panel; extend as more screens are ported.
import type { Lang } from "./types";

export const STRINGS = {
  he: {
    brand: "חברותא",
    newChat: "+ דיון חדש",
    newChatShort: "דיון חדש",
    recentChats: "שיחות אחרונות",
    myShiurim: "השיעורים שלי",
    settingsTitle: "הגדרות",
    supportTitle: "תמיכה",
    settings: "הגדרות",
    collapse: "כווץ",
    openChats: "פתח שיחות",
    openSources: "פתח מקורות",
    relatedSources: "מקורות קשורים",
    sourcesHint: "המקורות יופיעו כאן",
    noText: "אין טקסט זמין למקור זה.",
    srcEdition: "מהדורה",
    srcLicense: "רישיון",
    viewOnSefaria: "צפה ב-Sefaria",
    addSource: "+ הוסף מקור",
    welcomeTitle: "חברותא AI",
    welcomeBody: "ברוך הבא ללימוד. שאל שאלה על הסוגיא והחברותא תשיב ממקורות מצוטטים.",
    askPlaceholder: "שאל את החברותא…",
    footer: "נבנה ביראת שמיים · אינו פסיקת הלכה למעשה",
    send: "שלח",
    thinking: "החברותא חושבת…",
    deleteChat: "מחק שיחה",
  },
  en: {
    brand: "Chavruta",
    newChat: "+ New discussion",
    newChatShort: "New discussion",
    recentChats: "Recent chats",
    myShiurim: "My Shiurim",
    settingsTitle: "Settings",
    supportTitle: "Support",
    settings: "Settings",
    collapse: "Collapse",
    openChats: "Open chats",
    openSources: "Open sources",
    relatedSources: "Related sources",
    sourcesHint: "Sources will appear here",
    noText: "No text available for this source.",
    srcEdition: "Edition",
    srcLicense: "License",
    viewOnSefaria: "View on Sefaria",
    addSource: "+ Add source",
    welcomeTitle: "Chavruta AI",
    welcomeBody: "Welcome to the study. Ask about the sugya and the Chavruta will answer with cited sources.",
    askPlaceholder: "Ask the Chavruta…",
    footer: "Built in reverence · Not a halachic ruling",
    send: "Send",
    thinking: "The Chavruta is thinking…",
    deleteChat: "Delete chat",
  },
} as const;

export type StringKey = keyof (typeof STRINGS)["he"];

export function tr(lang: Lang, key: StringKey): string {
  return STRINGS[lang][key] ?? STRINGS.he[key] ?? key;
}
