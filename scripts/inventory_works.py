#!/usr/bin/env python3
"""Step 0 of the library feature: which works does the corpus hold, and which lack a Hebrew title?

Read-only and free: works come from data/ref_index.db (one row per corpus ref, underscore-dot form),
NOT from Qdrant. ref_index.db may be a superset of the live commercial collection, so each work is
also checked against licenses.json (he_license) and reported as commercial / not.

Usage:  .venv/Scripts/python.exe scripts/inventory_works.py [--out .scratch/inventory.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "chavruta" / "corpus" / "data"
_TAIL = re.compile(r"(?:[.\s]\d+[ab]?)+$")


def work_of(chunk_ref: str) -> str:
    """'Rashi_on_Genesis.1.1.1' -> 'Rashi on Genesis'. A trailing section number is dropped."""
    return _TAIL.sub("", chunk_ref).replace("_", " ").strip()


_HEB = re.compile(r"[֐-׿]")


def resolve(title: str, he: dict) -> tuple[str, dict | None]:
    """Map a ref-derived title to its Sefaria index title + entry.

    The ref index holds three shapes: plain ('Rashi on Genesis'), comma ('Beit Yosef, Orach Chayim' —
    work, then a section/volume/book), and a Hebrew-prefixed duplicate ('רש"י on Rashi on Shabbat').
    Strip the Hebrew prefix, then try the whole title and each comma-prefix, longest first.
    """
    if _HEB.search(title) and " on " in title:
        title = title.split(" on ", 1)[1]
    parts = [p.strip() for p in title.split(",")]
    for i in range(len(parts), 0, -1):
        cand = ", ".join(parts[:i])
        if cand in he:
            return cand, he[cand]
    return title, None


def live_ref(chunk_ref: str) -> str:
    """Legacy ref_index spelling -> the live corpus spelling.

    'אברבנאל on Abarbanel on Amos 4.1.1' -> 'Abarbanel_on_Amos.4.1.1'. Already-live refs pass through.
    Talmud daf refs ('Berakhot 2a') are NOT converted here — they need talmud_ref's amud math.
    """
    if _HEB.search(chunk_ref) and " on " in chunk_ref:
        chunk_ref = chunk_ref.split(" on ", 1)[1]
    m = _TAIL.search(chunk_ref)
    if not m:
        return chunk_ref.replace(" ", "_")
    head = chunk_ref[: m.start()].replace(" ", "_")
    return head + "." + ".".join(re.split(r"[.\s]+", m.group(0).strip(" .")))


def _natural(ref: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", ref)]


def collect_works() -> list[dict]:
    """One row per Sefaria index title found in ref_index.db (slow: scans ~3.7M rows, ~2 min)."""
    he = json.loads((DATA / "hebrew_titles.json").read_text(encoding="utf-8"))
    he.update(json.loads((DATA / "hebrew_titles_overrides.json").read_text(encoding="utf-8")))
    lic = json.loads((DATA / "licenses.json").read_text(encoding="utf-8"))

    con = sqlite3.connect(f"file:{ROOT / 'data' / 'ref_index.db'}?mode=ro", uri=True)
    works: dict[str, dict] = {}
    for (ref,) in con.execute("SELECT DISTINCT chunk_ref FROM refidx"):
        title, entry = resolve(work_of(ref), he)
        w = works.get(title)
        if w is None:
            w = works[title] = {
                "title": title, "segments": 0, "first_ref": "",
                "he": (entry or {}).get("he", ""), "cat": (entry or {}).get("cat", ""),
                "path": (entry or {}).get("path", ""),
                "he_license": (lic.get(title) or {}).get("he_license", ""),
            }
        w["segments"] += 1
        # Natural-order first ref in the live spelling, so the library opens a book at its beginning.
        live = live_ref(ref)
        if not w["first_ref"] or _natural(live) < _natural(w["first_ref"]):
            w["first_ref"] = live
    return sorted(works.values(), key=lambda r: r["title"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / ".scratch" / "inventory.json"))
    args = ap.parse_args()

    rows = collect_works()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    missing = [r for r in rows if not r["he"]]
    print(f"works in ref_index: {len(rows)}   with Hebrew title: {len(rows) - len(missing)}   missing: {len(missing)}")
    print(f"segments covered by missing titles: {sum(r['segments'] for r in missing)} / {sum(r['segments'] for r in rows)}")
    for r in sorted(missing, key=lambda r: -r["segments"])[:40]:
        print(f"  {r['segments']:>7}  {r['title']}   [{r['he_license']}]")


if __name__ == "__main__":
    main()
