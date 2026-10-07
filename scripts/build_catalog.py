#!/usr/bin/env python3
"""Build the library catalogue: every commercially-licensed work in the corpus, with a Hebrew title
and its category path in Hebrew and English.

Output: src/chavruta/corpus/data/catalog.json (package data — ships with the code), shape
    {"categories": {"<en path>": {"en", "he", "order"}},
     "books": [{"title_en", "title_he", "path", "segments", "first_ref", "license"}]}

Works come from --works (output of scan_collection_works.py on the live collection — the commercial
set itself, so no licence filter) or, without it, the legacy data/ref_index.db, a superset of the live
collection that is filtered fail-closed with rights.allows_commercial_use on licenses.json. The
`license` field is display-only and may be empty for live-scan books (per-chunk licence is not
stored in the collection payload).

Usage:  .venv/Scripts/python.exe scripts/build_catalog.py --works scan.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chavruta.corpus import rights  # noqa: E402
from inventory_works import DATA, _natural, collect_works, resolve  # noqa: E402


def works_from_scan(path: str) -> list[dict]:
    """Works from scripts/scan_collection_works.py output (the LIVE collection) instead of the
    legacy ref_index.db. Refs that are free Hebrew text (Wikisource: 'חידושי הריטב"א/…, אות') do not
    resolve to a Sefaria title and are skipped here; they are reported by the caller."""
    he = json.loads((DATA / "hebrew_titles.json").read_text(encoding="utf-8"))
    he.update(json.loads((DATA / "hebrew_titles_overrides.json").read_text(encoding="utf-8")))
    lic = json.loads((DATA / "licenses.json").read_text(encoding="utf-8"))
    works: dict[str, dict] = {}
    for raw, (n, first) in json.loads(Path(path).read_text(encoding="utf-8"))["works"].items():
        title, entry = resolve(raw.replace("_", " "), he)
        if not entry:
            continue
        w = works.setdefault(title, {
            "title": title, "segments": 0, "first_ref": first, "he": entry.get("he", ""),
            "cat": entry.get("cat", ""), "path": entry.get("path", ""),
            "he_license": (lic.get(title) or {}).get("he_license", ""),
        })
        w["segments"] += n
        if _natural(first) < _natural(w["first_ref"]):
            w["first_ref"] = first
    return sorted(works.values(), key=lambda r: r["title"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--works", help="scan_collection_works.py output; default: legacy ref_index.db")
    ap.add_argument("--reader-refs", help="lookup_reader_refs.py output: corpus ref -> the reader's own ref."
                    " Without it first_ref stays in corpus form, which the reader does NOT open.")
    args = ap.parse_args()
    cat_titles = json.loads((DATA / "category_titles.json").read_text(encoding="utf-8"))
    works = works_from_scan(args.works) if args.works else collect_works()
    live = bool(args.works)

    reader = json.loads(Path(args.reader_refs).read_text(encoding="utf-8")) if args.reader_refs else {}
    books, dropped_lic, dropped_other = [], [], []
    he_mismatch = 0
    for w in works:
        if reader:
            hit = reader.get(w["first_ref"])
            if not hit:
                w = {**w, "first_ref": ""}      # not in the reader's index → cannot be opened
            else:
                w = {**w, "first_ref": hit["ref"]}
                he_mismatch += bool(hit["author_he"]) and hit["author_he"] != w["he"]
        if not w["he"] or not w["first_ref"] or not w["path"]:
            dropped_other.append(w)
        elif not live and not rights.allows_commercial_use(w["he_license"]):
            # Legacy ref_index.db is a superset of the commercial collection: filter by licence,
            # fail closed. A scan of the live collection needs no filter — it IS the commercial set.
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
    if reader:
        print(f"Hebrew title differs from the reader's own author_he: {he_mismatch}")
    print(f"books: {len(books)}  categories: {len(categories)}")
    print(f"left out — no recorded/commercial licence: {len(dropped_lic)}; no Hebrew/ref/path: {len(dropped_other)}")
    for w in dropped_other[:10]:
        print("   ?", w["title"], "|", w["he"] or "-", "|", w["first_ref"] or "no ref", "|", w["path"] or "no path")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
