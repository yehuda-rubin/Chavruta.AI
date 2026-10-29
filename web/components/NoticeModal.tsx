"use client";
import { useEffect, useState } from "react";
import { api, type UserNotice } from "@/lib/api";
import { Modal } from "./Modal";
import { Icon } from "./Icon";
import type { Lang } from "@/lib/types";

export function NoticeModal({ lang }: { lang: Lang }) {
  const [notices, setNotices] = useState<UserNotice[]>([]);
  const [active, setActive] = useState<UserNotice | null>(null);

  useEffect(() => {
    api.userNotices
      .list()
      .then((res) => {
        const items = res?.notices || [];
        setNotices(items);
        if (items.length > 0) {
          setActive(items[0]);
        }
      })
      .catch(() => {
        // Not signed in or backend unavailable — safe to ignore
      });
  }, []);

  if (!active) return null;

  const dismiss = async () => {
    const current = active;
    const nextList = notices.filter((n) => n.id !== current.id);
    setNotices(nextList);
    setActive(nextList.length > 0 ? nextList[0] : null);
    try {
      await api.userNotices.markRead(current.id);
    } catch {
      // optimistic dismissal is preserved
    }
  };

  const defaultTitle = lang === "he" ? "הודעה מצוות חברותא" : "Message from Chavruta";

  return (
    <Modal
      open={true}
      title={active.title || defaultTitle}
      onClose={dismiss}
      maxW="max-w-md"
    >
      <div className="flex flex-col gap-4 text-ink/80">
        <div className="flex items-start gap-3.5 p-4 rounded-2xl bg-tekhelet/5 border border-tekhelet/15">
          <Icon name="campaign" className="text-gold text-[26px] mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink/85 whitespace-pre-line leading-relaxed font-sans">
              {active.body}
            </p>
            <p className="text-[11px] text-ink/40 mt-3 font-mono">
              {new Date(active.created_at).toLocaleDateString(lang === "he" ? "he-IL" : "en-US", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </p>
          </div>
        </div>
        <div className="flex justify-end pt-1">
          <button
            onClick={dismiss}
            className="px-5 py-2 rounded-2xl grad text-white font-semibold text-sm hover:opacity-90 shadow-sm transition-opacity"
          >
            {lang === "he" ? "הבנתי, תודה!" : "Got it, thanks!"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
