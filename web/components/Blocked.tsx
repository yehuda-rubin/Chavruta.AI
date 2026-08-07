"use client";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { Icon } from "./Icon";

const CONTACT_EMAIL = "rubinyehuda8@gmail.com";

// Full-screen block notice — shown when the signed-in account is on the blocklist. The user can read
// why and until when, appeal by email, and sign out; every other action is 403'd server-side anyway.
export function Blocked({ lang, until, reason }: { lang: Lang; until: string | null; reason: string }) {
  const { signOut } = useAuth();
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString(lang === "he" ? "he-IL" : "en-US",
      { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return (
    <div className="min-h-dvh grid place-items-center p-4">
      <div className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-4 text-center">
        <div className="h-14 w-14 mx-auto rounded-2xl bg-red-500/10 ring-1 ring-red-500/20 grid place-items-center text-red-500">
          <Icon name="block" className="text-[26px]" />
        </div>
        <h1 className="font-serif text-2xl font-bold text-red-600">{tr(lang, "blockedTitle")}</h1>
        <p className="text-sm text-ink/70 leading-relaxed">
          {until ? `${tr(lang, "blockedUntilPrefix")} ${fmt(until)}.` : tr(lang, "blockedPermanent")}
        </p>
        {reason && (
          <p className="text-xs text-ink/55">
            {tr(lang, "blockedReasonPrefix")} {reason}
          </p>
        )}
        <p className="text-xs text-ink/55">
          {tr(lang, "blockedContact")}{" "}
          <a href={`mailto:${CONTACT_EMAIL}`} dir="ltr" className="text-indigo font-semibold hover:underline">
            {CONTACT_EMAIL}
          </a>
        </p>
        <button
          onClick={() => signOut()}
          className="mt-1 py-2.5 rounded-full glass text-ink/70 font-semibold text-sm hover:bg-white/60 transition"
        >
          {tr(lang, "signOut")}
        </button>
      </div>
    </div>
  );
}
