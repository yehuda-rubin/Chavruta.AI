"use client";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Modal } from "./Modal";

const CONTACT_EMAIL = "rubinyehuda8@gmail.com";

// Support — quick guide, halachic disclaimer, limitations, and contact. Ported from the static UI.
export function SupportModal({ open, lang, onClose }: { open: boolean; lang: Lang; onClose: () => void }) {
  return (
    <Modal open={open} title={tr(lang, "supportTitle")} onClose={onClose} maxW="max-w-lg">
      <div className="flex flex-col gap-4 overflow-y-auto">
        <p className="text-sm text-ink/70 leading-relaxed">{tr(lang, "supIntro")}</p>

        <div>
          <h4 className="font-serif font-bold text-tekhelet mb-1.5">{tr(lang, "supGuideTitle")}</h4>
          <ul className="text-sm text-ink/70 leading-relaxed list-disc list-inside flex flex-col gap-1">
            <li>{tr(lang, "supGuideModes")}</li>
            <li>{tr(lang, "supGuideAdd")}</li>
            <li>{tr(lang, "supGuidePanels")}</li>
          </ul>
        </div>

        <div className="p-3.5 rounded-2xl bg-gold/10 ring-1 ring-gold/20">
          <h4 className="font-serif font-bold text-gold mb-1">{tr(lang, "supHalachaTitle")}</h4>
          <p className="text-sm text-ink/75 leading-relaxed">{tr(lang, "supHalacha")}</p>
        </div>

        <div className="p-3.5 rounded-2xl bg-red-500/5 ring-1 ring-red-500/15">
          <h4 className="font-serif font-bold text-red-500/90 mb-1">{tr(lang, "supLimitsTitle")}</h4>
          <p className="text-sm text-ink/75 leading-relaxed">{tr(lang, "supLimits")}</p>
        </div>

        <div>
          <h4 className="font-serif font-bold text-tekhelet mb-1">{tr(lang, "supContactTitle")}</h4>
          <p className="text-sm text-ink/70">
            <span>{tr(lang, "supContact")}</span>{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} dir="ltr" className="text-indigo font-semibold hover:underline">
              {CONTACT_EMAIL}
            </a>
          </p>
          <Link
            href="/feedback"
            onClick={onClose}
            className="mt-2 inline-block text-sm text-tekhelet/80 font-semibold hover:text-tekhelet"
          >
            {tr(lang, "supFeedbackCta")}
          </Link>
        </div>

        {/* Legal docs are their own pages (/terms, /privacy) — open in a new tab. */}
        <div className="flex gap-4">
          <a href="/terms" target="_blank" rel="noopener noreferrer"
             className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            {tr(lang, "termsLink")}
          </a>
          <a href="/privacy" target="_blank" rel="noopener noreferrer"
             className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            {tr(lang, "privacyLink")}
          </a>
        </div>
      </div>
    </Modal>
  );
}
