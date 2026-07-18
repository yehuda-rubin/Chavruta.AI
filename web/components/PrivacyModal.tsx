"use client";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { privacySections, PRIVACY_VERSION, PRIVACY_EFFECTIVE } from "@/lib/legal";
import { LegalModal } from "./LegalModal";

// Privacy Policy, rendered from lib/legal.ts (mirrors docs/legal/privacy-{he,en}.md).
export function PrivacyModal({ open, lang, onClose }: { open: boolean; lang: Lang; onClose: () => void }) {
  return (
    <LegalModal
      open={open}
      lang={lang}
      onClose={onClose}
      title={tr(lang, "privacyTitle")}
      versionLine={`${tr(lang, "termsVersionLabel")} ${PRIVACY_VERSION} · ${tr(lang, "termsEffectiveLabel")} ${PRIVACY_EFFECTIVE}`}
      sections={privacySections(lang)}
    />
  );
}
