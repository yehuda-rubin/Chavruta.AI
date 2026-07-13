# -*- coding: utf-8 -*-
"""ingest_job.py — Nebius Serverless Job entrypoint (the RAG "factory").

Builds the full prebuilt RAG index on a Nebius GPU Job and publishes it so anyone
can use it without re-running the Job:

  1. fetch_corpus   — get the raw chunks. Priority:
                        a) reuse local INGEST_CHUNKS_PATH if it already exists, else
                        b) download the corpus dataset from Hugging Face, else
                        c) pull Tanakh + commentators live from Sefaria (~300 calls).
  2. embed_corpus   — bge-m3 dense + sparse embeddings on GPU (~126k chunks).
  3. publish_index  — upload the prebuilt index (out/) to a Hugging Face dataset.
                       This is the artifact end users download (see scripts/bootstrap_rag.py).
  4. load_to_store  — optionally upsert into Qdrant Cloud for the live Endpoint.

Why this shape (see specs/001-chavruta-redesign/plan.md → "Index build & distribution"):
the Job is the FACTORY that computes embeddings on a GPU; Hugging Face is the WAREHOUSE
that distributes the result. Regular users only download (bootstrap_rag.py); the Job is
run by the maintainer (initial build + every corpus update) and by anyone embedding their
own corpus. A Serverless Job's filesystem is ephemeral, so it cannot push to a user's
machine directly — it publishes to HF and the user pulls.

All configuration comes from environment variables (see .env.example).

Corpus source (step 1):
  INGEST_CHUNKS_PATH        local chunks JSON; if present, fetch/HF are skipped
  INGEST_CORPUS_HF_REPO     HF dataset repo to pull the corpus from (e.g. user/chavruta-corpus)
  INGEST_CORPUS_HF_FILE     filename in that repo (default: all_chunks_full.json)
  INGEST_BOOKS              comma-separated book names for the Sefaria fallback (default: all)

Index publishing (step 3):
  INGEST_INDEX_HF_REPO      HF dataset repo to publish the prebuilt index to
  HF_TOKEN                  Hugging Face write token (required to publish)

Qdrant Cloud load (step 4):
  CHAVRUTA_QDRANT_URL       Qdrant Cloud cluster URL (if unset, this step is skipped)
  CHAVRUTA_QDRANT_API_KEY   Qdrant Cloud API key
  CHAVRUTA_COLLECTION       Qdrant collection name (default: chavruta)

Other:
  INGEST_BATCH              embedding batch size (default: 64)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Allow importing from src/ and scripts/ when run as a container entrypoint
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

CHUNKS_PATH = Path(os.environ.get("INGEST_CHUNKS_PATH", "data/processed/all_chunks_full.json"))
EMBED_OUT = Path("out")
BATCH = int(os.environ.get("INGEST_BATCH", "64"))
BOOKS_ENV = os.environ.get("INGEST_BOOKS", "")

CORPUS_HF_REPO = os.environ.get("INGEST_CORPUS_HF_REPO", "")
CORPUS_HF_FILE = os.environ.get("INGEST_CORPUS_HF_FILE", "all_chunks_full.json")
# Merge mode: download EVERY file in the repo whose name starts with this prefix and
# concatenate them into one corpus (e.g. INGEST_CORPUS_HF_PREFIX=halacha_part → all 44
# halacha_partNN.jsonl shards embedded in a single Job, one unified index out).
CORPUS_HF_PREFIX = os.environ.get("INGEST_CORPUS_HF_PREFIX", "")
INDEX_HF_REPO = os.environ.get("INGEST_INDEX_HF_REPO", "")
# Keep the existing collection on load (append) instead of dropping it — set false for
# incremental loads (e.g. adding halacha on top of Tanakh+Mishnah+Gemara+שו"ת).
RECREATE = os.environ.get("INGEST_RECREATE", "true").strip().lower() not in ("false", "0", "no")
HF_TOKEN = os.environ.get("HF_TOKEN")

# Files that make up the prebuilt index artifact (consumed by load_processed_chunks)
INDEX_FILES = ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")

t0 = time.time()


def _elapsed() -> str:
    return f"{(time.time() - t0) / 60:.1f}m"


def _load_chunks(path: Path) -> list:
    """Load chunks from a .jsonl (one per line) or .json ({"chunks":[…]} / [...])."""
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw["chunks"] if isinstance(raw, dict) else raw


def _chunk_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for l in path.open(encoding="utf-8") if l.strip())
    raw = json.loads(path.read_text(encoding="utf-8"))
    return len(raw["chunks"] if isinstance(raw, dict) else raw)


# ── Step 1: Get the corpus (local → HF → Sefaria) ─────────────────────────────

def step_fetch():
    # a) Reuse a local corpus file if it's already here.
    if CHUNKS_PATH.exists():
        print(f"[fetch] ✅ using local {CHUNKS_PATH} ({_chunk_count(CHUNKS_PATH):,} chunks)")
        return

    # a2) Merge mode — download every shard matching the prefix and concatenate.
    if CORPUS_HF_PREFIX and CORPUS_HF_REPO:
        from huggingface_hub import HfApi, hf_hub_download

        files = sorted(
            f for f in HfApi().list_repo_files(CORPUS_HF_REPO, repo_type="dataset", token=HF_TOKEN)
            if f.startswith(CORPUS_HF_PREFIX)
        )
        print(f"[fetch] merging {len(files)} shards matching {CORPUS_HF_PREFIX!r} from {CORPUS_HF_REPO}")
        CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with CHUNKS_PATH.open("w", encoding="utf-8") as out:
            for fn in files:
                local = hf_hub_download(repo_id=CORPUS_HF_REPO, filename=fn,
                                        repo_type="dataset", token=HF_TOKEN)
                for line in Path(local).open(encoding="utf-8"):
                    if line.strip():
                        out.write(line if line.endswith("\n") else line + "\n")
                        total += 1
                print(f"  + {fn}  (running total {total:,})")
        print(f"[fetch] ✅ merged {total:,} chunks → {CHUNKS_PATH} ({_elapsed()})")
        return

    # b) Pull the corpus dataset from Hugging Face (the common path: corpus is prebuilt).
    if CORPUS_HF_REPO:
        from huggingface_hub import hf_hub_download

        print(f"[fetch] downloading corpus {CORPUS_HF_REPO}/{CORPUS_HF_FILE} from Hugging Face …")
        local = hf_hub_download(
            repo_id=CORPUS_HF_REPO, filename=CORPUS_HF_FILE,
            repo_type="dataset", token=HF_TOKEN,
        )
        CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Copy out of the HF cache into the expected path so later steps find it.
        CHUNKS_PATH.write_bytes(Path(local).read_bytes())
        print(f"[fetch] ✅ {_chunk_count(CHUNKS_PATH):,} chunks → {CHUNKS_PATH} ({_elapsed()})")
        return

    # c) Fall back to a live Sefaria fetch (used to (re)build the corpus from source).
    print("[fetch] no local file and no HF repo — pulling Tanakh + commentators from Sefaria …")
    import importlib.util

    spec = importlib.util.spec_from_file_location("fetch_corpus", ROOT / "scripts" / "fetch_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    books = [b.strip() for b in BOOKS_ENV.split(",") if b.strip()] if BOOKS_ENV else None

    chunks = []
    stats = {"pasuk": 0, "commentary": 0, "works_fetched": 0, "works_404": 0}
    book_list = books or mod.ALL_BOOKS

    for bi, book in enumerate(book_list, 1):
        print(f"  [{bi}/{len(book_list)}] {book} ({_elapsed()})")
        base = mod.fetch_work(book)
        if base:
            stats["works_fetched"] += 1
            bhe, ben = base
            for ci, verses in enumerate(bhe or []):
                if not isinstance(verses, list):
                    continue
                for vi, vtext in enumerate(verses):
                    mod.add_chunk(chunks, stats, book, ci + 1, vi + 1, "pasuk", "",
                                  mod._seg(vtext), mod._seg(mod._get(ben, ci, vi)))
        time.sleep(0.3)
        for name in mod.COMMENTATORS + mod.TARGUMIM:
            res = None
            for title in mod._candidate_titles(name, book):
                res = mod.fetch_work(title)
                if res:
                    break
            if not res:
                stats["works_404"] += 1
                continue
            stats["works_fetched"] += 1
            che, cen = res
            for ci, verses in enumerate(che or []):
                if not isinstance(verses, list):
                    continue
                for vi, segs in enumerate(verses):
                    mod.add_chunk(chunks, stats, book, ci + 1, vi + 1, "commentary", name,
                                  mod._seg(segs), mod._seg(mod._get(cen, ci, vi)))
            time.sleep(0.3)

    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": {"total_chunks": len(chunks)}, "chunks": chunks}
    CHUNKS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"[fetch] ✅ {len(chunks):,} chunks saved → {CHUNKS_PATH} ({_elapsed()})")


# ── Step 2: Embed ─────────────────────────────────────────────────────────────

def step_embed():
    dense_path = EMBED_OUT / "corpus_vectors.npy"
    sparse_path = EMBED_OUT / "corpus_sparse.jsonl"
    meta_path = EMBED_OUT / "corpus_meta.jsonl"

    if dense_path.exists() and meta_path.exists():
        import numpy as np
        n = np.load(str(dense_path), mmap_mode="r").shape[0]
        print(f"[embed] ✅ skipped — {dense_path} already exists ({n:,} vectors)")
        return

    import numpy as np
    import torch
    from FlagEmbedding import BGEM3FlagModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[embed] bge-m3 on {device.upper()} | batch={BATCH}")
    if device == "cpu":
        print("[embed] ⚠️  no GPU detected — embedding will be slow")

    chunks = _load_chunks(CHUNKS_PATH)
    print(f"[embed] {len(chunks):,} chunks")

    docs = [c["document"] for c in chunks]
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=(device == "cuda"), device=device)

    dense_parts, sparse_rows = [], []
    for s in range(0, len(docs), BATCH):
        batch = docs[s: s + BATCH]
        enc = model.encode(batch, batch_size=BATCH, max_length=512,
                           return_dense=True, return_sparse=True,
                           return_colbert_vecs=False)
        dense_parts.append(np.asarray(enc["dense_vecs"], dtype="float32"))
        for w in enc["lexical_weights"]:
            sparse_rows.append({int(t): float(v) for t, v in dict(w).items()})
        if (s // BATCH) % 10 == 0:
            print(f"  🧠 {min(s + BATCH, len(docs)):,}/{len(docs):,} ({_elapsed()})")

    vecs = np.vstack(dense_parts)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    EMBED_OUT.mkdir(parents=True, exist_ok=True)
    np.save(str(dense_path), vecs)
    with open(sparse_path, "w", encoding="utf-8") as f:
        for i, row in enumerate(sparse_rows):
            f.write(json.dumps({"i": i, "sparse": row}) + "\n")
    with open(meta_path, "w", encoding="utf-8") as f:
        for i, c in enumerate(chunks):
            f.write(json.dumps({"i": i, "id": c["id"], "document": c["document"],
                                "metadata": c["metadata"]}, ensure_ascii=False) + "\n")
    print(f"[embed] ✅ {vecs.shape[0]:,}×{vecs.shape[1]} saved → {EMBED_OUT} ({_elapsed()})")


# ── Step 3: Publish the prebuilt index to Hugging Face ─────────────────────────

def step_publish():
    if not INDEX_HF_REPO:
        print("[publish] ⏭️  skipped — INGEST_INDEX_HF_REPO not set")
        return
    if not HF_TOKEN:
        print("[publish] ⚠️  skipped — HF_TOKEN not set (required to upload)")
        return

    from huggingface_hub import HfApi, create_repo

    missing = [f for f in INDEX_FILES if not (EMBED_OUT / f).exists()]
    if missing:
        raise RuntimeError(f"[publish] missing index files in {EMBED_OUT}: {missing}")

    print(f"[publish] uploading prebuilt index → https://huggingface.co/datasets/{INDEX_HF_REPO}")
    create_repo(INDEX_HF_REPO, repo_type="dataset", exist_ok=True, token=HF_TOKEN)
    api = HfApi()
    for fname in INDEX_FILES:
        src = EMBED_OUT / fname
        mb = src.stat().st_size / 1e6
        print(f"  ⬆️  {mb:8.2f} MB  {fname}")
        api.upload_file(
            path_or_fileobj=str(src),
            path_in_repo=fname,
            repo_id=INDEX_HF_REPO,
            repo_type="dataset",
            token=HF_TOKEN,
        )
    print(f"[publish] ✅ index published — users download via scripts/bootstrap_rag.py ({_elapsed()})")


# ── Step 4: Load to Qdrant Cloud (for the live Endpoint) ───────────────────────

def step_load():
    from chavruta.config.profile import Profile
    from chavruta.corpus.ingest import load_processed_chunks
    from chavruta.store.qdrant_store import QdrantStore

    profile = Profile.from_env()

    if not profile.qdrant_url:
        print("[load] ⏭️  skipped — CHAVRUTA_QDRANT_URL not set (publish-only run)")
        return
    if not profile.qdrant_api_key:
        print("[load] ⚠️  CHAVRUTA_QDRANT_API_KEY not set — proceeding without auth")

    print(f"[load] connecting to Qdrant: {profile.qdrant_url}")
    store = QdrantStore(mode="server", url=profile.qdrant_url, api_key=profile.qdrant_api_key)
    client = store._client_()

    if RECREATE and client.collection_exists(profile.collection):
        print(f"[load] ♻️  dropping existing collection '{profile.collection}'")
        client.delete_collection(profile.collection)
    elif not RECREATE:
        print(f"[load] ➕ INGEST_RECREATE=false — appending to '{profile.collection}'")
    store.ensure_collection(profile.collection, dim=1024)

    batch, total = [], 0
    for sc in load_processed_chunks(str(EMBED_OUT)):
        batch.append(sc)
        if len(batch) >= 512:
            store.upsert(profile.collection, batch)
            total += len(batch)
            print(f"  ⬆️  {total:,} ({_elapsed()})", end="\r")
            batch = []
    if batch:
        store.upsert(profile.collection, batch)
        total += len(batch)

    print(f"\n[load] ✅ {total:,} chunks → '{profile.collection}' @ {profile.qdrant_url} ({_elapsed()})")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Chavruta.AI — Nebius Serverless Ingest Job (RAG factory)")
    print("=" * 60)

    # Ensure cloud profile
    os.environ.setdefault("CHAVRUTA_PROFILE", "cloud")
    os.environ.setdefault("CHAVRUTA_QDRANT_MODE", "server")

    step_fetch()
    step_embed()
    step_publish()
    step_load()

    print(f"\n{'=' * 60}")
    print(f"✅  ingest complete in {_elapsed()}")
    print(f"{'=' * 60}")
