"use client";
import { useRef, useState } from "react";
import type { Attachment, Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { fileToDataURL } from "@/lib/files";
import { Modal } from "./Modal";
import { Icon } from "./Icon";

// Paste source text or upload files (image / PDF / Word) → user sources, sent with the next query.
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
  const fileRef = useRef<HTMLInputElement>(null);

  const save = async () => {
    const items: Attachment[] = [];
    if (text.trim()) {
      items.push({ kind: "text", name: text.trim().slice(0, 40) + (text.length > 40 ? "…" : ""), content: text.trim() });
    }
    for (const f of Array.from(fileRef.current?.files || [])) {
      items.push({ kind: "file", name: f.name, content: await fileToDataURL(f), mime: f.type });
    }
    if (items.length) onAdd(items);
    setText("");
    if (fileRef.current) fileRef.current.value = "";
    onClose();
  };

  return (
    <Modal open={open} title={tr(lang, "addSrcTitle")} onClose={onClose}>
      <p className="text-xs text-ink/55 leading-relaxed">{tr(lang, "addSrcDesc")}</p>
      <textarea
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="w-full glass rounded-2xl p-3 font-serif text-[15px] outline-none focus:ring-2 focus:ring-indigo/30 resize-none"
        placeholder={tr(lang, "addSrcPlaceholder")}
      />
      <button
        onClick={() => fileRef.current?.click()}
        className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl glass text-ink/70 font-semibold text-sm hover:bg-white/60 transition"
      >
        <Icon name="upload_file" className="text-[19px]" />
        {tr(lang, "uploadFile")}
      </button>
      {/* Images are intentionally excluded for now — OCR (image → Hebrew text) is a separate,
          owner-approved step. Re-add "image/*" here and drop the backend note to enable it. */}
      <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.txt" className="hidden" multiple />
      <div className="flex gap-2">
        <button onClick={save} className="flex-1 py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition">
          {tr(lang, "add")}
        </button>
        <button onClick={onClose} className="px-5 py-3 rounded-full glass text-ink/70 font-semibold text-sm hover:bg-white/60 transition">
          {tr(lang, "cancel")}
        </button>
      </div>
    </Modal>
  );
}
