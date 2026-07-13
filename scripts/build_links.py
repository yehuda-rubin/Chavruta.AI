# -*- coding: utf-8 -*-
"""Build the links graph (Phase 4, spec 002-query-understanding) → data/links.jsonl.

Scrolls the Qdrant collection and registers a `commentary_ref ↔ anchor_ref` edge for
every commentary chunk (the payload already carries `anchor_ref`). The resulting graph
lets the LinkExpander follow anchor chains: a pasuk reaches its commentaries (depth 1)
and their supercommentaries (depth 2 — e.g. pasuk → Rashi → Mizrachi), things vector
similarity alone does not encode. The pipeline auto-loads it and activates expansion.

    CHAVRUTA_QDRANT_URL=http://localhost:6333 python scripts/build_links.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qdrant_client import QdrantClient

from chavruta.corpus.links import LinkGraph

URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta")
OUT = Path(os.environ.get("CHAVRUTA_LINKS_PATH", "data/links.jsonl"))
PAGE = int(os.environ.get("BUILD_LINKS_PAGE", "10000"))


def main() -> None:
    client = QdrantClient(url=URL, timeout=600)
    graph = LinkGraph()
    scanned = anchored = 0
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION, limit=PAGE, offset=offset,
            with_payload=["ref", "anchor_ref", "work_id"], with_vectors=False,
        )
        for p in points:
            pl = p.payload or {}
            ref, anchor = pl.get("ref"), pl.get("anchor_ref")
            if ref and anchor:
                # anchor_work_id is best-effort; the expansion that matters (anchor → its
                # commentaries) carries the commentary's real work_id on that edge.
                graph.add_anchor(ref, anchor, pl.get("work_id", ""), anchor_work_id="tanakh")
                anchored += 1
        scanned += len(points)
        print(f"  scanned={scanned} anchored={anchored}", flush=True)
        if offset is None:
            break

    graph.save(OUT)
    print(f"done: {scanned} chunks, {anchored} anchor edges, {len(graph._adj)} nodes → {OUT}")


if __name__ == "__main__":
    main()
