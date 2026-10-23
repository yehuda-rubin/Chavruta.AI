import type { Metadata } from "next";
import Link from "next/link";
import { ExamplesShell } from "@/components/ExamplesShell";
import { dafPages, lessons } from "@/lib/examples";

export const metadata: Metadata = {
  title: "דוגמאות ללימוד עם חברותא",
  description: "דפי דף יומי ושיעורים לדוגמה, עם מקורות ורישיונות, כדי לראות איך נראה לימוד עם חברותא.",
};

export default function ExamplesIndex() {
  return (
    <ExamplesShell>
      <section className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold text-ink">דוגמאות ללימוד עם חברותא</h1>
        <p className="text-sm text-ink/75 leading-relaxed">
          כך נראה לימוד של דף בגמרא ושיעור בנושא. לכל תשובה מצורפת רשימת המקורות והרישיונות שלהם.
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-bold text-ink">הדף היומי</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {dafPages.map((p) => (
            <Link key={p.slug} href={`/examples/daf/${p.slug}`} className="glass rounded-[20px] p-4 hover:shadow-md transition">
              <div className="font-semibold text-ink">{p.title}</div>
              <div className="text-xs text-ink/65 mt-1">{p.turns.length} שאלות ותשובות</div>
            </Link>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-bold text-ink">שיעורים</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {lessons.map((l) => (
            <Link key={l.slug} href={`/examples/lesson/${l.slug}`} className="glass rounded-[20px] p-4 hover:shadow-md transition">
              <div className="font-semibold text-ink">{l.title}</div>
              <div className="text-xs text-ink/65 mt-1">שיעור מלא, מהלך ודף מקורות</div>
            </Link>
          ))}
        </div>
      </section>
    </ExamplesShell>
  );
}
