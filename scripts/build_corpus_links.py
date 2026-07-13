# -*- coding: utf-8 -*-
"""build_corpus_links.py — build the link graph from the corpus itself (NO API, NO external fetch).

A Sefaria commentary ref encodes what it comments on: ``Rashi on Chullin 11.3.1`` comments on
``Chullin 11.3`` (base = commentary minus the "<Commentator> on " prefix and, usually, one trailing
segment). We derive that base canonically and keep the edge ONLY if the base text actually exists in
the corpus — so every emitted edge is usable by construction (unlike the stale Sefaria links.jsonl,
which resolved 0%). Base depth varies by work, so we try both base-depths (drop 1 or 0 trailing
segments) and take whichever resolves. Precision-safe: a wrong derivation simply finds no base and is
dropped. Measured recall ≈ 79% of commentaries.

    .venv/Scripts/python.exe scripts/build_link_index.py     # once: builds data/ref_index.db
    .venv/Scripts/python.exe scripts/build_corpus_links.py   # then: builds data/links_corpus.jsonl
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from chavruta.corpus.refs import canonical_ref

DB = REPO / "data" / "ref_index.db"
OUT = REPO / "data" / "links_corpus.jsonl"
GRAPH_DB = REPO / "data" / "links_corpus.db"


def derive_base(comm_canon: str, canon_set: set[str]) -> str | None:
    """Base ref a commentary comments on: strip the '<Commentator> on ' prefix, then take the
    deepest trailing-segment count (drop 1, else 0) whose result exists in the corpus."""
    i = comm_canon.find(" on ")
    if i == -1:
        return None
    toks = comm_canon[i + 4:].split()
    for drop in (1, 0):
        if len(toks) > drop:
            cand = " ".join(toks[:len(toks) - drop] if drop else toks)
            if cand and cand != comm_canon and cand in canon_set:
                return cand
    return None


def main() -> None:
    if not DB.exists():
        print(f"{DB} not found — run scripts/build_link_index.py first"); sys.exit(1)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    print("loading canonical ref set from the index…")
    canon_set = {r[0] for r in con.execute("SELECT DISTINCT canon FROM refidx")}
    print(f"  {len(canon_set):,} distinct canonical refs in the corpus")

    commentaries = [r[0] for r in con.execute(
        "SELECT DISTINCT canon FROM refidx WHERE canon LIKE '% on %'")]
    con.close()
    print(f"  {len(commentaries):,} distinct commentary refs to link")

    if GRAPH_DB.exists():
        GRAPH_DB.unlink()
    g = sqlite3.connect(GRAPH_DB)
    g.execute("PRAGMA journal_mode=OFF")
    g.execute("PRAGMA synchronous=OFF")
    g.execute("CREATE TABLE edges (from_canon TEXT, to_canon TEXT)")

    written = base_missing = 0
    nodes: set[str] = set()
    with OUT.open("w", encoding="utf-8") as f:
        for comm_canon in commentaries:
            base = derive_base(comm_canon, canon_set)
            if base is None:
                base_missing += 1
                continue
            f.write(json.dumps({"from_ref": base, "to_ref": comm_canon,
                                "link_type": "commentary", "to_work_id": ""},
                               ensure_ascii=False) + "\n")
            # both directions so neighbours() works from either endpoint (pasuk↔commentary)
            g.execute("INSERT INTO edges VALUES (?,?)", (base, comm_canon))
            g.execute("INSERT INTO edges VALUES (?,?)", (comm_canon, base))
            written += 1
            nodes.add(base); nodes.add(comm_canon)
    g.commit()
    g.execute("CREATE INDEX idx_from ON edges(from_canon)")
    g.commit()
    g.close()

    print("\n" + "=" * 60)
    print(f"CORPUS LINK GRAPH → {OUT.relative_to(REPO)}  +  {GRAPH_DB.relative_to(REPO)} (on-disk)")
    print(f"  usable commentary→base edges (both in corpus): {written:,}  "
          f"({written/max(len(commentaries),1)*100:.1f}% of commentaries)")
    print(f"  dropped (base not resolvable in corpus):       {base_missing:,}")
    print(f"  distinct nodes connected:                      {len(nodes):,}")
    print(f"  vs stale data/links.jsonl usable edges: 0")


if __name__ == "__main__":
    main()
