#!/usr/bin/env python3
"""Build the library catalogue: every commercially-licensed work in the corpus, with a Hebrew title
and its category path in Hebrew and English.

Output: src/chavruta/corpus/data/catalog.json (package data — ships with the code), shape
    {"categories": {"<en path>": {"en", "he", "order"}},
     "books": [{"title_en", "title_he", "path", "segments", "first_ref", "license"}]}

Works come from data/ref_index.db, which can be a superset of the live collection; licensing is
fail-closed (rights.allows_commercial_use on licenses.json), so a work with no recorded licence is
left out rather than listed. Run scripts/inventory_works.py first to see coverage.

Usage:  .venv/Scripts/python.exe scripts/build_catalog.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chavruta.corpus import rights  # noqa: E402
from inventory_works import DATA, collect_works  # noqa: E402


def main() -> None:
    cat_titles = json.loads((DATA / "category_titles.json").read_text(encoding="utf-8"))
    works = collect_works()

    books, dropped_lic, dropped_other = [], [], []
    for w in works:
        if not w["he"] or not w["first_ref"] or not w["path"]:
            dropped_other.append(w)
        elif not rights.allows_commercial_use(w["he_license"]):
            dropped_lic.append(w)
        else:
            books.append({"title_en": w["title"], "title_he": w["he"], "path": w["path"],
                          "segments": w["segments"], "first_ref": w["first_ref"],
                          "license": w["he_license"]})

    used: set[str] = set()
    for b in books:
        parts = b["path"].split("/")
        used.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    # Sefaria's TOC order is the canonical one; dict order of category_titles.json is sorted, so
    # ordering is by the TOC position recorded below only when present, else alphabetical.
    categories = {p: {**cat_titles[p]} for p in sorted(used) if p in cat_titles}
    books.sort(key=lambda b: (b["path"], b["title_en"]))

    out = DATA / "catalog.json"
    out.write_text(json.dumps({"categories": categories, "books": books}, ensure_ascii=False,
                              separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"books: {len(books)}  categories: {len(categories)}")
    print(f"left out — no recorded/commercial licence: {len(dropped_lic)}; no Hebrew/ref/path: {len(dropped_other)}")
    for w in dropped_other[:10]:
        print("   ?", w["title"], "|", w["he"] or "-", "|", w["first_ref"] or "no ref", "|", w["path"] or "no path")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
