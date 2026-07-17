"use client";
import { useState } from "react";
import type { Citation, Lang, Message } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { commentatorTag, isHe } from "@/lib/format";
import { Icon } from "./Icon";

// Attribution — the edition + licence a source's text came from. CC-BY / CC-BY-SA require it.
// Renders nothing until the fields are populated (they arrive with the licence backfill).
function Attribution({ c, lang }: { c: Citation; lang: Lang }) {
  const lic = (c.license || "").trim();
  const ver = (c.version_title || "").trim();
  const link = (c.deep_link || "").trim();
  if (!lic && !ver && !link) return null;
  return (
    <div className="mt-2 pt-2 border-t border-line/40 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink/45">
      {ver && (
        <span>
          {tr(lang, "srcEdition")}: {ver}
        </span>
      )}
      {lic && (
        <span>
          {tr(lang, "srcLicense")}: {lic}
        </span>
      )}
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-tekhelet/70 hover:text-tekhelet inline-flex items-center gap-0.5"
        >
          {tr(lang, "viewOnSefaria")}
          <Icon name="open_in_new" className="text-[13px]" />
        </a>
      )}
    </div>
  );
}

export function SourcesPanel({ lang, messages }: { lang: Lang; messages: Message[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Dedupe across the whole conversation by ref, earliest-first (matches the static UI).
  const order: string[] = [];
  const byRef = new Map<string, Citation>();
  for (const m of messages) {
    if (m.role !== "assistant") continue;
    for (const c of m.citations || []) {
      if (!c || !c.ref) continue;
      if (!((c.text_he || "").trim() || (c.text_en || "").trim())) continue;
      if (!byRef.has(c.ref)) {
        byRef.set(c.ref, c);
        order.push(c.ref);
      }
    }
  }

  const toggle = (ref: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(ref) ? next.delete(ref) : next.add(ref);
      return next;
    });

  return (
    <aside className="w-80 shrink-0 glass rounded-[28px] flex flex-col overflow-hidden">
      <div className="flex items-center gap-2 p-4 pb-3">
        <h3 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "relatedSources")}</h3>
      </div>
      <div className="flex-1 overflow-y-auto p-4 pt-0 flex flex-col gap-3">
        {order.length === 0 ? (
          <p className="text-ink/40 text-sm text-center mt-10">{tr(lang, "sourcesHint")}</p>
        ) : (
          // most-recent on top; ordinal 1 = first used
          order
            .map((ref, idx) => ({ c: byRef.get(ref)!, n: idx + 1 }))
            .reverse()
            .map(({ c, n }) => {
              const open = expanded.has(c.ref);
              const full = lang === "en" ? c.text_en || c.text_he : c.text_he || c.text_en;
              return (
                <div
                  key={c.ref}
                  onClick={() => toggle(c.ref)}
                  className={
                    "block rounded-2xl p-4 shadow-sm transition cursor-pointer " +
                    (open ? "bg-white/85 ring-2 ring-gold/40" : "bg-white/60 hover:ring-2 hover:ring-gold/30")
                  }
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[10px] font-black tracking-widest text-gold uppercase flex items-center gap-1.5">
                        <span className="inline-grid place-items-center h-4 w-4 rounded-full bg-gold/15 text-gold text-[9px] shrink-0">
                          {n}
                        </span>
                        {commentatorTag(c)}
                      </p>
                      <h4 className="font-serif text-lg font-bold text-tekhelet mt-1 leading-tight break-words">
                        {c.ref}
                      </h4>
                    </div>
                    <Icon name={open ? "expand_less" : "expand_more"} className="text-ink/40 shrink-0" />
                  </div>
                  {open && (
                    <div className="mt-3 pt-3 border-t border-line/60">
                      <p
                        className="text-[15px] text-ink/85 font-serif leading-relaxed break-words"
                        style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                        dir={isHe(full || "") ? "rtl" : "ltr"}
                      >
                        {full || tr(lang, "noText")}
                      </p>
                      <Attribution c={c} lang={lang} />
                    </div>
                  )}
                </div>
              );
            })
        )}
      </div>
    </aside>
  );
}
