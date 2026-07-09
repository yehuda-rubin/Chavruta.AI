# -*- coding: utf-8 -*-
"""index_templates.py — build the TEMPLATE RAG (NO LLM API).

Embeds each lesson-template's manifest (title + description + when_to_use + keywords) with
bge-m3 and upserts it into a dedicated Qdrant collection ('chavruta_templates'). At lesson
time, retrieve_template.py queries this collection to pick the template set that best fits the
requested topic — the "which template?" retrieval layer that complements the "which sources?"
layer (retrieve_sources.py). Each template = a folder with 3 files (source_sheet, lesson_flow,
full_lesson) + manifest.yaml.

    docker compose up -d qdrant
    .venv/Scripts/python.exe scripts/index_templates.py        # (re)build the template index
"""

from __future__ import annotations

import torch  # noqa: F401 — MUST be first (native DLL load order; see verify_retrieval.py)
import os
import sys
import uuid
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
QDRANT_URL = os.environ["CHAVRUTA_QDRANT_URL"]
COLLECTION = os.environ.get("CHAVRUTA_TEMPLATES_COLLECTION", "chavruta_templates")
TEMPLATES_DIR = REPO / "lessons" / "templates"
_NS = uuid.UUID("c4a5f0de-7e11-4000-8000-000000000abc")  # stable id namespace for templates

DIM = 1024


def _manifest_text(m: dict) -> str:
    """The text that gets embedded — what the template IS and WHEN to use it.

    Includes example topics AND example query phrasings so real user questions ("האם מותר…",
    "מצוות … בחג") land on the right template even when genres overlap semantically.
    """
    kw = ", ".join(m.get("keywords", []))
    topics = ", ".join(m.get("example_topics", []))
    queries = " ".join(m.get("example_queries", []))
    return (
        f"{m.get('title','')}. {m.get('description','').strip()} "
        f"מתי להשתמש: {m.get('when_to_use','').strip()} "
        f"שאלות לדוגמה: {queries} "
        f"נושאים לדוגמה: {topics}. "
        f"מבנה: {m.get('structure','')}. מילות מפתח: {kw}"
    )


def main() -> None:
    from chavruta.embedding.bge_m3 import BgeM3Embedding  # loads model (FlagEmbedding) first
    emb = BgeM3Embedding(use_sparse=False)  # dense-only is enough for coarse template matching
    emb.embed_query("warmup")

    from qdrant_client import QdrantClient, models
    client = QdrantClient(url=QDRANT_URL, timeout=120)

    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE),
        )
        print(f"created collection '{COLLECTION}'")

    manifests = sorted(TEMPLATES_DIR.glob("*/manifest.yaml"))
    if not manifests:
        print(f"no manifests found under {TEMPLATES_DIR}")
        return

    points = []
    for mp in manifests:
        m = yaml.safe_load(mp.read_text(encoding="utf-8"))
        tid = m.get("id") or mp.parent.name
        e = emb.embed_query(_manifest_text(m))
        payload = {
            "id": tid,
            "title": m.get("title", ""),
            "genre": m.get("genre", ""),
            "description": m.get("description", "").strip(),
            "when_to_use": m.get("when_to_use", "").strip(),
            "keywords": m.get("keywords", []),
            "structure": m.get("structure", ""),
            "dir": str(mp.parent.relative_to(REPO)).replace("\\", "/"),
            "files": m.get("files", {}),
            "example_topics": m.get("example_topics", []),
        }
        points.append(models.PointStruct(id=str(uuid.uuid5(_NS, tid)), vector=e.dense, payload=payload))
        print(f"  indexed template: {tid:12s} ({m.get('genre','')})")

    client.upsert(collection_name=COLLECTION, points=points)
    total = client.count(COLLECTION, exact=True).count
    print(f"\n✅ template RAG '{COLLECTION}' now has {total} templates")


if __name__ == "__main__":
    main()
