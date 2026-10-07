"use client";
import { useRef, useState } from "react";
import type { Attachment, Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { fileKind, fileToDataURL } from "@/lib/files";
import { Modal } from "./Modal";
import { Icon } from "./Icon";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Paste source text or upload files (PDF / Word / TXT) → user sources, sent with the next query.
export function AddSourceModal({
  open,
  lang,
  onClose,
  onAdd,
}: {
  open: boolean;
  lang: Lang;
  onClose: () => void;
  onAdd: (items: Attachment[]) => void;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFilesChosen = (newFiles: FileList | File[] | null) => {
    if (!newFiles) return;
    const list = Array.from(newFiles);
    setFiles((prev) => [...prev, ...list]);
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleClose = () => {
    setText("");
    setFiles([]);
    if (fileRef.current) fileRef.current.value = "";
    onClose();
  };

  const save = async () => {
    const items: Attachment[] = [];
    if (text.trim()) {
      items.push({
        kind: "text",
        name: text.trim().slice(0, 40) + (text.length > 40 ? "…" : ""),
        content: text.trim(),
      });
    }
    for (const f of files) {
      items.push({
        kind: "file",
        name: f.name,
        content: await fileToDataURL(f),
        mime: f.type,
      });
    }
    if (items.length) onAdd(items);
    handleClose();
  };

  const hasContent = Boolean(text.trim() || files.length > 0);
  const totalCount = (text.trim() ? 1 : 0) + files.length;

  return (
    <Modal open={open} title={tr(lang, "addSrcTitle")} onClose={handleClose}>
      <p className="text-xs text-ink/60 leading-relaxed">{tr(lang, "addSrcDesc")}</p>

      {/* Text paste area */}
      <div className="flex flex-col gap-1.5">
        <textarea
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-full glass rounded-2xl p-3 font-serif text-[15px] outline-none focus:ring-2 focus:ring-indigo/40 resize-none placeholder:text-ink/35"
          placeholder={tr(lang, "addSrcPlaceholder")}
        />
        {text.trim() && (
          <span className="text-[11px] text-indigo font-medium self-end px-1">
            {text.trim().length} {lang === "he" ? "תווים הוזנו" : "characters entered"}
          </span>
        )}
      </div>

      {/* Uploaded files card list (visible immediately inside the modal when selected) */}
      {files.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold text-ink/70">
            {lang === "he" ? `קבצים שנבחרו (${files.length}):` : `Selected files (${files.length}):`}
          </span>
          <div className="flex flex-col gap-2 max-h-48 overflow-y-auto pr-1">
            {files.map((f, i) => {
              const k = fileKind(f.name, lang);
              return (
                <div
                  key={i}
                  className="flex items-center gap-2.5 p-2.5 rounded-xl bg-emerald-50/80 border border-emerald-200/80 text-sm shadow-xs transition"
                >
                  <div className="w-8 h-8 rounded-lg bg-white flex items-center justify-center text-emerald-700 shadow-xs shrink-0">
                    <Icon name={k.icon} className="text-[20px]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-ink truncate text-xs" title={f.name}>
                      {f.name}
                    </p>
                    <div className="flex items-center gap-2 text-[10px] text-ink/50">
                      <span>{k.label}</span>
                      <span>•</span>
                      <span>{formatBytes(f.size)}</span>
                      <span className="text-emerald-600 font-medium">✓ {lang === "he" ? "מוכן להוספה" : "Ready"}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeFile(i)}
                    className="p-1 text-ink/40 hover:text-red-500 rounded-md hover:bg-white/80 transition shrink-0"
                    title={tr(lang, "remove")}
                  >
                    <Icon name="close" className="text-[16px]" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Drop zone / Upload trigger button */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFilesChosen(e.dataTransfer.files);
        }}
        onClick={() => fileRef.current?.click()}
        className={`w-full flex items-center justify-center gap-2 py-3.5 px-4 rounded-2xl cursor-pointer transition border-2 border-dashed ${
          isDragging
            ? "border-indigo bg-indigo/10 text-indigo"
            : files.length > 0
              ? "border-line/80 glass hover:bg-white/70 text-ink/75"
              : "border-line/70 glass hover:bg-white/70 text-ink/70"
        }`}
      >
        <Icon name={files.length > 0 ? "add_circle_outline" : "upload_file"} className="text-[20px] text-indigo" />
        <span className="font-semibold text-sm">
          {files.length > 0
            ? (lang === "he" ? "העלה קובץ נוסף · Word או PDF" : "Add another file · Word or PDF")
            : tr(lang, "uploadFile")}
        </span>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.doc,.docx,.txt"
        className="hidden"
        multiple
        onChange={(e) => {
          handleFilesChosen(e.target.files);
          e.target.value = "";
        }}
      />

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={save}
          disabled={!hasContent}
          className={`flex-1 py-3 rounded-full font-bold text-sm transition shadow-md ${
            hasContent
              ? "grad text-white hover:opacity-95 shadow-tekhelet/20 cursor-pointer"
              : "bg-ink/15 text-ink/40 cursor-not-allowed shadow-none"
          }`}
        >
          {totalCount > 1
            ? (lang === "he" ? `הוסף ${totalCount} מקורות` : `Add ${totalCount} sources`)
            : totalCount === 1
              ? (lang === "he" ? "הוסף מקור" : "Add source")
              : tr(lang, "add")}
        </button>
        <button
          onClick={handleClose}
          className="px-5 py-3 rounded-full glass text-ink/70 font-semibold text-sm hover:bg-white/60 transition cursor-pointer"
        >
          {tr(lang, "cancel")}
        </button>
      </div>
    </Modal>
  );
}
