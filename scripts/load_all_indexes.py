# -*- coding: utf-8 -*-
"""load_all_indexes.py — load all 15 prebuilt indexes from HF into the LOCAL Qdrant server.

Everything local (Qdrant on localhost:6333, bge-m3 on CPU); only the LLM is remote (Nebius).
Targets the local server with memory tier applied (quantization + on-disk) so the full ~2.9M
corpus fits a 16GB machine. Idempotent (upserts keyed by chunk_id) AND resumable: finished
categories are recorded in a .done file and skipped on re-run — so a mid-run stall (e.g. the
laptop sleeping and killing an HF download) costs nothing, just re-run.

    docker compose up -d qdrant                 # local Qdrant first
    python scripts/load_all_indexes.py          # load / resume (skips done categories)
    python scripts/load_all_indexes.py --fresh  # drop the collection and load from scratch
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# smallest → largest, so the light ones land first and a failure late costs least
SLUGS = ["second_temple", "reference", "musar", "tosefta", "liturgy", "kabbalah",
         "midrash", "chasidut", "jewish_thought", "shut", "yerushalmi", "mishnah",
         "tanakh", "halacha", "gemara"]
NS = "Yehuda-Rubin"
COLLECTION = "chavruta"
QDRANT_URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
OUT = Path("out_load")
DONE_FILE = Path("data/processed/local_load.done")
INDEX_FILES = ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")

# force LOCAL targeting regardless of .env; fail fast on stalled HF downloads (no infinite hang)
ENV = dict(os.environ)
ENV.update({
    "CHAVRUTA_PROFILE": "local",
    "CHAVRUTA_QDRANT_MODE": "server",
    "CHAVRUTA_QDRANT_URL": QDRANT_URL,
    "CHAVRUTA_QDRANT_API_KEY": "",
    "CHAVRUTA_MEM_TIER": os.environ.get("CHAVRUTA_MEM_TIER", "16gb"),
    "CHAVRUTA_COLLECTION": COLLECTION,
    "HF_HUB_DOWNLOAD_TIMEOUT": "30",   # a dead socket errors out instead of hanging the run
})


def _done() -> set[str]:
    if DONE_FILE.exists():
        return {l.strip() for l in DONE_FILE.read_text(encoding="utf-8").splitlines() if l.strip()}
    return set()


def main() -> None:
    from qdrant_client import QdrantClient
    client = QdrantClient(url=QDRANT_URL)
    client.get_collections()  # sanity: server reachable

    if "--fresh" in sys.argv:
        if client.collection_exists(COLLECTION):
            print(f"🗑️  --fresh: dropping '{COLLECTION}'")
            client.delete_collection(COLLECTION)
        DONE_FILE.unlink(missing_ok=True)

    done = _done()
    todo = [s for s in SLUGS if s not in done]
    OUT.mkdir(exist_ok=True)
    DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    print(f"resume: {len(done)} done, {len(todo)} to load → {todo}")

    ok, fail = list(done), []
    t0 = time.time()
    for i, slug in enumerate(todo, 1):
        repo = f"{NS}/chavruta-index-{slug}"
        print(f"\n{'='*60}\n[{i}/{len(todo)}] {slug}   {repo}\n{'='*60}", flush=True)
        cmd = [sys.executable, "scripts/bootstrap_rag.py", "--repo", repo,
               "--out", str(OUT), "--append", "--profile", "local"]
        rc = subprocess.run(cmd, env=ENV).returncode
        if rc == 0:
            ok.append(slug)
            with DONE_FILE.open("a", encoding="utf-8") as f:
                f.write(slug + "\n")
        else:
            fail.append(slug)
        for f in INDEX_FILES:                      # free disk before the next download
            try:
                (OUT / f).unlink()
            except FileNotFoundError:
                pass
        print(f"   ⏱️  {(time.time()-t0)/60:.1f}m | done={len(ok)}/15 fail={len(fail)}", flush=True)

    n = client.count(COLLECTION, exact=True).count if client.collection_exists(COLLECTION) else 0
    print(f"\n{'='*60}\n✅ collection '{COLLECTION}' now has {n:,} points | done={len(ok)}/15")
    if fail:
        print(f"❌ failed (just re-run to retry): {fail}")


if __name__ == "__main__":
    main()
