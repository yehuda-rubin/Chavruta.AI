# -*- coding: utf-8 -*-
"""load_gemara_sliced.py — load the big gemara index into local Qdrant in small slices.

gemara (711k×1024) loaded in one shot thrashes a 16GB box (Qdrant already holds ~2.2M points).
Fix: load it in fixed-size slices, each in a FRESH subprocess that exits and releases all memory
before the next — so nothing accumulates on the loader side. Indexing is deferred (threshold=0)
for the whole run and rebuilt once at the end. Resumable via a .done file of finished slices.

    docker compose up -d qdrant
    python scripts/load_gemara_sliced.py            # loads/for-resumes all slices from out_load/
    python scripts/load_gemara_sliced.py --slice 0 40000   # (internal worker mode)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUT = Path("out_load")
COLLECTION = "chavruta"
URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
SLICE = 40_000
BATCH = 256
DONE = Path("data/processed/gemara_slices.done")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def worker(a: int, b: int) -> None:
    """Upsert only rows [a, b) — mmap vectors, stream meta+sparse in lockstep. Fresh process."""
    import numpy as np

    from chavruta.corpus.ingest import payload_from_legacy_meta
    from chavruta.store.base import StoredChunk
    from chavruta.store.qdrant_store import QdrantStore

    vecs = np.load(OUT / "corpus_vectors.npy", mmap_mode="r")
    store = QdrantStore(mode="server", url=URL)
    meta_f = (OUT / "corpus_meta.jsonl").open(encoding="utf-8")
    sparse_f = (OUT / "corpus_sparse.jsonl").open(encoding="utf-8")
    batch: list[StoredChunk] = []
    n = 0
    try:
        for j, mline in enumerate(meta_f):
            sline = sparse_f.readline()        # keep sparse aligned even while skipping
            if j < a:
                continue
            if j >= b:
                break
            meta = json.loads(mline)
            payload = payload_from_legacy_meta(meta)
            sparse = {}
            if sline:
                d = json.loads(sline)
                sparse = {int(t): float(w) for t, w in d["sparse"].items()}
            batch.append(StoredChunk(chunk_id=payload["chunk_id"],
                                     dense=[float(x) for x in vecs[j]],
                                     sparse=sparse, payload=payload))
            if len(batch) >= BATCH:
                store.upsert(COLLECTION, batch); n += len(batch); batch = []
        if batch:
            store.upsert(COLLECTION, batch); n += len(batch)
    finally:
        meta_f.close(); sparse_f.close()
    print(f"  slice {a}:{b} → upserted {n:,}", flush=True)


def _done() -> set[str]:
    return {l.strip() for l in DONE.read_text().splitlines()} if DONE.exists() else set()


def orchestrate() -> None:
    import numpy as np
    from qdrant_client import QdrantClient, models

    total = int(np.load(OUT / "corpus_vectors.npy", mmap_mode="r").shape[0])
    slices = [(a, min(a + SLICE, total)) for a in range(0, total, SLICE)]
    DONE.parent.mkdir(parents=True, exist_ok=True)

    c = QdrantClient(url=URL, timeout=120)
    c.update_collection(COLLECTION, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=0))
    print(f"gemara: {total:,} rows in {len(slices)} slices of {SLICE:,} (indexing deferred)")

    env = {**os.environ, "CHAVRUTA_PROFILE": "local", "CHAVRUTA_QDRANT_MODE": "server",
           "CHAVRUTA_QDRANT_URL": URL, "CHAVRUTA_QDRANT_API_KEY": "", "CHAVRUTA_MEM_TIER": "16gb"}
    done = _done()
    t0 = time.time()
    for i, (a, b) in enumerate(slices, 1):
        key = f"{a}:{b}"
        if key in done:
            continue
        print(f"[{i}/{len(slices)}] slice {a}:{b} …", flush=True)
        rc = subprocess.run([sys.executable, __file__, "--slice", str(a), str(b)], env=env).returncode
        if rc == 0:
            with DONE.open("a") as f:
                f.write(key + "\n")
        else:
            print(f"  ❌ slice {a}:{b} failed (rc={rc}); re-run to retry", flush=True)
        time.sleep(3)                          # let Qdrant settle between slices

    print("\nrebuilding index (threshold → 20000)…", flush=True)
    c.update_collection(COLLECTION, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000))
    n = c.count(COLLECTION, exact=True).count
    print(f"✅ done in {(time.time()-t0)/60:.1f}m — collection now {n:,} points", flush=True)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--slice":
        worker(int(sys.argv[2]), int(sys.argv[3]))
    else:
        orchestrate()
