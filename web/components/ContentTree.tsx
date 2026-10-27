"use client";
import { useEffect, useMemo, useState } from "react";
import type { Lang } from "@/lib/types";
import type { ContentEntry, ContentNode, ContentSettings } from "@/lib/api";
import { tr } from "@/lib/i18n";

// Category/book toggles shared by the school page (PUT /orgs/content) and the family page
// (PUT /parent/children/{id}/content). Everything is on by default; unticking adds an entry to the
// caller's OWN disabled list. The server also reports nodes switched off by the OTHER side (a parent
// cannot lift a school's limit and vice versa); those show locked rather than as a tick the caller
// could not honour.

type Key = string;
const keyOf = (kind: string, id: string): Key => `${kind}:${id}`;

function kids(n: ContentNode): ContentNode[] {
  return [...(n.children ?? []), ...(n.books ?? [])];
}

export function ContentTree({
  lang, load, save, disabledAll,
}: {
  lang: Lang;
  load: () => Promise<ContentSettings>;
  save: (disabled: ContentEntry[]) => Promise<ContentSettings>;
  disabledAll?: boolean;       // read-only (demo school)
}) {
  const [settings, setSettings] = useState<ContentSettings | null>(null);
  const [off, setOff] = useState<Set<Key>>(new Set());          // the caller's own switched-off entries
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [failed, setFailed] = useState(false);

  const adopt = (s: ContentSettings) => {
    setSettings(s);
    setOff(new Set((s.disabled ?? []).map((e) => keyOf(e.kind, e.value))));
  };

  useEffect(() => {
    let alive = true;
    load().then((s) => { if (alive) adopt(s); }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Nodes the server says are off although none of the caller's own entries (on the node or above it)
  // explain it: someone else's limit.
  const external = useMemo(() => {
    const out = new Set<Key>();
    if (!settings) return out;
    const own = new Set((settings.disabled ?? []).map((e) => keyOf(e.kind, e.value)));
    const walk = (n: ContentNode, ownAbove: boolean) => {
      const ownHere = ownAbove || own.has(keyOf(n.kind, n.id));
      if (!n.enabled && !ownHere) out.add(keyOf(n.kind, n.id));
      kids(n).forEach((c) => walk(c, ownHere));
    };
    settings.categories.forEach((n) => walk(n, false));
    return out;
  }, [settings]);

  const toggle = (n: ContentNode) => {
    const k = keyOf(n.kind, n.id);
    setMsg("");
    setOff((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  };

  const onSave = async () => {
    setBusy(true);
    setMsg("");
    setFailed(false);
    try {
      const entries: ContentEntry[] = [...off].map((k) => {
        const i = k.indexOf(":");
        return { kind: k.slice(0, i) as ContentEntry["kind"], value: k.slice(i + 1) };
      });
      adopt(await save(entries));
      setMsg(tr(lang, "contentTreeSaved"));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  const renderNode = (n: ContentNode, ownAbove: boolean, depth: number): React.ReactNode => {
    const k = keyOf(n.kind, n.id);
    const ownHere = ownAbove || off.has(k);
    const locked = external.has(k) || (disabledAll ?? false);
    const label = (lang === "he" ? n.label_he : n.label_en) || n.label_he || n.label_en || n.id;
    const children = kids(n);
    const isOpen = open.has(k);
    return (
      <li key={k}>
        <div className="flex items-center gap-2 py-1" style={{ paddingInlineStart: depth * 16 }}>
          {children.length > 0 ? (
            <button
              type="button"
              aria-expanded={isOpen}
              aria-label={`${tr(lang, isOpen ? "contentTreeCollapse" : "contentTreeExpand")}: ${label}`}
              onClick={() => setOpen((p) => { const x = new Set(p); if (x.has(k)) x.delete(k); else x.add(k); return x; })}
              className="h-6 w-6 shrink-0 rounded-full glass text-ink/60 text-xs rtl:rotate-180"
            >
              {isOpen ? "▾" : "▸"}
            </button>
          ) : <span className="w-6 shrink-0" />}
          <label className="flex items-center gap-2 text-sm cursor-pointer min-w-0">
            <input
              type="checkbox"
              checked={!ownHere && !external.has(k)}
              disabled={locked || (ownAbove && !off.has(k))}
              onChange={() => toggle(n)}
              className="accent-tekhelet"
            />
            <span className="truncate">{label}</span>
            {external.has(k) && <span className="text-[10px] text-ink/45">{tr(lang, "contentTreeExternal")}</span>}
          </label>
        </div>
        {children.length > 0 && isOpen && (
          <ul>{children.map((c) => renderNode(c, ownHere, depth + 1))}</ul>
        )}
      </li>
    );
  };

  if (failed && !settings) return <p role="alert" className="text-xs text-red-600">{tr(lang, "contentTreeFailed")}</p>;
  if (!settings) return <p className="text-xs text-ink/50">{tr(lang, "contentTreeLoading")}</p>;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px] text-ink/50 leading-relaxed">{tr(lang, "contentTreeHint")}</p>
      <ul className="max-h-80 overflow-y-auto pe-1">{settings.categories.map((n) => renderNode(n, false, 0))}</ul>
      <div className="flex items-center gap-3">
        <button onClick={onSave} disabled={busy || disabledAll}
                className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40">
          {tr(lang, "contentTreeSave")}
        </button>
        <span role="status" className="text-xs text-ink/60">{msg}</span>
        {failed && <span role="alert" className="text-xs text-red-600">{tr(lang, "contentTreeFailed")}</span>}
      </div>
    </div>
  );
}
