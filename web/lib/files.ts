import type { Lang } from "./types";
import { tr } from "./i18n";

// Icon + label for a user-added source, by filename — matches the static UI's fileKind.
export function fileKind(name: string, lang: Lang): { icon: string; label: string } {
  const n = (name || "").toLowerCase();
  if (/\.(png|jpe?g|gif|webp|bmp|heic)$/.test(n)) return { icon: "image", label: tr(lang, "kindImage") };
  if (n.endsWith(".pdf")) return { icon: "picture_as_pdf", label: tr(lang, "kindPdf") };
  if (/\.(docx?|rtf|odt)$/.test(n)) return { icon: "description", label: tr(lang, "kindWord") };
  return { icon: "notes", label: tr(lang, "kindText") };
}

export function fileToDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}
