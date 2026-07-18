"use client";
import type { Lang } from "@/lib/types";
import { Modal } from "./Modal";

// Generic renderer for a legal document (Terms / Privacy) — a numbered list of heading+body sections
// with a version/effective line. Terms and Privacy are thin wrappers over this.
export function LegalModal({
  open,
  lang,
  onClose,
  title,
  versionLine,
  sections,
}: {
  open: boolean;
  lang: Lang;
  onClose: () => void;
  title: string;
  versionLine: string;
  sections: { heading: string; body: string }[];
}) {
  return (
    <Modal open={open} title={title} onClose={onClose} maxW="max-w-lg">
      <div className="flex flex-col gap-4 overflow-y-auto">
        <p className="text-xs text-ink/50">{versionLine}</p>
        {sections.map((s, i) => (
          <div key={i}>
            <h4 className="font-serif font-bold text-tekhelet mb-1">{`${i + 1}. ${s.heading}`}</h4>
            <p className="text-sm text-ink/75 leading-relaxed whitespace-pre-line">{s.body}</p>
          </div>
        ))}
      </div>
    </Modal>
  );
}
