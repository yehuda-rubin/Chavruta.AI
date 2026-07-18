"use client";
import { useEffect } from "react";
import { Icon } from "./Icon";

// Shared modal shell — backdrop (click-to-close) + glass card, matching the static UI modals.
export function Modal({
  open,
  title,
  onClose,
  children,
  maxW = "max-w-md",
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  maxW?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className={`glass rounded-[28px] p-6 w-full ${maxW} flex flex-col gap-4 max-h-[85vh]`}>
        <div className="flex items-center justify-between">
          <h3 className="font-serif text-xl font-bold text-tekhelet">{title}</h3>
          <button
            onClick={onClose}
            className="h-8 w-8 rounded-full glass grid place-items-center text-ink/60 hover:text-tekhelet"
          >
            <Icon name="close" className="text-[18px]" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
