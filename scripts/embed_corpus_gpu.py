# -*- coding: utf-8 -*-
"""
embed_corpus_gpu.py — הטמעת הקורפוס על GPU (Colab/Kaggle/Nebius).
─────────────────────────────────────────────────────────────────────────────
למה: bge-m3 על CPU = ~14 שעות ל-15K צ'אנקים. על GPU = ~5-10 דקות.
הפלט **גנרי ל-store** (לא Chroma ולא Qdrant) — קובץ וקטורים נייד שנטען מקומית
לתוך Qdrant בלי הטמעה חוזרת. כך זמן-הריצה נשאר מקומי/offline.

קלט:  data/processed/all_chunks.json   (מטמיע את שדה ה-"document" של כל צ'אנק)
פלט:  out/corpus_vectors.npy           (float32, N×1024 — מנורמל)
       out/corpus_meta.jsonl            (N שורות: {id, document, metadata})

הרצה (Colab GPU):
    python scripts/embed_corpus_gpu.py --chunks all_chunks.json --out out/
"""

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default="data/processed/all_chunks.json")
    ap.add_argument("--out",    default="out")
    ap.add_argument("--model",  default="BAAI/bge-m3")
    ap.add_argument("--batch",  type=int, default=128)   # GPU — batch גדול
    ap.add_argument("--max_seq", type=int, default=512)
    args = ap.parse_args()

    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"⚙️  device: {device}  | batch: {args.batch}")
    if device == "cpu":
        print("⚠️  אין GPU — זה יהיה איטי מאוד. הרץ על Colab/Kaggle GPU.")

    # ── טען צ'אנקים ───────────────────────────────
    raw = json.loads(Path(args.chunks).read_text(encoding="utf-8"))
    chunks = raw["chunks"] if isinstance(raw, dict) else raw
    print(f"📦 chunks: {len(chunks):,}")

    docs = [c["document"] for c in chunks]
    ids  = [c["id"]       for c in chunks]
    metas = [c["metadata"] for c in chunks]

    # ── טען מודל והטמע ────────────────────────────
    model = SentenceTransformer(args.model, device=device)
    model.max_seq_length = args.max_seq
    print(f"🧠 {args.model} | dim={model.get_sentence_embedding_dimension()}")

    vecs = model.encode(
        docs,
        batch_size=args.batch,
        normalize_embeddings=True,     # ל-cosine
        convert_to_numpy=True,
        show_progress_bar=True,
    ).astype("float32")
    print(f"✅ embedded: {vecs.shape}")

    # ── שמירה (גנרי ל-store) ──────────────────────
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "corpus_vectors.npy", vecs)
    with open(out / "corpus_meta.jsonl", "w", encoding="utf-8") as f:
        for i, (cid, doc, meta) in enumerate(zip(ids, docs, metas)):
            f.write(json.dumps({"i": i, "id": cid, "document": doc, "metadata": meta},
                               ensure_ascii=False) + "\n")

    print(f"💾 saved:\n   {out/'corpus_vectors.npy'}  ({vecs.nbytes/1e6:.1f} MB)")
    print(f"   {out/'corpus_meta.jsonl'}")
    print("\nהבא: הורד את שני הקבצים והרץ מקומית  scripts/load_to_qdrant.py")


if __name__ == "__main__":
    main()
