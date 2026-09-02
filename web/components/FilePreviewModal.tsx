"use client";
import { useEffect } from "react";
import type { FileOut, Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { renderText } from "@/lib/format";
import { downloadDoc, printHtmlContent } from "@/lib/doc";
import { Icon } from "./Icon";

// Preview a lesson/sourcesheet file's content before downloading — with rich HTML/PDF and docx support.
export function FilePreviewModal({ file, lang, onClose }: { file: FileOut | null; lang: Lang; onClose: () => void }) {
  useEffect(() => {
    if (!file) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [file, onClose]);

  if (!file) return null;

  const isHtml = file.name.toLowerCase().endsWith(".html");
  const isDocx = file.name.toLowerCase().endsWith(".docx");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className={`glass rounded-[28px] w-full ${isHtml ? "max-w-4xl" : "max-w-2xl"} max-h-[90vh] flex flex-col overflow-hidden`}>
        <div className="flex items-center justify-between gap-3 p-5 pb-3">
          <div className="min-w-0">
            <h3 className="font-serif text-xl font-bold text-tekhelet truncate">{file.title || file.name}</h3>
            {file.title && <p className="text-[12px] text-ink/50 truncate">{file.name}</p>}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {isHtml ? (
              <>
                <button
                  onClick={() => printHtmlContent(file.content || "")}
                  className="px-4 py-2 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition flex items-center gap-1.5 shadow-sm"
                  title={tr(lang, "printPdf")}
                >
                  <Icon name="print" className="text-[18px]" />
                  {tr(lang, "printPdf")}
                </button>
                <button
                  onClick={() => downloadDoc(file.name, file.title || file.name, file.content || "")}
                  className="px-3.5 py-2 rounded-full glass hover:bg-white/80 font-bold text-sm text-tekhelet transition flex items-center gap-1"
                  title={tr(lang, "download")}
                >
                  <Icon name="download" className="text-[18px]" />
                  {tr(lang, "download")}
                </button>
              </>
            ) : (
              <button
                onClick={() => downloadDoc(file.name, file.title || file.name.replace(/\.docx?$/, ""), file.content || "")}
                className="px-4 py-2 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition flex items-center gap-1 shadow-sm"
              >
                <Icon name="download" className="text-[18px]" />
                {isDocx ? tr(lang, "downloadWord") : tr(lang, "download")}
              </button>
            )}
            <button onClick={onClose} className="h-9 w-9 rounded-full glass grid place-items-center text-ink/60 hover:text-tekhelet">
              <Icon name="close" className="text-[18px]" />
            </button>
          </div>
        </div>

        {isHtml ? (
          <div className="flex-1 p-4 bg-white/70 overflow-hidden">
            <iframe
              srcDoc={file.content || ""}
              title={file.title || file.name}
              className="w-full h-[72vh] border border-line/60 rounded-2xl bg-white shadow-inner"
              sandbox="allow-same-origin allow-scripts allow-modals"
            />
          </div>
        ) : isDocx ? (
          <div className="p-10 flex flex-col items-center text-center bg-white/40 font-serif leading-relaxed" dir="rtl">
            <div className="h-16 w-16 rounded-2xl grad grid place-items-center text-white mb-4 shadow-md">
              <Icon name="description" className="text-[32px]" />
            </div>
            <h4 className="text-xl font-bold text-tekhelet mb-2">{file.title || file.name}</h4>
            <p className="max-w-md text-[15px] text-ink/70 mb-6">
              קובץ Microsoft Word (.docx) אמיתי ומעוצב ברמה גבוהה. כולל כיוון ימין-שמאל (RTL), גופנים תורניים (Frank Ruhl / David), טבלאות מעוצבות ותאימות מלאה להדפסה ולעריכה.
            </p>
            <button
              onClick={() => downloadDoc(file.name, file.title || file.name, file.content || "")}
              className="px-6 py-3 rounded-full grad text-white font-bold text-base hover:opacity-95 transition flex items-center gap-2 shadow-lg"
            >
              <Icon name="download" className="text-[20px]" />
              {tr(lang, "downloadWord")}
            </button>
          </div>
        ) : (
          <div
            className="p-7 overflow-y-auto bg-white/40 font-serif text-[16px] leading-relaxed text-ink/85"
            dir="rtl"
            style={{ whiteSpace: "pre-wrap" }}
          >
            {file.content ? renderText(file.content) : tr(lang, "noContent")}
          </div>
        )}
      </div>
    </div>
  );
}
