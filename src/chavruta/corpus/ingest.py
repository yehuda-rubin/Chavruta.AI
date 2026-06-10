"""Ingestion — fetch → normalize → chunk → (embed) → upsert (research D8) — task T015.

Two paths:
  • `ingest_work`: the forward path — pull a new Work from its SourceAdapter, embed, and
    upsert (+ capture its Links / anchor chains). Adding a corpus is pure data/config.
  • `load_processed_chunks` / `payload_from_legacy_meta`: the reuse path — map the already
    fetched+embedded Tanakh corpus (`out/corpus_meta.jsonl` + `corpus_vectors.npy`, dense
    only) into the store without re-embedding (used by scripts/load_to_store.py, T020).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from chavruta.corpus.links import LinkGraph
from chavruta.corpus.schema import AnchorKind, Chunk, UnitType, Work
from chavruta.store.base import StoredChunk


def ingest_work(
    work: Work,
    adapter,
    refs: Iterable[str],
    embedding,
    store,
    *,
    link_graph: LinkGraph | None = None,
    collection: str,
    batch_size: int = 64,
) -> int:
    """Fetch, embed (dense+sparse), and upsert a Work incrementally. Returns chunk count."""
    store.ensure_collection(collection, embedding.dim)
    refs = list(refs)
    total = 0
    batch: list[Chunk] = []

    def flush(chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        for c in chunks:
            c.validate()
        embeddings = embedding.embed_batch([c.text for c in chunks])
        stored = [
            StoredChunk(chunk_id=c.chunk_id, dense=e.dense, sparse=e.sparse, payload=c.to_payload())
            for c, e in zip(chunks, embeddings)
        ]
        store.upsert(collection, stored)
        return len(stored)

    for chunk in adapter.fetch_chunks(work, refs):
        batch.append(chunk)
        if len(batch) >= batch_size:
            total += flush(batch)
            batch = []
    total += flush(batch)

    if link_graph is not None:
        for link in adapter.fetch_links(work, refs):
            link_graph.add(link)
        # record anchor chains for any commentary chunks
        for chunk in adapter.fetch_chunks(work, refs):
            if chunk.unit_type is UnitType.COMMENTARY and chunk.anchor_ref:
                link_graph.add_anchor(chunk.ref, chunk.anchor_ref, chunk.work_id, work.work_id)

    return total


# ── Reuse path: map the legacy embedded corpus into the new schema ──

def payload_from_legacy_meta(meta: dict, work_id: str = "tanakh") -> dict:
    """Map a legacy `corpus_meta.jsonl` record to the new Chunk payload schema."""
    md = meta.get("metadata", {})
    commentator = md.get("commentator", "") or None
    chunk_type = md.get("chunk_type", "")
    is_commentary = bool(commentator) or chunk_type == "commentary"
    ref = md.get("verse_id", "") or md.get("ref", "") or meta.get("id", "")
    document = meta.get("document", "")
    chunk = Chunk(
        chunk_id=meta.get("id", ref),
        work_id=work_id,
        unit_type=UnitType.COMMENTARY if is_commentary else UnitType.SOURCE,
        ref=ref,
        lang="he",
        text=document,
        text_he=document,
        deep_link=f"https://www.sefaria.org/{ref.replace(' ', '.')}" if ref else "",
        position={k: md.get(k) for k in ("book", "chapter", "verse") if k in md},
        anchor_ref=md.get("verse_id") if is_commentary else None,
        anchor_kind=AnchorKind.SOURCE if is_commentary else None,
        commentator_id=commentator,
    )
    return chunk.to_payload()


def load_processed_chunks(out_dir: str | Path) -> Iterator[StoredChunk]:
    """Yield StoredChunks from a legacy `out/` dir (dense-only; sparse added on re-embed)."""
    import numpy as np  # lazy

    out = Path(out_dir)
    vecs = np.load(out / "corpus_vectors.npy")
    with (out / "corpus_meta.jsonl").open(encoding="utf-8") as f:
        for j, line in enumerate(f):
            meta = json.loads(line)
            payload = payload_from_legacy_meta(meta)
            yield StoredChunk(
                chunk_id=payload["chunk_id"],
                dense=[float(x) for x in vecs[j]],
                sparse={},                         # legacy vectors are dense-only (D5 fallback)
                payload=payload,
            )
