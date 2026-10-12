#!/usr/bin/env python3
"""Assemble the per-book acceptance file from the HAND-MADE judgments.

The judgments themselves are in src/chavruta/corpus/data/book_acceptance_judgments.txt — one line per
range of books (sorted by path then English title), written by Claude reading every title. This script does
no classifying: it expands those ranges, checks that every book is covered exactly once, and writes
  docs/book_acceptance.csv   (open in Excel; UTF-8 with BOM)
  src/chavruta/corpus/data/book_acceptance.json

These are assessments from general knowledge, NOT halachic rulings; the two communities are not monolithic.
Usage:  .venv/Scripts/python.exe scripts/build_acceptance.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "chavruta" / "corpus" / "data"
VAL = {"A": ("accepted", "מקובל"), "P": ("partial", "מקובל בהסתייגות"),
       "R": ("rejected", "לא מקובל"), "U": ("unknown", "לא ידוע")}
CONF = {"H": ("high", "גבוהה"), "M": ("medium", "בינונית"), "L": ("low", "נמוכה")}


def main() -> None:
    cat = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    books = sorted(cat["books"], key=lambda b: (b["path"], b["title_en"]))
    cat_he = {k: v["he"] for k, v in cat["categories"].items()}

    judged: dict[int, tuple] = {}
    for n, raw in enumerate((DATA / "book_acceptance_judgments.txt").read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.startswith("#"):
            continue
        rng, h, d, c, note = (raw.split("|", 4) + [""])[:5]
        a, _, b = rng.partition("-")
        for i in range(int(a), int(b or a) + 1):
            if i in judged:
                sys.exit(f"book {i} judged twice (line {n})")
            judged[i] = (h, d, c, note.strip())
    missing = [i for i in range(1, len(books) + 1) if i not in judged]
    if missing or len(judged) != len(books):
        sys.exit(f"{len(missing)} books have no judgment, first: {missing[:10]}")

    rows = []
    for i, b in enumerate(books, 1):
        h, d, c, note = judged[i]
        rows.append({"title_he": b["title_he"], "title_en": b["title_en"], "path": b["path"],
                     "haredi": VAL[h][0], "dati": VAL[d][0], "confidence": CONF[c][0], "note": note})
    (DATA / "book_acceptance.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n",
                                               encoding="utf-8")
    out = ROOT / "docs" / "book_acceptance.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["שם הספר", "שם באנגלית", "קטגוריה", "חרדים", "דתיים", "רמת ביטחון", "הערה"])
        for i, b in enumerate(books, 1):
            h, d, c, note = judged[i]
            w.writerow([b["title_he"], b["title_en"], cat_he.get(b["path"].split("/")[0], ""),
                        VAL[h][1], VAL[d][1], CONF[c][1], note])
    print("books:", len(rows))
    print("haredi:", dict(Counter(r["haredi"] for r in rows)))
    print("dati:  ", dict(Counter(r["dati"] for r in rows)))
    print("confidence:", dict(Counter(r["confidence"] for r in rows)))
    print("wrote", out)


if __name__ == "__main__":
    main()
