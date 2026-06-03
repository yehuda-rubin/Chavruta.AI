# -*- coding: utf-8 -*-
"""
vector_store.py — שכבת אחסון וקטורי אגנוסטית לפריסה (Decision D5).
─────────────────────────────────────────────────────────────────────────────
ממשק אחיד search(vector, k, chunk_type) מעל Qdrant, בשני מצבים נבחרים דרך env:

  • embedded (ברירת מחדל) — בתוך-תהליך, OFFLINE. מתאים ל<20K נקודות (תורה).
  • server                — Qdrant ב-Docker. לכל-ספריא (150-300K).

env:
  VECTOR_BACKEND = qdrant                 (כרגע היחיד)
  QDRANT_URL     = http://localhost:6333  → server mode (אם מוגדר)
  QDRANT_PATH    = data/qdrant            → embedded mode (ברירת מחדל)
  QDRANT_COLLECTION = chavruta

הוקטור של השאלה מחושב ע"י הקורא (rag_pipeline, bge-m3 על CPU) ומועבר ל-search.
"""

from __future__ import annotations
import os
from pathlib import Path

_DEFAULT_PATH = str(Path(__file__).resolve().parent.parent / "data" / "qdrant")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "chavruta")


class QdrantStore:
    def __init__(self, collection: str = COLLECTION,
                 path: str | None = None, url: str | None = None):
        from qdrant_client import QdrantClient
        self.collection = collection
        self.client = QdrantClient(url=url) if url else QdrantClient(path=path)
        self.mode = f"server {url}" if url else f"embedded {path}"

    def count(self) -> int:
        return self.client.count(self.collection).count

    def search(self, vector: list[float], k: int,
               chunk_type: str | None = None,
               commentator: str | None = None) -> list[dict]:
        """
        מחזיר רשימת {meta, document, similarity, distance}.
        סינון אופציונלי לפי chunk_type (pasuk/commentary) ו/או commentator.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        conds = []
        if chunk_type:
            conds.append(FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type)))
        if commentator:
            conds.append(FieldCondition(key="commentator", match=MatchValue(value=commentator)))
        flt = Filter(must=conds) if conds else None

        hits = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=flt,
            limit=k,
            with_payload=True,
        ).points

        out = []
        for h in hits:
            p = h.payload or {}
            sim = float(h.score)                 # COSINE: גבוה = דומה יותר
            out.append({
                "meta":       p.get("meta", {}),
                "document":   p.get("document", ""),
                "similarity": round(sim, 4),
                "distance":   round(1.0 - sim, 4),
            })
        return out


def get_store():
    """בוחר backend לפי env. כרגע Qdrant (embedded/server)."""
    backend = os.environ.get("VECTOR_BACKEND", "qdrant").lower()
    if backend != "qdrant":
        raise ValueError(f"VECTOR_BACKEND לא נתמך: {backend!r} (כרגע: qdrant)")
    url = os.environ.get("QDRANT_URL") or None
    path = None if url else os.environ.get("QDRANT_PATH", _DEFAULT_PATH)
    return QdrantStore(path=path, url=url)


if __name__ == "__main__":
    store = get_store()
    print("mode:", store.mode, "| count:", store.count())
