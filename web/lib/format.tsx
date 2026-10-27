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
  // ref_he before ref. `commentator_id` is empty on every point of the commercial corpus and is
  // derived from the ref at read time — but that derivation keys on "_on_", which the comma form
  // (Chizkuni,_Deuteronomy.10.6.1) does not have. Falling straight to `ref` is why a Hebrew answer
  // showed a chip reading "Chizkuni,_Deuteronomy.10.6.1" beside one reading "rashbam".
  return (c.commentator || c.ref_he || c.ref || "").trim();
}

function splitRow(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
  if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
  return trimmed.split("|").map((c) => c.trim());
}

function isDelimiterRow(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.includes("-") || !trimmed.includes("|")) return false;
  const cols = splitRow(trimmed);
  if (cols.length === 0) return false;
  return cols.every((c) => /^:?-+:?$/.test(c));
}

function parseAlignments(delimLine: string): ("center" | "left" | "right" | "start")[] {
  const cols = splitRow(delimLine);
  return cols.map((c) => {
    const left = c.startsWith(":");
    const right = c.endsWith(":");
    if (left && right) return "center";
    if (left) return "left";
    if (right) return "right";
    return "start";
  });
}

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const parts = (text || "").split(/\*\*(.+?)\*\*/g);
  parts.forEach((p, i) => {
    if (!p) return;
    out.push(
      i % 2 === 1 ? (
        <strong key={`${keyPrefix}-${i}`} className="font-bold text-ink">
          {p}
        </strong>
      ) : (
        <React.Fragment key={`${keyPrefix}-${i}`}>{p}</React.Fragment>
      )
    );
  });
  return out;
}

// Minimal, safe Markdown renderer for assistant text — handles tables, horizontal rules,
// **bold** inline formatting and newlines. Returns React nodes (no dangerouslySetInnerHTML).
export function renderText(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const lines = (text || "").split("\n");
  let i = 0;
  let blockIdx = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Markdown Table
    if (i + 1 < lines.length && line.includes("|") && isDelimiterRow(lines[i + 1])) {
      const headers = splitRow(line);
      const aligns = parseAlignments(lines[i + 1]);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitRow(lines[i]));
        i++;
      }

      const tableKey = `table-${blockIdx++}`;
      out.push(
        <div
          key={tableKey}
          className="my-4 overflow-hidden rounded-2xl border border-line bg-white/95 shadow-sm"
          style={{ whiteSpace: "normal" }}
        >
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-start text-[14px] sm:text-[15px] md:text-[16px]">
              <thead>
                <tr className="border-b border-line bg-tekhelet/5 text-tekhelet">
                  {headers.map((h, hi) => {
                    const align = aligns[hi] || "start";
                    const alignClass =
                      align === "center"
                        ? "text-center"
                        : align === "left"
                        ? "text-left"
                        : align === "right"
                        ? "text-right"
                        : "text-start";
                    return (
                      <th
                        key={hi}
                        className={`py-3 px-4 font-bold text-ink/90 border-e border-line/40 last:border-e-0 ${alignClass}`}
                      >
                        {renderInline(h, `${tableKey}-th-${hi}`)}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {rows.map((row, ri) => (
                  <tr key={ri} className="transition-colors hover:bg-cream-2/40 even:bg-cream/25">
                    {headers.map((_, ci) => {
                      const cell = row[ci] || "";
                      const align = aligns[ci] || "start";
                      const alignClass =
                        align === "center"
                          ? "text-center"
                          : align === "left"
                          ? "text-left"
                          : align === "right"
                          ? "text-right"
                          : "text-start";
                      return (
                        <td
                          key={ci}
                          className={`py-2.5 px-4 text-ink/85 align-top border-e border-line/40 last:border-e-0 ${alignClass}`}
                        >
                          {renderInline(cell, `${tableKey}-td-${ri}-${ci}`)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );
      continue;
    }

    // 2. Horizontal rule (---, ***, ___)
    if (/^(\s*[-*_]\s*){3,}$/.test(trimmed)) {
      out.push(<hr key={`hr-${blockIdx++}`} className="my-5 border-t border-line/80" />);
      i++;
      continue;
    }

    // 3. Regular text line
    const inlineNodes = renderInline(line, `line-${blockIdx++}`);
    inlineNodes.forEach((node) => out.push(node));
    if (i < lines.length - 1) {
      out.push(<br key={`br-${blockIdx++}`} />);
    }
    i++;
  }

  return out;
}
