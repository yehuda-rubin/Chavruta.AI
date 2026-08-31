"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type HelperStatus } from "@/lib/api";
import { tr } from "@/lib/i18n";
import type { Lang } from "@/lib/types";
import { Icon } from "./Icon";

// The dev-helper side the PERSON sees: the invitation, and any notices the operator sent them.
//
// The invitation panel carries the full disclosure — what changes, what is stored, and that it is
// voluntary and unpaid. That placement is the point, not decoration: the privacy policy is where
// this is written down, but the moment of asking is where it has to be READ. Consent given without
// seeing what is collected is not informed consent, and a link to a policy page is a poor substitute
// for the two lines that actually matter.
//
// Renders nothing at all for the overwhelming majority of accounts, which is why it is safe to mount
// unconditionally: /helper/status answers {status:"none"} rather than erroring for them.
export function HelperPrompt({ lang }: { lang: Lang }) {
  const [st, setSt] = useState<HelperStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.helper.status().then(setSt).catch(() => setSt(null));
  }, []);

  if (!st) return null;

  const answer = async (accept: boolean) => {
    setBusy(true);
    try {
      setSt(accept ? await api.helper.accept() : await api.helper.decline());
    } catch {
      /* leave the panel up — an unanswered invitation is better than one that looks answered */
    } finally {
      setBusy(false);
    }
  };

  const dismiss = async (id: number) => {
    // Optimistic: the notice disappears now and the read receipt catches up. A failed write means
    // it reappears on the next load, which is the right way round for something already read.
    setSt({ ...st, unread: (st.unread || []).filter((m) => m.id !== id) });
    try {
      await api.helper.markRead(id);
    } catch {
      /* ignore */
    }
  };

  return (
    <>
      {st.status === "invited" && (
        <div
          role="dialog"
          aria-modal="false"
          aria-labelledby="helper-invite-title"
          className="glass rounded-[24px] p-5 flex flex-col gap-3 ring-1 ring-tekhelet/20"
        >
          <h2 id="helper-invite-title" className="font-serif text-lg font-bold text-tekhelet">
            {tr(lang, "helperInviteTitle")}
          </h2>
          {st.note && (
            <p className="text-xs text-ink/50">{tr(lang, "helperInviteNote")} {st.note}</p>
          )}

          <div className="text-sm text-ink/75 leading-relaxed flex flex-col gap-2">
            <p><b>{tr(lang, "helperGetLabel")}</b> {tr(lang, "helperGetBody")}</p>
            <p><b>{tr(lang, "helperStoredLabel")}</b> {tr(lang, "helperStoredBody")}</p>
            <p><b>{tr(lang, "helperNotLabel")}</b> {tr(lang, "helperNotBody")}</p>
          </div>

          <p className="text-[11px] text-ink/40">
            {tr(lang, "helperDetailsPre")}
            <Link href="/terms" className="text-tekhelet/70 hover:underline">
              {tr(lang, "helperDetailsTerms")}
            </Link>
            {tr(lang, "helperDetailsMid")}
            <Link href="/privacy" className="text-tekhelet/70 hover:underline">
              {tr(lang, "helperDetailsPrivacy")}
            </Link>.
          </p>

          <div className="flex gap-2">
            <button
              disabled={busy}
              onClick={() => answer(true)}
              className="px-4 py-2 rounded-2xl grad text-white font-semibold text-sm disabled:opacity-40"
            >
              {tr(lang, "helperAccept")}
            </button>
            <button
              disabled={busy}
              onClick={() => answer(false)}
              className="px-4 py-2 rounded-2xl glass text-ink/60 font-semibold text-sm disabled:opacity-40"
            >
              {tr(lang, "helperDecline")}
            </button>
          </div>
        </div>
      )}

      {/* Already helping. Two promises live here, both of which the panel used to make and not keep:
          Terms 11a says "you may stop at any time" — which had no control anywhere in the product
          once the invitation panel disappeared — and the privacy policy says the operator's note is
          shown to you, which held for the invitation screen and then stopped holding, even though
          the operator can edit that note afterwards. */}
      {st.status === "accepted" && (
        <div className="glass rounded-[24px] p-4 flex flex-col gap-2 ring-1 ring-tekhelet/15">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-sm text-ink/75">
              {tr(lang, "helperActiveLabel")}
              {st.plan ? ` — ${tr(lang, "helperActiveQuota")} ${st.plan}` : ""}.
            </span>
            <button
              onClick={() => {
                // Confirmed, because stopping is destructive on the operator's side too: it erases
                // their note about you and the notices they sent. Right for a refusal — a person who
                // is out should not have our description of them on file — but not something a
                // mis-click should do, which is what a bare button on an always-visible panel is.
                if (window.confirm(tr(lang, "helperStopConfirm"))) {
                  answer(false);
                }
              }}
              disabled={busy}
              className="px-3 py-1.5 rounded-full glass text-ink/60 text-xs font-semibold hover:bg-ink/5 disabled:opacity-40"
            >
              {tr(lang, "helperStop")}
            </button>
          </div>
          {st.note && (
            <p className="text-xs text-ink/50">
              {tr(lang, "helperNoteOnYou")} {st.note}
            </p>
          )}
          {!!st.features.length && (
            <p className="text-xs text-ink/50">
              {tr(lang, "helperOpenedForYou")} {st.features.join(" · ")}
            </p>
          )}
        </div>
      )}

      {(st.unread || []).map((m) => (
        <div
          key={m.id}
          role="status"
          className="glass rounded-[24px] p-4 flex items-start gap-3 ring-1 ring-gold/25"
        >
          <Icon name="campaign" className="text-gold text-[20px] mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink/80 whitespace-pre-line break-words">{m.body}</p>
            <p className="text-[11px] text-ink/40 mt-1">
              {new Date(m.at).toLocaleString(lang === "he" ? "he-IL" : "en-US")}
            </p>
          </div>
          <button
            onClick={() => dismiss(m.id)}
            aria-label={tr(lang, "helperMarkRead")}
            title={tr(lang, "helperMarkRead")}
            className="shrink-0 h-8 w-8 rounded-full glass grid place-items-center text-ink/50 hover:text-tekhelet"
          >
            <Icon name="close" className="text-[18px]" />
          </button>
        </div>
      ))}
    </>
  );
}
