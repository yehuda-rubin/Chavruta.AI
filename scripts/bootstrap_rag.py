# -*- coding: utf-8 -*-
"""bootstrap_rag.py — download the prebuilt RAG and load it into a local Qdrant.

This is the END-USER side of the distribution model (see specs/001-chavruta-redesign/plan.md
→ "Index build & distribution"). The Nebius Job (scripts/ingest_job.py) is the factory that
computes embeddings on a GPU and publishes the prebuilt index to a Hugging Face dataset.
Regular users never run the Job — they run this one command to get a working RAG offline:

    python scripts/bootstrap_rag.py --repo <user>/chavruta-index

It downloads the index artifact (corpus_vectors.npy + corpus_sparse.jsonl + corpus_meta.jsonl)
from Hugging Face, then loads it into the local store (embedded or server Qdrant, per Profile).
No GPU and no re-embedding required — the vectors are already computed.

Why a download step at all (vs. the Job pushing to your machine): a Serverless Job's
filesystem is ephemeral and your machine has no public address for the cloud to push to.
HF is the shared "mailbox" — the Job pushes there, you pull from there.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.config.profile import Profile              # noqa: E402
from chavruta.corpus.ingest import load_processed_chunks  # noqa: E402
from chavruta.store.qdrant_store import QdrantStore      # noqa: E402

INDEX_FILES = ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")


def download_index(repo: str, out_dir: Path, token: str | None) -> None:
    """Pull the prebuilt index files from the HF dataset into out_dir."""
    from huggingface_hub import hf_hub_download

    out_dir.mkdir(parents=True, exist_ok=True)
    for fname in INDEX_FILES:
        print(f"⬇️  {repo}/{fname}")
        local = hf_hub_download(repo_id=repo, filename=fname, repo_type="dataset", token=token)
        (out_dir / fname).write_bytes(Path(local).read_bytes())
    print(f"✅ index downloaded → {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Download the prebuilt Chavruta RAG and load it locally.")
    ap.add_argument("--repo", required=True,
                    help="HF dataset repo holding the prebuilt index, e.g. user/chavruta-index")
    ap.add_argument("--out", default="out", help="where to store the downloaded index (default: out)")
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN"),
                    help="HF token (only needed for a private index repo)")
    ap.add_argument("--profile", default=None, help="overrides CHAVRUTA_PROFILE (default: local)")
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--skip-download", action="store_true",
                    help="reuse an index already present in --out instead of re-downloading")
    ap.add_argument("--append", action="store_true",
                    help="ADD this index to the existing collection instead of dropping it "
                         "(incremental load — e.g. adding halacha on top of Tanakh+Mishnah+Gemara+שו\"ת)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    if not args.skip_download:
        download_index(args.repo, out_dir, args.token)
    elif not all((out_dir / f).exists() for f in INDEX_FILES):
        ap.error(f"--skip-download set but index files are missing in {out_dir}")

    if args.profile:
        os.environ["CHAVRUTA_PROFILE"] = args.profile
    profile = Profile.from_env()

    print(f"📥 loading into Qdrant ({profile.qdrant_mode}: {profile.qdrant_path or profile.qdrant_url})")
    store = QdrantStore(mode=profile.qdrant_mode, path=profile.qdrant_path,
                        url=profile.qdrant_url, api_key=profile.qdrant_api_key)
    client = store._client_()
    if args.append:
        print(f"➕ --append — adding to existing collection '{profile.collection}' (not dropping)")
    elif client.collection_exists(profile.collection):
        print(f"♻️  dropping existing collection '{profile.collection}' (fully regenerable from the index)")
        client.delete_collection(profile.collection)
    store.ensure_collection(profile.collection, dim=1024)

    batch, total = [], 0
    for sc in load_processed_chunks(str(out_dir)):
        batch.append(sc)
        if len(batch) >= args.batch:
            store.upsert(profile.collection, batch)
            total += len(batch)
            print(f"  ⬆️  {total:,}", end="\r")
            batch = []
    if batch:
        store.upsert(profile.collection, batch)
        total += len(batch)

    print(f"\n✅ ready — {total:,} chunks in '{profile.collection}'. The RAG runs locally now.")


if __name__ == "__main__":
    main()
