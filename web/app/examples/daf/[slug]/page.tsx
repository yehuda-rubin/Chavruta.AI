import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ExamplesShell, Paragraphs } from "@/components/ExamplesShell";
import { dafPages, dedupeSources } from "@/lib/examples";

type Props = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return dafPages.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const page = dafPages.find((p) => p.slug === slug);
  return page ? { title: `${page.title} | חברותא`, description: "לימוד דף בגמרא עם חברותא, עם מקורות ורישיונות." } : {};
}

export default async function DafExample({ params }: Props) {
  const { slug } = await params;
  const page = dafPages.find((p) => p.slug === slug);
  if (!page) notFound();

  return (
    <ExamplesShell back={{ href: "/examples", label: "כל הדוגמאות" }}>
      <h1 className="text-2xl font-bold text-ink">{page.title}</h1>
      {page.turns.map((t, i) => {
        const sources = dedupeSources(t.sources);
        return (
          <article key={i} className="glass rounded-[24px] p-6 flex flex-col gap-4">
            <h2 className="text-base font-bold text-tekhelet">{t.q}</h2>
            <Paragraphs text={t.answer} />
            {sources.length > 0 && (
              <details className="text-xs text-ink/75">
                <summary className="cursor-pointer font-semibold">מקורות ורישיונות ({sources.length})</summary>
                <table className="mt-2 w-full text-right border-separate border-spacing-y-1">
                  <thead>
                    <tr className="text-ink/60">
                      <th className="font-semibold">מקור</th>
                      <th className="font-semibold">מהדורה</th>
                      <th className="font-semibold">רישיון</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((s, j) => (
                      <tr key={j}>
                        <td>{s.name}</td>
                        <td dir="ltr" className="text-right">{s.edition}</td>
                        <td dir="ltr" className="text-right">{s.license}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </article>
        );
      })}
    </ExamplesShell>
  );
}
