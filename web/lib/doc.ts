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

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export function downloadDoc(filename: string, title: string, bodyText: string): void {
  // If PDF file (rich printable HTML payload)
  if (filename.toLowerCase().endsWith(".pdf")) {
    printHtmlContent(bodyText || "");
    return;
  }

  // If modern .docx file with base64 content
  if (filename.toLowerCase().endsWith(".docx")) {
    try {
      const cleanB64 = (bodyText || "").replace(/\s/g, "");
      const binaryStr = atob(cleanB64);
      const len = binaryStr.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }
      const blob = new Blob([bytes], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      triggerBlobDownload(blob, filename);
      return;
    } catch {
      // If not valid base64, fall through to text download
    }
  }

  // If printable HTML file
  if (filename.toLowerCase().endsWith(".html")) {
    const blob = new Blob([bodyText || ""], { type: "text/html;charset=utf-8" });
    triggerBlobDownload(blob, filename);
    return;
  }

  // If Markdown file
  if (filename.toLowerCase().endsWith(".md")) {
    const blob = new Blob([bodyText || ""], { type: "text/markdown;charset=utf-8" });
    triggerBlobDownload(blob, filename);
    return;
  }

  // Fallback / legacy Word-compatible HTML export (.doc)
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
  const blob = new Blob(["\ufeff", html], { type: "application/msword" });
  triggerBlobDownload(blob, filename);
}

export function printHtmlContent(htmlContent: string): void {
  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.right = "0";
  iframe.style.bottom = "0";
  iframe.style.width = "0";
  iframe.style.height = "0";
  iframe.style.border = "0";
  document.body.appendChild(iframe);

  const doc = iframe.contentWindow?.document;
  if (!doc) {
    const win = window.open("", "_blank");
    if (win) {
      win.document.open();
      win.document.write(htmlContent);
      win.document.close();
      win.focus();
      setTimeout(() => win.print(), 350);
    }
    return;
  }

  doc.open();
  doc.write(htmlContent);
  doc.close();

  setTimeout(() => {
    try {
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
    } finally {
      setTimeout(() => {
        if (document.body.contains(iframe)) {
          document.body.removeChild(iframe);
        }
      }, 3000);
    }
  }, 400);
}
