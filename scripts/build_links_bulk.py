# -*- coding: utf-8 -*-
"""build_links_bulk.py — build the WHOLE link graph from Sefaria's bulk links export (NO API load).

Far better than per-ref API calls: Sefaria publishes its entire links table as CSV in a public GCS
bucket (https://storage.googleapis.com/sefaria-export/links/links0.csv …), built for bulk download.
One ~500 MB download replaces ~1M API calls and puts ZERO load on Sefaria's API. It contains ALL
link types (commentary, quotation, reference, parallel), so it also supersedes the heuristic
commentary→base derivation with Sefaria's exact links.

Pipeline: stream each CSV → canonical_ref both citations → keep the edge only if BOTH endpoints
resolve in the corpus (ref_index.db, on-disk membership, low RAM) → dedup into links_corpus.db
(+ .jsonl) → (optional) upload to HF. CSV columns: Citation 1, Citation 2, Conection Type, Text 1,
Text 2, Category 1, Category 2.

    docker compose up -d qdrant           # ref_index.db must exist (scripts/build_link_index.py)
    .venv/Scripts/python.exe scripts/build_links_bulk.py --upload
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from chavruta.corpus.refs import canonical_ref
from chavruta.corpus.ref_index import RefIndex

DATA = REPO / "data"
REF_DB = DATA / "ref_index.db"
OUT_JSONL = DATA / "links_corpus.jsonl"
OUT_DB = DATA / "links_corpus.db"
URL = "https://storage.googleapis.com/sefaria-export/links/links{}.csv"
csv.field_size_limit(10_000_000)


def download(i: int, dest: Path) -> bool:
    try:
        with urllib.request.urlopen(URL.format(i), timeout=120) as r, dest.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--keep-csv", action="store_true", help="keep downloaded CSVs (default: delete)")
    args = ap.parse_args()
    if not REF_DB.exists():
        raise SystemExit(f"{REF_DB} missing — run scripts/build_link_index.py first")

    refs = RefIndex(REF_DB)
    tmp = DATA / "sefaria_links_csv"
    tmp.mkdir(exist_ok=True)

    if OUT_DB.exists():
        OUT_DB.unlink()
    con = sqlite3.connect(OUT_DB)
    con.execute("PRAGMA journal_mode=OFF"); con.execute("PRAGMA synchronous=OFF")
    con.execute("CREATE TABLE edges (from_canon TEXT, to_canon TEXT, link_type TEXT, UNIQUE(from_canon,to_canon))")

    t0 = time.time()
    total_rows = kept = 0
    by_type: dict[str, int] = {}
    i = 0
    while True:
        dest = tmp / f"links{i}.csv"
        print(f"  downloading links{i}.csv …", flush=True)
        if not download(i, dest):
            print(f"  links{i}.csv → 404 (end of set)")
            break
        with dest.open(encoding="utf-8", newline="") as f:
            rd = csv.reader(f)
            next(rd, None)  # header
            for row in rd:
                if len(row) < 3:
                    continue
                total_rows += 1
                c1, c2 = canonical_ref(row[0]), canonical_ref(row[1])
                typ = (row[2] or "reference").strip().lower()
                if c1 and c2 and c1 != c2 and refs.has(c1) and refs.has(c2):
                    cur = con.execute("INSERT OR IGNORE INTO edges VALUES (?,?,?)", (c1, c2, typ))
                    con.execute("INSERT OR IGNORE INTO edges VALUES (?,?,?)", (c2, c1, typ))
                    if cur.rowcount:
                        kept += 1
                        by_type[typ] = by_type.get(typ, 0) + 1
        con.commit()
        if not args.keep_csv:
            dest.unlink()
        print(f"    links{i}.csv done | rows seen {total_rows:,} | usable edges {kept:,} | {time.time()-t0:.0f}s", flush=True)
        i += 1

    con.execute("CREATE INDEX idx_from ON edges(from_canon)"); con.commit()
    # export portable jsonl (both directions, matching the db)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for a, b, t in con.execute("SELECT from_canon, to_canon, link_type FROM edges"):
            f.write(json.dumps({"from_ref": a, "to_ref": b, "link_type": t, "to_work_id": ""},
                               ensure_ascii=False) + "\n")
    n_edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    con.close()
    if not args.keep_csv:
        try:
            tmp.rmdir()
        except OSError:
            pass

    print("\n" + "=" * 60)
    print(f"LINK GRAPH (from Sefaria bulk export) → {OUT_DB.name} + {OUT_JSONL.name}")
    print(f"  CSV link rows scanned:        {total_rows:,}")
    print(f"  usable edges (both in corpus): {kept:,}  (undirected; {n_edges:,} directed rows)")
    print("  by connection type:")
    for t, c in sorted(by_type.items(), key=lambda kv: -kv[1])[:12]:
        print(f"    {t or '(reference)':16s} {c:,}")

    if args.upload:
        import subprocess
        subprocess.run([sys.executable, str(REPO / "scripts" / "upload_links_hf.py")], check=True)
    else:
        print("\nrun scripts/upload_links_hf.py to publish to HF.")


if __name__ == "__main__":
    main()
