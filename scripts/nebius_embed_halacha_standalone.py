# -*- coding: utf-8 -*-
"""nebius_embed_halacha_standalone.py — self-contained GPU embedding job.

The SIMPLE Nebius path: NO custom Docker image. A Serverless Job runs a public PyTorch
image, curls THIS one file from the public repo, and runs it. Zero dependency on the
chavruta package — only FlagEmbedding + numpy + huggingface_hub.

Install with PINNED versions (an unpinned `pip install FlagEmbedding` pulls a transformers
that breaks bge-m3 with "Could not import module 'AutoModel'"):
    pip install "FlagEmbedding==1.3.4" "transformers==4.44.2" huggingface_hub numpy
on a public PyTorch base image, e.g. pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime.

What it does (mirrors scripts/ingest_job.py steps 1–3, publish-only):
  1. merge — download every `<PREFIX>NN.jsonl` shard from the HF corpus dataset, concat.
  2. embed — bge-m3 dense + sparse on GPU, batched, normalized.
  3. publish — upload corpus_vectors.npy + corpus_sparse.jsonl + corpus_meta.jsonl to HF.

You then pull that index home and APPEND it into the local Docker Qdrant:
  python scripts/bootstrap_rag.py --repo <INDEX_REPO> --out out_halacha --append --profile local

Config (env vars):
  HF_TOKEN              HF write token (required to publish; read works without for public)
  CORPUS_REPO          HF dataset with the shards (default: Yehuda-Rubin/chavruta-torah-mixed)
  CORPUS_PREFIX        shard filename prefix     (default: halacha_part)
  INDEX_REPO           HF dataset to publish to  (default: Yehuda-Rubin/chavruta-index-halacha)
  BATCH                embedding batch size      (default: 128)
"""

import json
import os
import time
from pathlib import Path

HF_TOKEN = os.environ.get("HF_TOKEN")
CORPUS_REPO = os.environ.get("CORPUS_REPO", "Yehuda-Rubin/chavruta-torah-mixed")
CORPUS_PREFIX = os.environ.get("CORPUS_PREFIX", "halacha_part")
INDEX_REPO = os.environ.get("INDEX_REPO", "Yehuda-Rubin/chavruta-index-halacha")
BATCH = int(os.environ.get("BATCH", "128"))

OUT = Path("out")
MERGED = Path("halacha_merged.jsonl")
INDEX_FILES = ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")
t0 = time.time()


def _el() -> str:
    return f"{(time.time() - t0) / 60:.1f}m"


def step_merge() -> None:
    from huggingface_hub import HfApi, hf_hub_download

    files = sorted(
        f for f in HfApi().list_repo_files(CORPUS_REPO, repo_type="dataset", token=HF_TOKEN)
        if f.startswith(CORPUS_PREFIX) and f.endswith(".jsonl")
    )
    if not files:
        raise SystemExit(f"[merge] no shards matching {CORPUS_PREFIX!r} in {CORPUS_REPO}")
    print(f"[merge] {len(files)} shards from {CORPUS_REPO}")
    total = 0
    with MERGED.open("w", encoding="utf-8") as out:
        for fn in files:
            local = hf_hub_download(repo_id=CORPUS_REPO, filename=fn,
                                    repo_type="dataset", token=HF_TOKEN)
            for line in Path(local).open(encoding="utf-8"):
                if line.strip():
                    out.write(line if line.endswith("\n") else line + "\n")
                    total += 1
            print(f"  + {fn}  (total {total:,})")
    print(f"[merge] ✅ {total:,} chunks → {MERGED} ({_el()})")


def step_embed() -> None:
    import numpy as np
    import torch
    from FlagEmbedding import BGEM3FlagModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[embed] bge-m3 on {device.upper()} | batch={BATCH}")
    if device == "cpu":
        print("[embed] ⚠️  no GPU — this will be very slow")

    chunks = [json.loads(l) for l in MERGED.open(encoding="utf-8") if l.strip()]
    docs = [c["document"] for c in chunks]
    print(f"[embed] {len(docs):,} chunks")

    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=(device == "cuda"), device=device)
    dense_parts, sparse_rows = [], []
    for s in range(0, len(docs), BATCH):
        enc = model.encode(docs[s:s + BATCH], batch_size=BATCH, max_length=512,
                           return_dense=True, return_sparse=True, return_colbert_vecs=False)
        dense_parts.append(np.asarray(enc["dense_vecs"], dtype="float32"))
        for w in enc["lexical_weights"]:
            sparse_rows.append({int(t): float(v) for t, v in dict(w).items()})
        if (s // BATCH) % 10 == 0:
            print(f"  🧠 {min(s + BATCH, len(docs)):,}/{len(docs):,} ({_el()})")

    vecs = np.vstack(dense_parts)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs /= norms

    OUT.mkdir(parents=True, exist_ok=True)
    np.save(str(OUT / "corpus_vectors.npy"), vecs)
    with (OUT / "corpus_sparse.jsonl").open("w", encoding="utf-8") as f:
        for i, row in enumerate(sparse_rows):
            f.write(json.dumps({"i": i, "sparse": row}) + "\n")
    with (OUT / "corpus_meta.jsonl").open("w", encoding="utf-8") as f:
        for i, c in enumerate(chunks):
            f.write(json.dumps({"i": i, "id": c["id"], "document": c["document"],
                                "metadata": c["metadata"]}, ensure_ascii=False) + "\n")
    print(f"[embed] ✅ {vecs.shape[0]:,}×{vecs.shape[1]} → {OUT} ({_el()})")


def step_publish() -> None:
    if not HF_TOKEN:
        raise SystemExit("[publish] HF_TOKEN not set — required to upload")
    from huggingface_hub import HfApi, create_repo

    missing = [f for f in INDEX_FILES if not (OUT / f).exists()]
    if missing:
        raise SystemExit(f"[publish] missing index files: {missing}")

    print(f"[publish] → https://huggingface.co/datasets/{INDEX_REPO}")
    create_repo(INDEX_REPO, repo_type="dataset", exist_ok=True, token=HF_TOKEN)
    api = HfApi()
    for fn in INDEX_FILES:
        mb = (OUT / fn).stat().st_size / 1e6
        print(f"  ⬆️  {mb:8.2f} MB  {fn}")
        api.upload_file(path_or_fileobj=str(OUT / fn), path_in_repo=fn,
                        repo_id=INDEX_REPO, repo_type="dataset", token=HF_TOKEN)
    print(f"[publish] ✅ published ({_el()})")


if __name__ == "__main__":
    print("=" * 60)
    print("Chavruta.AI — standalone Halacha embed (no-Docker Nebius job)")
    print("=" * 60)
    step_merge()
    step_embed()
    step_publish()
    print(f"\n✅ done in {_el()} — pull home with bootstrap_rag.py --append")
