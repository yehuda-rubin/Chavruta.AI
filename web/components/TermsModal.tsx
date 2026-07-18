"use client";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { termsSections, TERMS_VERSION, TERMS_EFFECTIVE } from "@/lib/legal";
import { LegalModal } from "./LegalModal";

// Terms of Use, rendered from lib/legal.ts (mirrors docs/legal/terms-{he,en}.md).
export function TermsModal({ open, lang, onClose }: { open: boolean; lang: Lang; onClose: () => void }) {
  return (
    <LegalModal
      open={open}
      lang={lang}
      onClose={onClose}
      title={tr(lang, "termsTitle")}
      versionLine={`${tr(lang, "termsVersionLabel")} ${TERMS_VERSION} · ${tr(lang, "termsEffectiveLabel")} ${TERMS_EFFECTIVE}`}
      sections={termsSections(lang)}
    />
  );
}
