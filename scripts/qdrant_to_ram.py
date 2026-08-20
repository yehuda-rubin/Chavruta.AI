#!/usr/bin/env python3
"""qdrant_to_ram.py — the mirror of qdrant_to_disk.py: move an already-loaded collection to a
faster, more-RAM tier, IN PLACE.

qdrant_to_disk.py exists for a RAM-constrained machine (the production box). This is for the
opposite case — a rented GPU box with RAM to spare, where the collection was restored from a
snapshot that still carries the production "ssd" tier's settings (HNSW graph + vectors memmapped
from disk). HNSW graph search is many small random reads scattered across the whole index; that is
the single biggest per-query cost on the ssd tier, and moving just the graph into RAM ("16gb", the
default here) captures most of the win without needing the RAM of "max" (everything in RAM, several
times the footprint, for a benefit — faster rescoring off already-narrowed candidates — that matters
far less than graph search does).

No re-embed, no reload, no re-harvest — same points, same vectors, just where Qdrant keeps them.
Qdrant migrates segments in the background after the config change; get_collection status flips back
to "green" once the migration is done, which is what --wait blocks on.

    python scripts/qdrant_to_ram.py              # default: 16gb tier (HNSW + quantized vectors in RAM)
    python scripts/qdrant_to_ram.py --tier max --wait   # everything in RAM; needs real RAM headroom
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chavruta.store.qdrant_store import MEM_TIERS  # noqa: E402

URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta_commercial")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", choices=sorted(MEM_TIERS), default="16gb")
    ap.add_argument("--wait", action="store_true",
                    help="block until Qdrant reports the collection green again")
    args = ap.parse_args()

    from qdrant_client import QdrantClient, models

    client = QdrantClient(url=URL, timeout=300)
    if not client.collection_exists(COLLECTION):
        print(f"collection {COLLECTION!r} does not exist at {URL}")
        return 1

    cfg = MEM_TIERS[args.tier]
    print(f"moving {COLLECTION!r} to {args.tier!r} tier "
          f"(hnsw_on_disk={cfg['hnsw_on_disk']} quant_ram={cfg['quant_ram']} "
          f"on_disk_vectors={cfg['on_disk_vectors']})…")

    quant_cfg = (models.ScalarQuantization(
                    scalar=models.ScalarQuantizationConfig(
                        type=models.ScalarType.INT8, always_ram=cfg["quant_ram"]))
                 if cfg["quant"] == "int8" else models.Disabled())
    client.update_collection(
        collection_name=COLLECTION,
        hnsw_config=models.HnswConfigDiff(on_disk=cfg["hnsw_on_disk"]),
        quantization_config=quant_cfg,
        vectors_config={"dense": models.VectorParamsDiff(on_disk=cfg["on_disk_vectors"])},
    )
    # Nudge the optimizer to re-lay segments now instead of lazily on the next write.
    client.update_collection(
        collection_name=COLLECTION,
        optimizer_config=models.OptimizersConfigDiff(memmap_threshold=20000),
    )

    if args.wait:
        print("waiting for Qdrant to finish migrating segments…")
        while str(client.get_collection(COLLECTION).status).split(".")[-1].lower() != "green":
            time.sleep(5)
        print("done — collection is green.")
    else:
        info = client.get_collection(COLLECTION)
        print(f"status={info.status} points={info.points_count:,} "
              f"(migrating in the background — query latency settles once green)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
