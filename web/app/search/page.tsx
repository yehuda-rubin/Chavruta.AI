"use client";

import { useEffect } from "react";

// The old full-text search page was merged into the library (/library): book and source search on one
// side, content search on the other. Old links and bookmarks land here and are forwarded with their
// query intact. The API routes under /search/query and /reader/* are unchanged.
export default function SearchRedirect() {
  useEffect(() => {
    const src = new URLSearchParams(window.location.search);
    const out = new URLSearchParams();
    const q = src.get("q");
    if (q) {
      out.set("mode", "content");
      out.set("q", q);
      const w = src.get("work_id");
      if (w) out.set("work_id", w);
      const p = src.get("page");
      if (p) out.set("page", p);
    }
    const qs = out.toString();
    window.location.replace(qs ? `/library?${qs}` : "/library");
  }, []);
  return null;
}
