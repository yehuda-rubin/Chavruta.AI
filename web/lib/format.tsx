import React from "react";
import type { Citation } from "./types";

// Hebrew if the first letter that carries direction is in the Hebrew block (matches the static UI).
export function isHe(text: string): boolean {
  for (const ch of text || "") {
    if (ch >= "֐" && ch <= "׿") return true;
    if ((ch >= "a" && ch <= "z") || (ch >= "A" && ch <= "Z")) return false;
  }
  return true; // default Hebrew-first
}

export function commentatorTag(c: Citation): string {
  return (c.commentator || c.ref || "").trim();
}

// Minimal, safe **bold** + newline renderer — no dangerouslySetInnerHTML. Returns React nodes so
// the framework escapes everything for us.
export function renderText(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const lines = (text || "").split("\n");
  lines.forEach((line, li) => {
    const parts = line.split(/\*\*(.+?)\*\*/g);
    parts.forEach((p, i) => {
      if (!p) return;
      out.push(i % 2 === 1 ? <strong key={`${li}-${i}`}>{p}</strong> : <React.Fragment key={`${li}-${i}`}>{p}</React.Fragment>);
    });
    if (li < lines.length - 1) out.push(<br key={`br-${li}`} />);
  });
  return out;
}
