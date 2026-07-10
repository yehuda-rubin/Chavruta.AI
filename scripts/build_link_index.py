# -*- coding: utf-8 -*-
"""build_link_index.py — the on-disk connection table + link-coverage report (NO LLM API).

Scrolls the 'chavruta' corpus once and writes an on-disk SQLite index mapping every chunk's
canonical ref (and anchor_ref) → chunk, using the shared canonical_ref() normalizer. Then streams
data/links.jsonl and reports how many of the ~681K Sefaria links actually RESOLVE to corpus
chunks — i.e. how connected the graph really is. This is the empirical number that decides whether
we need an external (Nebius) job to re-fetch a fuller links set.

    docker compose up -d qdrant
    .venv/Scripts/python.exe scripts/build_link_index.py
Outputs: data/ref_index.db  (table refidx(canon, chunk_ref, is_anchor), indexed on canon).
"""
from __future__ import annotations

import torch  # noqa: F401 — first (native DLL order)
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from chavruta.corpus.refs import canonical_ref

os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
QURL = os.environ["CHAVRUTA_QDRANT_URL"]
COLL = os.environ.get("CHAVRUTA_COLLECTION", "chavruta")
DB = REPO / "data" / "ref_index.db"
LINKS = REPO / "data" / "links.jsonl"
BATCH = 20000


def build_index() -> int:
    from qdrant_client import QdrantClient
    client = QdrantClient(url=QURL, timeout=300)
    total = client.count(COLL, exact=True).count
    print(f"corpus '{COLL}': {total:,} points → indexing to {DB.relative_to(REPO)}")

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("CREATE TABLE refidx (canon TEXT, chunk_ref TEXT, is_anchor INTEGER)")

    seen = 0
    t0 = time.time()
    offset = None
    while True:
        pts, offset = client.scroll(COLL, limit=BATCH, offset=offset,
                                    with_payload=["ref", "anchor_ref"], with_vectors=False)
        if not pts:
            break
        rows = []
        for p in pts:
            pl = p.payload or {}
            ref = pl.get("ref") or ""
            ck = canonical_ref(ref)
            if ck:
                rows.append((ck, ref, 0))
            anc = pl.get("anchor_ref")
            if anc:
                ak = canonical_ref(anc)
                if ak:
                    rows.append((ak, ref, 1))
        con.executemany("INSERT INTO refidx VALUES (?,?,?)", rows)
        seen += len(pts)
        if seen % (BATCH * 10) == 0 or offset is None:
            print(f"  {seen:,}/{total:,}  ({seen/max(total,1)*100:.0f}%)  {time.time()-t0:.0f}s")
        if offset is None:
            break
    con.commit()
    print("  building index on canon…")
    con.execute("CREATE INDEX idx_canon ON refidx(canon)")
    con.commit()
    n_keys = con.execute("SELECT COUNT(DISTINCT canon) FROM refidx").fetchone()[0]
    print(f"  ref index: {seen:,} chunks → {n_keys:,} distinct canonical refs")
    con.close()
    return seen


def coverage() -> None:
    con = sqlite3.connect(DB)

    def resolvable(canon: str) -> bool:
        return con.execute("SELECT 1 FROM refidx WHERE canon=? LIMIT 1", (canon,)).fetchone() is not None

    cache: dict[str, bool] = {}

    def ok(ref: str) -> bool:
        c = canonical_ref(ref)
        if c not in cache:
            cache[c] = resolvable(c)
        return cache[c]

    n = both = from_ok = to_ok = 0
    unmatched = []
    with LINKS.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            n += 1
            f_ok, t_ok = ok(d["from_ref"]), ok(d["to_ref"])
            from_ok += f_ok
            to_ok += t_ok
            if f_ok and t_ok:
                both += 1
            elif len(unmatched) < 8:
                miss = d["from_ref"] if not f_ok else d["to_ref"]
                unmatched.append(miss)
    print("\n" + "=" * 60)
    print(f"LINK COVERAGE (data/links.jsonl — {n:,} links)")
    print(f"  from_ref resolves to a corpus chunk: {from_ok:,}  ({from_ok/n*100:.1f}%)")
    print(f"  to_ref   resolves to a corpus chunk: {to_ok:,}  ({to_ok/n*100:.1f}%)")
    print(f"  BOTH endpoints resolve (usable edge): {both:,}  ({both/n*100:.1f}%)")
    print(f"  distinct link endpoints checked: {len(cache):,}")
    if unmatched:
        print("  sample unmatched endpoints:")
        for m in unmatched:
            print(f"    - {m!r}  → canon {canonical_ref(m)!r}")
    con.close()


def main() -> None:
    build_index()
    coverage()


if __name__ == "__main__":
    main()
