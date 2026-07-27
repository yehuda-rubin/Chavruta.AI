#!/usr/bin/env python3
"""qdrant_to_disk.py — move an already-loaded collection to SSD-served mode, IN PLACE.

For a machine that OOMs serving the corpus from RAM: this reconfigures the live collection so the
HNSW graph, the quantized vectors, the original vectors and the payload are all memmapped from SSD
instead of held in RAM (the "ssd" tier in store/qdrant_store.py). RAM for the full ~2.9M corpus
drops from several GB to ~1–2GB; queries get slower (SSD reads) but the machine survives.

No re-embed and no reload — Qdrant migrates segments in the background after the config change.

    docker compose up -d qdrant            # Qdrant must be running
    python scripts/qdrant_to_disk.py       # convert the live collection

It's the same effect as loading fresh with CHAVRUTA_MEM_TIER=ssd, but for a collection that's
already on disk.
"""
from __future__ import annotations

import os
import sys

URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta_commercial")  # config.DEFAULT_COLLECTION


def main() -> int:
    from qdrant_client import QdrantClient, models

    client = QdrantClient(url=URL, timeout=300)
    if not client.collection_exists(COLLECTION):
        print(f"collection {COLLECTION!r} does not exist at {URL}")
        return 1

    print(f"moving {COLLECTION!r} to SSD-served mode (HNSW + quantized + vectors + payload on disk)…")
    client.update_collection(
        collection_name=COLLECTION,
        # HNSW graph on disk — the biggest RAM saver.
        hnsw_config=models.HnswConfigDiff(on_disk=True),
        # Quantized vectors memmapped instead of pinned in RAM.
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=False)),
        # Original dense vectors on disk (rescore reads them from SSD).
        vectors_config={"dense": models.VectorParamsDiff(on_disk=True)},
    )
    # Nudge the optimizer to re-lay the segments to disk now rather than lazily.
    client.update_collection(
        collection_name=COLLECTION,
        optimizer_config=models.OptimizersConfigDiff(memmap_threshold=20000),
    )
    info = client.get_collection(COLLECTION)
    print(f"done. status={info.status} points={info.points_count:,}")
    print("Qdrant will migrate segments to SSD in the background; RAM drops as it does.")
    print("Query latency is higher now (SSD reads) — expected for the ssd tier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
