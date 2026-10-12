#!/usr/bin/env python3
"""Delete the books listed in src/chavruta/corpus/data/excluded_works.json from the live stores:
the Qdrant collection and the reader's search_index.db. Run it ON the production host, from the repo
root, and RE-RUN IT AFTER EVERY RESTORE OR RE-UPLOAD FROM HuggingFace — the HF snapshot and the
chavruta-index-* datasets still contain these books (a Qdrant snapshot cannot be edited in place), so
a restore brings them back.

    python3 scripts/purge_excluded_books.py            # dry run: counts only
    python3 scripts/purge_excluded_books.py --apply    # delete

Order: ref list from search_index.db (chunk_id is UNIQUE-indexed, so a prefix range is cheap) ->
delete those refs from Qdrant by `ref` filter (keyword-indexed) -> delete the rows from search_index.db
(the FTS triggers follow). Do it in a quiet window and restart the search container afterwards.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = ROOT / "src" / "chavruta" / "corpus" / "data" / "excluded_works.json"


def qdrant(url: str, coll: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{url}/collections/{coll}/{path}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))["result"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--qdrant", default="http://localhost:6333")
    ap.add_argument("--collection", default="chavruta_commercial")
    ap.add_argument("--db", default=str(ROOT / "data" / "search_index.db"))
    args = ap.parse_args()

    prefixes = [w["ref_prefix"] for w in json.loads(EXCLUDED.read_text(encoding="utf-8"))]
    db = sqlite3.connect(args.db, timeout=120)
    refs: list[str] = []
    ranges: list[tuple[str, str]] = []
    for p in prefixes:
        lo, hi = p, p + "￿"
        ranges.append((lo, hi))
        for chunk_id, work_id in db.execute(
                "SELECT chunk_id, work_id FROM chunks WHERE chunk_id >= ? AND chunk_id < ?", (lo, hi)):
            suffix = "_" + work_id
            refs.append(chunk_id[: -len(suffix)] if chunk_id.endswith(suffix) else chunk_id)
        print(f"{p}: {sum(1 for r in refs if r.startswith(p))} rows in search_index.db")

    def count_qdrant() -> int:
        n = 0
        for i in range(0, len(refs), 400):
            n += qdrant(args.qdrant, args.collection, "points/count", {
                "filter": {"must": [{"key": "ref", "match": {"any": refs[i:i + 400]}}]}, "exact": True})["count"]
        return n

    print(f"refs to remove: {len(refs)}   in Qdrant now: {count_qdrant()}")
    if not args.apply:
        print("dry run — nothing deleted (use --apply)")
        return

    for i in range(0, len(refs), 400):
        qdrant(args.qdrant, args.collection, "points/delete?wait=true", {
            "filter": {"must": [{"key": "ref", "match": {"any": refs[i:i + 400]}}]}})
    print("Qdrant after delete:", count_qdrant())

    with db:
        for lo, hi in ranges:
            db.execute("DELETE FROM chunks WHERE chunk_id >= ? AND chunk_id < ?", (lo, hi))
    left = sum(db.execute("SELECT COUNT(*) FROM chunks WHERE chunk_id >= ? AND chunk_id < ?", r).fetchone()[0]
               for r in ranges)
    print("search_index.db rows left for these books:", left)


if __name__ == "__main__":
    main()
