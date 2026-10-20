import data from "@/content/examples.json";

export interface ExampleSource { name: string; edition: string; license: string }
export interface ExampleTurn { q: string; answer: string; sources: ExampleSource[] }
export interface DafExample { slug: string; title: string; tractate: string; daf: string; turns: ExampleTurn[] }
export interface LessonFile { kind: string; title: string; content: string }
export interface LessonExample { slug: string; title: string; request?: string; files: LessonFile[] }

// A lesson that did not pass editorial review stays out of the public catalogue until it is rebuilt.
const HELD_BACK = new Set(["halacha-shehechiyanu"]);

export const dafPages = (data as unknown as { dafPages: DafExample[] }).dafPages;
export const lessons = (data as unknown as { lessons: LessonExample[] }).lessons.filter((l) => !HELD_BACK.has(l.slug));

export const LESSON_KINDS: Record<string, string> = {
  full: "השיעור המלא",
  flow: "מהלך השיעור",
  sheet: "דף מקורות",
};

// Sefaria writes a Talmud page as "2." (amud a) or "2:" (amud b); show it the way a reader expects.
export function readableName(name: string): string {
  return name.replace(/(\d+)\.\s*$/, "$1א").replace(/(\d+):\s*$/, "$1ב");
}

export function dedupeSources(sources: ExampleSource[]): ExampleSource[] {
  const seen = new Set<string>();
  return sources.map((s) => ({ ...s, name: readableName(s.name) })).filter((s) => {
    const k = `${s.name}|${s.edition}|${s.license}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}
