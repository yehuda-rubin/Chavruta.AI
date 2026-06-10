# -*- coding: utf-8 -*-
"""load_to_store.py — load pre-embedded vectors into the configured store (task T020).

Reuses the existing Tanakh corpus (out/corpus_vectors.npy + out/corpus_meta.jsonl, dense
only) into the new `chavruta.store` — no re-embedding. Profile/config picks embedded (local)
vs server (cloud) Qdrant.

    python scripts/load_to_store.py --in out/ --profile local
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.config.profile import Profile          # noqa: E402
from chavruta.corpus.ingest import load_processed_chunks  # noqa: E402
from chavruta.store.qdrant_store import QdrantStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", default="out")
    ap.add_argument("--profile", default=None, help="overrides CHAVRUTA_PROFILE")
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--recreate", action="store_true", default=True,
                    help="drop + recreate the collection (it is fully regenerable from --in)")
    ap.add_argument("--no-recreate", dest="recreate", action="store_false")
    args = ap.parse_args()

    if args.profile:
        import os
        os.environ["CHAVRUTA_PROFILE"] = args.profile
    profile = Profile.from_env()

    store = QdrantStore(mode=profile.qdrant_mode, path=profile.qdrant_path, url=profile.qdrant_url)
    if args.recreate:
        client = store._client_()
        if client.collection_exists(profile.collection):
            print(f"♻️  dropping existing collection '{profile.collection}' (schema refresh)")
            client.delete_collection(profile.collection)
    store.ensure_collection(profile.collection, dim=1024)

    batch = []
    total = 0
    for sc in load_processed_chunks(args.indir):
        batch.append(sc)
        if len(batch) >= args.batch:
            store.upsert(profile.collection, batch)
            total += len(batch)
            print(f"  ⬆️  {total:,}", end="\r")
            batch = []
    if batch:
        store.upsert(profile.collection, batch)
        total += len(batch)

    print(f"\n✅ loaded {total:,} chunks into '{profile.collection}' "
          f"({profile.qdrant_mode}: {profile.qdrant_path or profile.qdrant_url})")


if __name__ == "__main__":
    main()
