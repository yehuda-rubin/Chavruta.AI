import Link from "next/link";
import type { ReactNode } from "react";

// Shared frame for the public examples pages (/examples/...). Server component, Hebrew only: these
// are fixed, reviewed samples, not live answers. The page owns its scroll because <body> is
// overflow-hidden for the chat layout (same reason as LegalPage).
export function ExamplesShell({ children, back }: { children: ReactNode; back?: { href: string; label: string } }) {
  return (
    <div dir="rtl" className="h-dvh overflow-y-auto py-8 px-4">
      <div className="max-w-3xl mx-auto flex flex-col gap-5">
        <header className="flex items-center justify-between gap-3">
          <Link href={back?.href ?? "/"} className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            ← {back?.label ?? "חזרה לחברותא"}
          </Link>
          <Link href="/signup?mode=up" className="rounded-full bg-indigo text-white text-sm font-semibold px-4 py-2">
            נסו בעצמכם, חינם
          </Link>
        </header>
        {children}
        <footer className="glass rounded-[20px] p-5 text-xs text-ink/70 leading-relaxed">
          <p>
            אלה דוגמאות קבועות שנוצרו על ידי חברותא ונבדקו, לא תשובות חיות. חברותא היא כלי לימוד שמראה מקורות
            ואינה מחליפה רב. בשאלות הלכה למעשה יש לפנות לרב.
          </p>
          <p className="mt-2">
            <Link href="/terms" className="underline">תנאי שימוש</Link>
            {" · "}
            <Link href="/privacy" className="underline">פרטיות</Link>
            {" · "}
            <Link href="/limits" className="underline">מכסות ותוכניות</Link>
          </p>
        </footer>
      </div>
    </div>
  );
}

export function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n{2,}/).map((p, i) => (
        <p key={i} className="whitespace-pre-line leading-[1.9] text-[15px] text-ink">
          {p.split(/\*\*(.+?)\*\*/g).map((part, j) => (j % 2 === 1 ? <strong key={j}>{part}</strong> : part))}
        </p>
      ))}
    </>
  );
}
