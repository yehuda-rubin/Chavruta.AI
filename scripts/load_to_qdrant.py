# -*- coding: utf-8 -*-
"""
load_to_qdrant.py — טוען וקטורים מוטמעים-מראש ל-Qdrant (מקומי, מהיר, בלי הטמעה).
─────────────────────────────────────────────────────────────────────────────
קלט (מ-embed_corpus_gpu.py): out/corpus_vectors.npy + out/corpus_meta.jsonl
פלט: אוסף Qdrant ב-data/qdrant (embedded mode — offline, מתאים ל<20K נקודות).

לכל-ספריא (150-300K): החלף ל-server mode (Docker) — אותו קוד, רק url= במקום path=.

הרצה:
    pip install qdrant-client
    python scripts/load_to_qdrant.py --in out/ --path data/qdrant
"""

import argparse
import json
from pathlib import Path

COLLECTION = "chavruta"
VECTOR_DIM = 1024          # bge-m3
INDEX_FIELDS = ["book", "commentator", "chunk_type", "verse_id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",   dest="indir", default="out")
    ap.add_argument("--path", default="data/qdrant", help="embedded mode (offline)")
    ap.add_argument("--url",  default=None, help="server mode, למשל http://localhost:6333")
    ap.add_argument("--batch", type=int, default=512)
    args = ap.parse_args()

    import numpy as np
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        VectorParams, Distance, PayloadSchemaType, PointStruct,
    )

    indir = Path(args.indir)
    vecs = np.load(indir / "corpus_vectors.npy")
    metas = [json.loads(l) for l in open(indir / "corpus_meta.jsonl", encoding="utf-8")]
    assert len(vecs) == len(metas), "אי-התאמה בין וקטורים למטא-דאטה"
    print(f"📦 {len(vecs):,} נקודות, dim={vecs.shape[1]}")

    # ── חיבור: embedded (offline) או server ───────
    client = QdrantClient(url=args.url) if args.url else QdrantClient(path=args.path)
    mode = f"server {args.url}" if args.url else f"embedded {args.path}"
    print(f"🔌 Qdrant: {mode}")

    # ── יצירת אוסף + אינדקסי payload לסינון ────────
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    for field in INDEX_FIELDS:
        client.create_payload_index(COLLECTION, field, PayloadSchemaType.KEYWORD)

    # ── upsert ב-batches ──────────────────────────
    added = 0
    for s in range(0, len(vecs), args.batch):
        pts = []
        for j in range(s, min(s + args.batch, len(vecs))):
            m = metas[j]
            md = m.get("metadata", {})
            pts.append(PointStruct(
                id=m["i"],
                vector=vecs[j].tolist(),
                payload={
                    "chunk_id":    m["id"],
                    "document":    m["document"],
                    # שדות top-level — לאינדוקס וסינון מהיר:
                    "book":        md.get("book", ""),
                    "commentator": md.get("commentator", ""),
                    "chunk_type":  md.get("chunk_type", ""),
                    "verse_id":    md.get("verse_id", ""),
                    # מטא-דאטה מלא — לבונה-הפרומפט/תצוגה:
                    "meta":        md,
                },
            ))
        client.upsert(collection_name=COLLECTION, points=pts)
        added += len(pts)
        print(f"  ⬆️  {added:,}/{len(vecs):,}", end="\r")

    print(f"\n✅ נטען. סה\"כ ב-Qdrant: {client.count(COLLECTION).count:,}")


if __name__ == "__main__":
    main()
