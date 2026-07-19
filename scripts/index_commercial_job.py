"""index_commercial_job.py — GPU embed + index the WHOLE commercial corpus, publish the ready index.

Runs on a cloud GPU (H100) as a batch job. Does end-to-end what took "forever" locally:

  1. merge    — download all 15 `Yehuda-Rubin/chavruta-commercial-<slug>` datasets' `<slug>.jsonl`.
  2. embed    — bge-m3 dense+sparse on GPU, BATCH at a time (default 2048), normalized → 3 index files.
  3. load     — upsert into a Qdrant SERVER via the project's own QdrantStore (named vectors dense+sparse,
                mem tier config identical to what the app reads) using the project's load_processed_chunks.
  4. index    — create the keyword payload indexes (ref / anchor_ref / license_he / license_en) so
                link-expansion + the licence filter are fast (without them, scroll filters full-scan).
  5. publish  — snapshot the collection + upload the snapshot AND the 3 index files to HF, so the index
                can be restored locally in seconds — no re-embedding, no re-indexing.

Run it with the project package available (docker/Dockerfile.commercial-index bundles chavruta + a
co-located Qdrant + bge-m3 weights). See nebius/job.commercial.yaml.

Env:
  HF_TOKEN               HF write token (required to publish)
  COMMERCIAL_NAMESPACE   HF namespace of the source tiers (default Yehuda-Rubin)
  BATCH                  embedding batch size (default 2048 — the user's H100 target)
  CHAVRUTA_QDRANT_URL    Qdrant server (default http://localhost:6333 — the co-located one)
  CHAVRUTA_COLLECTION    collection name (default chavruta_commercial)
  CHAVRUTA_MEM_TIER      store mem tier (default ssd — on-disk, memory-safe)
  INDEX_REPO             HF dataset to publish the snapshot + index files to
                         (default Yehuda-Rubin/chavruta-commercial-index)
  TIERS                  comma list to override the tier set (default: all 15)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

NAMESPACE = os.environ.get("COMMERCIAL_NAMESPACE", "Yehuda-Rubin")
PREFIX = os.environ.get("COMMERCIAL_PREFIX", "chavruta-commercial-")
BATCH = int(os.environ.get("BATCH", "2048"))
QDRANT_URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta_commercial")
MEM_TIER = os.environ.get("CHAVRUTA_MEM_TIER", "ssd")
INDEX_REPO = os.environ.get("INDEX_REPO", f"{NAMESPACE}/chavruta-commercial-index")
HF_TOKEN = os.environ.get("HF_TOKEN")

ALL_TIERS = ["second_temple", "reference", "musar", "tosefta", "liturgy", "kabbalah", "midrash",
             "chasidut", "jewish_thought", "shut", "yerushalmi", "mishnah", "tanakh", "halacha", "gemara"]
TIERS = [t.strip() for t in os.environ.get("TIERS", ",".join(ALL_TIERS)).split(",") if t.strip()]

OUT = Path("out")
MERGED = Path("commercial_merged.jsonl")
INDEX_FILES = ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")
PAYLOAD_INDEX_FIELDS = ("ref", "anchor_ref", "license_he", "license_en")
_t0 = time.time()


def _el() -> str:
    return f"{(time.time() - _t0) / 60:.1f}m"


# ── 1. merge ──────────────────────────────────────────────────────────────────
def step_merge() -> int:
    from huggingface_hub import hf_hub_download

    total = 0
    with MERGED.open("w", encoding="utf-8") as out:
        for slug in TIERS:
            repo = f"{NAMESPACE}/{PREFIX}{slug}"
            local = hf_hub_download(repo_id=repo, filename=f"{slug}.jsonl",
                                    repo_type="dataset", token=HF_TOKEN)
            n = 0
            for line in Path(local).open(encoding="utf-8"):
                if line.strip():
                    out.write(line if line.endswith("\n") else line + "\n")
                    n += 1
            total += n
            print(f"  + {slug:16} {n:>9,} chunks  (total {total:,})", flush=True)
    print(f"[merge] {total:,} chunks from {len(TIERS)} tiers → {MERGED} ({_el()})", flush=True)
    return total


# ── 2. embed ──────────────────────────────────────────────────────────────────
def step_embed() -> None:
    import numpy as np
    import torch
    from FlagEmbedding import BGEM3FlagModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[embed] bge-m3 on {device.upper()} | batch={BATCH}", flush=True)
    if device == "cpu":
        print("[embed] ⚠️  no GPU — this will be very slow", flush=True)

    chunks = [json.loads(l) for l in MERGED.open(encoding="utf-8") if l.strip()]
    docs = [c["document"] for c in chunks]
    print(f"[embed] {len(docs):,} chunks", flush=True)

    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=(device == "cuda"), device=device)
    OUT.mkdir(parents=True, exist_ok=True)
    dense_parts, sparse_rows = [], []
    for s in range(0, len(docs), BATCH):
        enc = model.encode(docs[s:s + BATCH], batch_size=BATCH, max_length=512,
                           return_dense=True, return_sparse=True, return_colbert_vecs=False)
        dense_parts.append(np.asarray(enc["dense_vecs"], dtype="float32"))
        for w in enc["lexical_weights"]:
            sparse_rows.append({int(t): float(v) for t, v in dict(w).items()})
        if (s // BATCH) % 10 == 0:
            print(f"  🧠 {min(s + BATCH, len(docs)):,}/{len(docs):,} ({_el()})", flush=True)

    vecs = np.vstack(dense_parts)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs /= norms

    np.save(str(OUT / "corpus_vectors.npy"), vecs)
    with (OUT / "corpus_sparse.jsonl").open("w", encoding="utf-8") as f:
        for i, row in enumerate(sparse_rows):
            f.write(json.dumps({"i": i, "sparse": row}) + "\n")
    with (OUT / "corpus_meta.jsonl").open("w", encoding="utf-8") as f:
        for i, c in enumerate(chunks):
            f.write(json.dumps({"i": i, "id": c["id"], "document": c["document"],
                                "metadata": c["metadata"]}, ensure_ascii=False) + "\n")
    print(f"[embed] ✅ {vecs.shape[0]:,}×{vecs.shape[1]} → {OUT} ({_el()})", flush=True)


# ── 3. load into Qdrant (the project's own loader → identical collection/payload) ─────────────────
def step_load() -> int:
    from chavruta.corpus.ingest import load_processed_chunks
    from chavruta.store.qdrant_store import QdrantStore

    store = QdrantStore(mode="server", url=QDRANT_URL)
    client = store._client_()
    if client.collection_exists(COLLECTION):
        print(f"♻️  dropping existing '{COLLECTION}' (fully regenerable)", flush=True)
        client.delete_collection(COLLECTION)
    print(f"[load] collection '{COLLECTION}' @ {QDRANT_URL} | mem_tier={MEM_TIER}", flush=True)
    store.ensure_collection(COLLECTION, dim=1024, mem_tier=MEM_TIER)

    batch, total = [], 0
    for sc in load_processed_chunks(str(OUT)):
        batch.append(sc)
        if len(batch) >= 1000:
            store.upsert(COLLECTION, batch)
            total += len(batch); batch = []
            if total % 50000 == 0:
                print(f"  ⬆️  {total:,} ({_el()})", flush=True)
    if batch:
        store.upsert(COLLECTION, batch); total += len(batch)
    print(f"[load] ✅ {total:,} points in '{COLLECTION}' ({_el()})", flush=True)
    return total


# ── 4. payload indexes ────────────────────────────────────────────────────────
def step_index() -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(url=QDRANT_URL, timeout=300)
    for field in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index(collection_name=COLLECTION, field_name=field,
                                        field_schema=models.PayloadSchemaType.KEYWORD, wait=True)
            print(f"  ✓ index on '{field}'", flush=True)
        except Exception as exc:
            print(f"  • '{field}': {exc}", flush=True)
    print(f"[index] ✅ payload indexes ready ({_el()})", flush=True)


# ── 5. snapshot + publish ─────────────────────────────────────────────────────
def step_publish() -> None:
    if not HF_TOKEN:
        raise SystemExit("[publish] HF_TOKEN not set — required to upload")
    import requests
    from huggingface_hub import HfApi, create_repo
    from qdrant_client import QdrantClient

    client = QdrantClient(url=QDRANT_URL, timeout=600)
    print("[publish] creating collection snapshot…", flush=True)
    snap = client.create_snapshot(collection_name=COLLECTION, wait=True)
    snap_name = snap.name
    snap_path = OUT / snap_name
    # Download the snapshot bytes from the server and stream them to disk.
    url = f"{QDRANT_URL}/collections/{COLLECTION}/snapshots/{snap_name}"
    with requests.get(url, stream=True, timeout=1200) as r:
        r.raise_for_status()
        with snap_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    print(f"[publish] snapshot {snap_path.stat().st_size / 1e9:.2f} GB", flush=True)

    create_repo(INDEX_REPO, repo_type="dataset", exist_ok=True, token=HF_TOKEN)
    api = HfApi()
    # The Qdrant snapshot (restore locally in seconds) + the raw index files (for bootstrap_rag).
    to_upload = [(snap_path, f"snapshots/{snap_name}")] + \
                [(OUT / f, f) for f in INDEX_FILES if (OUT / f).exists()]
    for path, name in to_upload:
        mb = path.stat().st_size / 1e6
        print(f"  ⬆️  {mb:9.1f} MB  {name}", flush=True)
        api.upload_file(path_or_fileobj=str(path), path_in_repo=name,
                        repo_id=INDEX_REPO, repo_type="dataset", token=HF_TOKEN)
    # A tiny manifest so consumers know what collection/vectors this snapshot restores to.
    manifest = {"collection": COLLECTION, "snapshot": f"snapshots/{snap_name}", "mem_tier": MEM_TIER,
                "dim": 1024, "vectors": "dense+sparse (bge-m3)", "tiers": TIERS}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    api.upload_file(path_or_fileobj=str(OUT / "manifest.json"), path_in_repo="manifest.json",
                    repo_id=INDEX_REPO, repo_type="dataset", token=HF_TOKEN)
    print(f"[publish] ✅ https://huggingface.co/datasets/{INDEX_REPO} ({_el()})", flush=True)


if __name__ == "__main__":
    print("=" * 64, flush=True)
    print("Chavruta.AI — commercial corpus: GPU embed + index + publish", flush=True)
    print(f"tiers={len(TIERS)} batch={BATCH} collection={COLLECTION} mem_tier={MEM_TIER}", flush=True)
    print("=" * 64, flush=True)
    step_merge()
    step_embed()
    step_load()
    step_index()
    step_publish()
    print(f"\n✅ done in {_el()} — restore locally with the snapshot in {INDEX_REPO}", flush=True)
