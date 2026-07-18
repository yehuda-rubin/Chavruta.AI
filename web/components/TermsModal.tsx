"use client";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { termsSections, TERMS_VERSION, TERMS_EFFECTIVE } from "@/lib/legal";
import { Modal } from "./Modal";

// Terms of Use, rendered from lib/legal.ts (mirrors docs/legal/terms-{he,en}.md). Opened from the
// sign-up consent line and available anywhere the terms need to be shown.
export function TermsModal({ open, lang, onClose }: { open: boolean; lang: Lang; onClose: () => void }) {
  return (
    <Modal open={open} title={tr(lang, "termsTitle")} onClose={onClose} maxW="max-w-lg">
      <div className="flex flex-col gap-4 overflow-y-auto">
        <p className="text-xs text-ink/50">
          {tr(lang, "termsVersionLabel")} {TERMS_VERSION} · {tr(lang, "termsEffectiveLabel")} {TERMS_EFFECTIVE}
        </p>
        {termsSections(lang).map((s, i) => (
          <div key={i}>
            <h4 className="font-serif font-bold text-tekhelet mb-1">{`${i + 1}. ${s.heading}`}</h4>
            <p className="text-sm text-ink/75 leading-relaxed whitespace-pre-line">{s.body}</p>
          </div>
        ))}
      </div>
    </Modal>
  );
}
