// Client-side .doc export — ported from the static UI's downloadDoc. Builds a Word-openable HTML
// blob (RTL, Frank Ruhl Libre) so a lesson's files download without a server round-trip.
function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string,
  );
}
function fmt(line: string): string {
  return esc(line).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

export function downloadDoc(filename: string, title: string, bodyText: string): void {
  const paras = String(bodyText || "")
    .split("\n")
    .map((line) => (line.trim() ? `<p>${fmt(line)}</p>` : "<p>&nbsp;</p>"))
    .join("");
  const html =
    '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" ' +
    'xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="utf-8"><title>' +
    esc(title) +
    "</title></head>" +
    "<body dir=\"rtl\" style=\"font-family:'Frank Ruhl Libre','David',serif;font-size:13pt;line-height:1.7;color:#1c1a17;\">" +
    `<h1 style="color:#002045;font-size:20pt">${esc(title)}</h1>${paras}</body></html>`;
  const blob = new Blob(["﻿", html], { type: "application/msword" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
