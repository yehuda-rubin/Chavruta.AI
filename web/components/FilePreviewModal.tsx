"use client";
import { useEffect } from "react";
import type { FileOut, Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { renderText } from "@/lib/format";
import { downloadDoc } from "@/lib/doc";
import { Icon } from "./Icon";

// Preview a lesson file's content before downloading — ported from the static UI's openFilePreview.
export function FilePreviewModal({ file, lang, onClose }: { file: FileOut | null; lang: Lang; onClose: () => void }) {
  useEffect(() => {
    if (!file) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [file, onClose]);

  if (!file) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="glass rounded-[28px] w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between gap-3 p-5 pb-3">
          <h3 className="font-serif text-xl font-bold text-tekhelet truncate">{file.title || file.name}</h3>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => downloadDoc(file.name, file.title || file.name.replace(/\.docx?$/, ""), file.content || "")}
              className="px-4 py-2 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition flex items-center gap-1"
            >
              <Icon name="download" className="text-[18px]" />
              {tr(lang, "downloadWord")}
            </button>
            <button onClick={onClose} className="h-9 w-9 rounded-full glass grid place-items-center text-ink/60 hover:text-tekhelet">
              <Icon name="close" className="text-[18px]" />
            </button>
          </div>
        </div>
        <div
          className="p-7 overflow-y-auto bg-white/40 font-serif text-[16px] leading-relaxed text-ink/85"
          dir="rtl"
          style={{ whiteSpace: "pre-wrap" }}
        >
          {file.content ? renderText(file.content) : tr(lang, "noContent")}
        </div>
      </div>
    </div>
  );
}
