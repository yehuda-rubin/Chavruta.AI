import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ExamplesShell, Paragraphs } from "@/components/ExamplesShell";
import { lessons, LESSON_KINDS } from "@/lib/examples";

type Props = { params: Promise<{ slug: string }> };

const ORDER = ["full", "flow", "sheet"];

export function generateStaticParams() {
  return lessons.map((l) => ({ slug: l.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const lesson = lessons.find((l) => l.slug === slug);
  return lesson ? { title: `${lesson.title} | שיעור לדוגמה`, description: "שיעור לדוגמה של חברותא: שיעור מלא, מהלך ודף מקורות." } : {};
}

export default async function LessonExample({ params }: Props) {
  const { slug } = await params;
  const lesson = lessons.find((l) => l.slug === slug);
  if (!lesson) notFound();
  const files = ORDER.map((k) => lesson.files.find((f) => f.kind === k)).filter((f): f is NonNullable<typeof f> => !!f);

  return (
    <ExamplesShell back={{ href: "/examples", label: "כל הדוגמאות" }}>
      <h1 className="text-2xl font-bold text-ink">{lesson.title}</h1>
      <nav className="flex gap-3 text-sm">
        {files.map((f) => (
          <a key={f.kind} href={`#${f.kind}`} className="underline text-tekhelet">{LESSON_KINDS[f.kind] ?? f.title}</a>
        ))}
      </nav>
      {files.map((f) => (
        <article key={f.kind} id={f.kind} className="glass rounded-[24px] p-6 flex flex-col gap-4 scroll-mt-4">
          <h2 className="text-lg font-bold text-tekhelet">{LESSON_KINDS[f.kind] ?? f.title}</h2>
          <Paragraphs text={f.content.replace(/^> ?/gm, "")} />
        </article>
      ))}
    </ExamplesShell>
  );
}
