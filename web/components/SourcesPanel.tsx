"use client";
import { useEffect, useState } from "react";
import type { Attachment, Citation, Lang, Message } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { isHe } from "@/lib/format";
import { citeText, useCiteLabels } from "@/lib/labels";
import { fileKind } from "@/lib/files";
import { Icon } from "./Icon";

// Human-readable label for a raw licence string — mirrors app/api.py's _LICENSE_HE (that copy
// serves the lesson source sheet; this one serves the sources panel). Everything not in the map
// falls back to the licence's own identifier (CC-BY-SA, CC0…), which is what people search for.
const LICENSE_LABEL: Record<Lang, Record<string, string>> = {
  he: { "public domain": "נחלת הכלל", "public domain mark": "נחלת הכלל", cc0: "CC0 (ויתור על זכויות)" },
  en: { "public domain": "Public Domain", "public domain mark": "Public Domain", cc0: "CC0 (public domain dedication)" },
};
function licenseLabel(lic: string, lang: Lang): string {
  return LICENSE_LABEL[lang]?.[lic.trim().toLowerCase()] ?? lic;
}

// Attribution — the edition + licence a source's text came from. CC-BY / CC-BY-SA require it;
// every source shows it regardless, so a reader always knows what they may do with the text, not
// only the sources where a licence legally demands it (same reasoning as _license_table in
// app/api.py for lesson sheets — see rights.py::document_license_notice).
// Still renders nothing when NONE of edition/licence/link are populated (a source with no
// attribution data at all, e.g. before the licence backfill reaches it) — an "unknown licence"
// placeholder on every card before that data lands would read as a wall of warnings, not
// information; the underlying gap is tracked in docs/CORPUS_SOURCES_CANDIDATES.md §9.
function Attribution({ c, lang }: { c: Citation; lang: Lang }) {
  const lic = (c.license || "").trim();
  const ver = (c.version_title || "").trim();
  // Only ever render http(s) links — deep_link is server data, but a malformed/hostile value
  // (e.g. "javascript:...") must not become a clickable anchor.
  const rawLink = (c.deep_link || "").trim();
  const link = /^https?:\/\//i.test(rawLink) ? rawLink : "";
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
          {tr(lang, "srcLicense")}: {licenseLabel(lic, lang)}
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

export function SourcesPanel({
  lang,
  messages,
  userSources,
  srcDefaultOpen,
  onRemoveSource,
  onAddSource,
  onCollapse,
}: {
  lang: Lang;
  messages: Message[];
  userSources: Attachment[];
  srcDefaultOpen: boolean;
  onRemoveSource: (i: number) => void;
  onAddSource: () => void;
  onCollapse: () => void;
}) {
  // When "sources open by default", membership in `toggled` means "collapsed" (inverted).
  const [toggled, setToggled] = useState<Set<string>>(new Set());

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

  const labels = useCiteLabels(order);

  // Show the evidence, not just a list of titles: when a new source arrives, its card opens (the
  // panel only exists because there is something to read). Keyed on the newest ref so a re-render
  // doesn't undo a card the reader has since opened or closed.
  const newest = order[order.length - 1];
  useEffect(() => {
    if (!newest) return;
    setToggled((prev) => {
      const next = new Set(prev);
      if (srcDefaultOpen) next.delete(newest);
      else next.add(newest);
      return next;
    });
  }, [newest, srcDefaultOpen]);

  const toggle = (ref: string) =>
    setToggled((prev) => {
      const next = new Set(prev);
      next.has(ref) ? next.delete(ref) : next.add(ref);
      return next;
    });
  const isOpen = (ref: string) => (srcDefaultOpen ? !toggled.has(ref) : toggled.has(ref));

  return (
    <aside className="w-[22rem] shrink-0 glass rounded-[28px] flex flex-col overflow-hidden">
      <div className="flex items-center gap-2 p-4 pb-3">
        <button
          onClick={onCollapse}
          className="h-10 w-10 rounded-full grid place-items-center text-ink/45 hover:bg-cream-2 hover:text-indigo shrink-0 transition"
          title={tr(lang, "collapse")}
        >
          <Icon name={lang === "en" ? "chevron_right" : "chevron_left"} />
        </button>
        <h3 className="text-lg font-bold text-ink">{tr(lang, "relatedSources")}</h3>
      </div>
      <div className="flex-1 overflow-y-auto p-4 pt-0 flex flex-col gap-3">
        {/* The model's own source list used to render here and was removed on sight (2026-08-14):
            it repeated, in English, the very sources listed underneath it. It existed to get a
            work's NAME in front of a Hebrew reader — and the comma fix in
            corpus/refs.py::hebrew_display_ref did that properly instead, taking the panel's own
            Hebrew coverage from 66% to 98.5%. The server still carries `source_note` on the
            message; nothing displays it, and the prompt that asks for it is gated off. */}
        {order.length === 0 ? (
          <p className="text-ink/40 text-sm text-center mt-10">{tr(lang, "sourcesHint")}</p>
        ) : (
          // most-recent on top; ordinal 1 = first used
          order
            .map((ref, idx) => ({ c: byRef.get(ref)!, n: idx + 1 }))
            .reverse()
            .map(({ c, n }) => {
              const open = isOpen(c.ref);
              const full = lang === "en" ? c.text_en || c.text_he : c.text_he || c.text_en;
              const cite = citeText(c, lang, labels);
              return (
                <div
                  key={c.ref}
                  onClick={() => toggle(c.ref)}
                  className={
                    "block rounded-3xl p-4 border transition cursor-pointer " +
                    (open ? "bg-white border-indigo/40 shadow-lg shadow-indigo/10" : "bg-cream border-transparent hover:border-indigo/30")
                  }
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-gold flex items-center gap-2">
                        <span className="inline-grid place-items-center h-5 w-5 rounded-full bg-indigo text-white text-[11px] font-bold tabular-nums shrink-0">
                          {n}
                        </span>
                        {cite.who}
                      </p>
                      <h4 className="text-[17px] font-bold text-ink mt-1.5 leading-tight break-words">
                        {cite.title}
                      </h4>
                    </div>
                    <Icon name={open ? "expand_less" : "expand_more"} className="text-ink/40 shrink-0" />
                  </div>
                  {open && (
                    <div className="mt-3 pt-3 border-t border-line">
                      <p
                        className="text-[17px] text-ink/90 font-quote leading-[1.9] break-words"
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

      {/* User-added sources + the add button (sent with the next question). */}
      <div className="p-4 pt-3 border-t border-line flex flex-col gap-2">
        {userSources.map((s, i) => {
          const k = s.kind === "text" ? { icon: "notes", label: tr(lang, "kindText") } : fileKind(s.name, lang);
          return (
            <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/70 ring-1 ring-line/70 text-sm">
              <Icon name={k.icon} className="text-[18px] text-indigo shrink-0" />
              <span className="flex-1 truncate text-ink/75" title={s.name}>
                {s.name}
              </span>
              <span className="text-[10px] font-bold text-gold uppercase shrink-0">{k.label}</span>
              <button onClick={() => onRemoveSource(i)} className="text-ink/40 hover:text-red-500 shrink-0" title={tr(lang, "remove")}>
                <Icon name="close" className="text-[16px]" />
              </button>
            </div>
          );
        })}
        <button
          onClick={onAddSource}
          className="w-full min-h-11 rounded-full bg-cream-2 text-indigo font-semibold text-sm hover:bg-indigo hover:text-white transition-colors"
        >
          {tr(lang, "addSource")}
          {userSources.length ? ` (${userSources.length})` : ""}
        </button>
      </div>
    </aside>
  );
}
