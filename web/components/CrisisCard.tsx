"use client";
import type { CrisisContact, CrisisPayload, Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { Icon } from "./Icon";

// The fixed support reply that replaces a model answer when a minor's message is screened (spec 009).
// The text comes from the server verbatim (written by a human, never generated); nothing here edits it.
// One tap per channel. The police contact is flagged only_if_danger and is shown only when the payload
// says immediate_danger.

/** wa.me wants digits with the country code: an Israeli "052-845-1201" becomes 972528451201. */
function waLink(raw: string): string {
  let d = raw.replace(/\D/g, "");
  if (d.startsWith("0")) d = "972" + d.slice(1);
  return `https://wa.me/${d}`;
}

function isHttp(u?: string): u is string {
  return !!u && /^https:\/\//i.test(u);
}

const btn =
  "inline-flex items-center justify-center gap-1.5 min-h-11 px-4 rounded-full text-sm font-semibold transition";

function ContactRow({ lang, c }: { lang: Lang; c: CrisisContact }) {
  const label = (lang === "he" ? c.label_he : c.label_en) || c.label || c.id;
  const tel = (c.tel || "").replace(/[^\d+]/g, "");
  return (
    <li className="flex flex-col gap-2 rounded-2xl bg-white/70 border border-line p-3">
      <span className="font-bold text-ink">{label}</span>
      <div className="flex flex-wrap gap-2">
        {tel && (
          <a href={`tel:${tel}`} className={`${btn} grad text-white`}>
            <Icon name="call" className="text-[18px]" />
            <span>{tr(lang, "crisisCall")} <bdi dir="ltr">{c.tel}</bdi></span>
          </a>
        )}
        {c.whatsapp && (
          <a href={waLink(c.whatsapp)} target="_blank" rel="noopener noreferrer"
             className={`${btn} bg-emerald-600 text-white hover:bg-emerald-700`}>
            <Icon name="chat" className="text-[18px]" />
            <span>{tr(lang, "crisisWhatsapp")}</span>
          </a>
        )}
        {isHttp(c.chat_url) && (
          <a href={c.chat_url} target="_blank" rel="noopener noreferrer"
             className={`${btn} bg-white border border-line text-indigo hover:bg-cream-2`}>
            <Icon name="forum" className="text-[18px]" />
            <span>{tr(lang, "crisisChat")}</span>
          </a>
        )}
        {isHttp(c.site) && (
          <a href={c.site} target="_blank" rel="noopener noreferrer"
             className={`${btn} bg-white border border-line text-indigo hover:bg-cream-2`}>
            <Icon name="open_in_new" className="text-[18px]" />
            <span>{tr(lang, "crisisSite")}</span>
          </a>
        )}
      </div>
    </li>
  );
}

export function CrisisCard({ lang, crisis }: { lang: Lang; crisis: CrisisPayload }) {
  const text = (lang === "he" ? crisis.message_he : crisis.message_en) || crisis.message || "";
  const contacts = (crisis.contacts || []).filter((c) => !c.only_if_danger || crisis.immediate_danger);
  return (
    <section
      role="region"
      aria-label={tr(lang, "crisisCardLabel")}
      dir={lang === "he" ? "rtl" : "ltr"}
      className="min-w-0 flex-1 rounded-3xl border border-gold/40 bg-gold/10 p-5 flex flex-col gap-4"
    >
      <p className="text-[18px] leading-[1.9] text-ink/90" style={{ whiteSpace: "pre-wrap" }}>{text}</p>
      {contacts.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-bold text-tekhelet">{tr(lang, "crisisHelpHeading")}</h3>
          <ul className="flex flex-col gap-2">
            {contacts.map((c) => <ContactRow key={c.id} lang={lang} c={c} />)}
          </ul>
        </div>
      )}
    </section>
  );
}
