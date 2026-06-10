# -*- coding: utf-8 -*-
"""embed_corpus_gpu.py — GPU corpus embedding, dense + sparse (full hybrid, research D5).

Why GPU: bge-m3 over 126k chunks ≈ 14h on CPU vs minutes-to-an-hour on a GPU
(Kaggle / Colab / Nebius). The output is **store-agnostic and portable** — load it locally
into Qdrant with scripts/load_to_store.py, no re-embedding (Principle II / reproducibility).

Emits BOTH retrieval channels of bge-m3 (via FlagEmbedding):
  • dense  (1024-dim, normalized)         → semantic similarity
  • sparse (token→weight lexical vector)  → exact-term matching ("רש\"י", refs)
Together they power hybrid RRF retrieval. (--dense-only falls back to the old behavior.)

Input : data/processed/all_chunks_full.json   (embeds each chunk's "document" field)
Output: out/corpus_vectors.npy                (float32, N×1024, normalized)
        out/corpus_sparse.jsonl               (N lines: {"i": idx, "sparse": {token_id: w}})
        out/corpus_meta.jsonl                 (N lines: {i, id, document, metadata})

Run (Kaggle/Colab GPU):
    pip install -U FlagEmbedding
    python scripts/embed_corpus_gpu.py --chunks all_chunks_full.json --out out/
"""

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default="data/processed/all_chunks_full.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--max_seq", type=int, default=512)
    ap.add_argument("--dense-only", action="store_true",
                    help="legacy mode: sentence-transformers, no sparse output")
    args = ap.parse_args()

    import numpy as np
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"⚙️  device: {device}  | batch: {args.batch}")
    if device == "cpu":
        print("⚠️  No GPU — this will be VERY slow. Run on Kaggle/Colab/Nebius GPU.")

    # ── load chunks ──────────────────────────────
    raw = json.loads(Path(args.chunks).read_text(encoding="utf-8"))
    chunks = raw["chunks"] if isinstance(raw, dict) else raw
    print(f"📦 chunks: {len(chunks):,}")

    docs = [c["document"] for c in chunks]
    ids = [c["id"] for c in chunks]
    metas = [c["metadata"] for c in chunks]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ── embed ────────────────────────────────────
    if args.dense_only:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(args.model, device=device)
        model.max_seq_length = args.max_seq
        vecs = model.encode(docs, batch_size=args.batch, normalize_embeddings=True,
                            convert_to_numpy=True, show_progress_bar=True).astype("float32")
        sparse_rows = None
    else:
        from FlagEmbedding import BGEM3FlagModel

        model = BGEM3FlagModel(args.model, use_fp16=(device == "cuda"), device=device)
        dense_parts, sparse_rows = [], []
        for s in range(0, len(docs), args.batch):
            batch = docs[s: s + args.batch]
            enc = model.encode(batch, batch_size=args.batch, max_length=args.max_seq,
                               return_dense=True, return_sparse=True,
                               return_colbert_vecs=False)
            dense_parts.append(np.asarray(enc["dense_vecs"], dtype="float32"))
            for w in enc["lexical_weights"]:
                sparse_rows.append({int(t): float(v) for t, v in dict(w).items()})
            print(f"  🧠 {min(s + args.batch, len(docs)):,}/{len(docs):,}", end="\r")
        vecs = np.vstack(dense_parts)
        # bge-m3 dense vecs are normalized already; normalize defensively for cosine
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
    print(f"\n✅ embedded: {vecs.shape}" + ("" if sparse_rows is None else f" + sparse×{len(sparse_rows):,}"))

    # ── save (store-agnostic) ────────────────────
    np.save(out / "corpus_vectors.npy", vecs)
    if sparse_rows is not None:
        with open(out / "corpus_sparse.jsonl", "w", encoding="utf-8") as f:
            for i, row in enumerate(sparse_rows):
                f.write(json.dumps({"i": i, "sparse": row}) + "\n")
    with open(out / "corpus_meta.jsonl", "w", encoding="utf-8") as f:
        for i, (cid, doc, meta) in enumerate(zip(ids, docs, metas)):
            f.write(json.dumps({"i": i, "id": cid, "document": doc, "metadata": meta},
                               ensure_ascii=False) + "\n")

    print(f"💾 saved → {out/'corpus_vectors.npy'}  ({vecs.nbytes/1e6:.1f} MB)")
    if sparse_rows is not None:
        print(f"         {out/'corpus_sparse.jsonl'}")
    print(f"         {out/'corpus_meta.jsonl'}")
    print("\nNext: download the files and run locally  scripts/load_to_store.py --in out/")


if __name__ == "__main__":
    main()
