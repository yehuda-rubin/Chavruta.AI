"use client";
import { useEffect, useState } from "react";
import type { Lang, SavedLesson } from "@/lib/types";
import { api } from "@/lib/api";
import { tr } from "@/lib/i18n";
import { Modal } from "./Modal";
import { Icon } from "./Icon";

// My Shiurim — the saved lessons (GET /lessons). Open loads it into the chat; delete removes it.
export function LessonsModal({
  open,
  lang,
  onClose,
  onOpenLesson,
}: {
  open: boolean;
  lang: Lang;
  onClose: () => void;
  onOpenLesson: (l: SavedLesson) => void;
}) {
  const [lessons, setLessons] = useState<SavedLesson[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLessons(null);
    setError(null);
    api.listLessons().then(setLessons).catch((e) => setError(String(e)));
  }, [open]);

  const del = async (id: string) => {
    try {
      await api.deleteLesson(id);
    } catch {
      /* ignore */
    }
    setLessons((prev) => (prev || []).filter((l) => l.id !== id));
  };

  const meta = (l: SavedLesson) => {
    const aud = l.audience === "school" ? `${tr(lang, "audSchool")} ${l.grade_band || ""}` : l.audience === "yeshiva" ? tr(lang, "audYeshiva") : "";
    return [aud.trim(), l.length, (l.created_at || "").slice(0, 10)].filter(Boolean).join(" · ");
  };

  return (
    <Modal open={open} title={tr(lang, "myShiurim")} onClose={onClose} maxW="max-w-lg">
      <div className="flex-1 overflow-y-auto flex flex-col gap-2 min-h-[120px]">
        {error ? (
          <p className="text-red-500 text-sm p-4">{error}</p>
        ) : lessons === null ? (
          <p className="text-ink/40 text-sm p-4">…</p>
        ) : lessons.length === 0 ? (
          <p className="text-ink/50 text-sm p-8 text-center">{tr(lang, "libEmpty")}</p>
        ) : (
          lessons.map((l) => (
            <div key={l.id} className="flex items-center gap-3 bg-white/70 hover:bg-white/95 ring-1 ring-line/70 rounded-2xl p-3.5 transition">
              <button onClick={() => onOpenLesson(l)} className="flex-1 min-w-0 text-start">
                <span className="block font-serif font-bold text-tekhelet truncate">{l.topic}</span>
                <span className="block text-[11px] text-ink/50">{meta(l)}</span>
              </button>
              <button
                onClick={() => del(l.id)}
                className="h-8 w-8 rounded-lg hover:bg-white grid place-items-center text-ink/40 hover:text-red-500 shrink-0"
                title={tr(lang, "remove")}
              >
                <Icon name="delete" className="text-[20px]" />
              </button>
            </div>
          ))
        )}
      </div>
    </Modal>
  );
}
