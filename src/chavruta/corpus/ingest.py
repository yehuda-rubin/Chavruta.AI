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

def _slug(name: str) -> str:
    """'Ibn Ezra' → 'ibn_ezra', 'Or HaChaim' → 'or_hachaim' — matches router ids."""
    import re

    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def payload_from_legacy_meta(meta: dict, work_id: str = "tanakh") -> dict:
    """Map a legacy `corpus_meta.jsonl` record to the new Chunk payload schema."""
    md = meta.get("metadata", {})
    commentator_raw = md.get("commentator", "")
    commentator = _slug(commentator_raw) if commentator_raw else None
    chunk_type = md.get("chunk_type", "")
    is_commentary = bool(commentator) or chunk_type == "commentary"
    verse_id = md.get("verse_id", "") or md.get("ref", "") or meta.get("id", "")
    # commentary gets its own ref ("Rashi on Genesis.1.1"); pasuk keeps the verse ref
    ref = f"{commentator_raw} on {verse_id}" if is_commentary and commentator_raw else verse_id
    document = meta.get("document", "")
    # work_id override: Mishnah chunks carry work="mishnah" in metadata
    effective_work_id = md.get("work", work_id)
    position = {k: md.get(k) for k in ("book", "chapter", "verse") if k in md}
    # Mishnah-specific extra coords (seder, tractate) stored alongside standard keys
    for k in ("seder", "tractate"):
        if k in md:
            position[k] = md[k]
    chunk = Chunk(
        chunk_id=meta.get("id", ref),
        work_id=effective_work_id,
        unit_type=UnitType.COMMENTARY if is_commentary else UnitType.SOURCE,
        ref=ref,
        lang="he",
        text=document,
        text_he=md.get("text_he", "") or document,
        text_en=md.get("text_en", ""),
        deep_link=f"https://www.sefaria.org/{verse_id}" if verse_id else "",
        period=md.get("period", ""),   # responsa carry their halachic era (geonim/rishonim/…)
        position=position,
        anchor_ref=verse_id if is_commentary else None,
        anchor_kind=AnchorKind.SOURCE if is_commentary else None,
        commentator_id=commentator,
    )
    return chunk.to_payload()


def load_processed_chunks(out_dir: str | Path) -> Iterator[StoredChunk]:
    """Yield StoredChunks from an `out/` dir produced by embed_corpus_gpu.py.

    Picks up `corpus_sparse.jsonl` automatically when present (full hybrid, D5);
    otherwise yields dense-only chunks (the fallback mode for legacy vectors).
    """
    import numpy as np  # lazy

    out = Path(out_dir)
    # mmap the vectors instead of loading all ~GBs into RAM — the big index files (e.g. gemara,
    # 711k×1024) otherwise thrash a 16GB box that is also running Qdrant. Rows are paged in on
    # demand as each chunk is yielded.
    vecs = np.load(out / "corpus_vectors.npy", mmap_mode="r")

    # Stream sparse in lockstep with meta instead of pre-building a dict of all N rows — for
    # gemara (711k) that dict is several GB. corpus_sparse.jsonl and corpus_meta.jsonl are written
    # in the same index order by the embed step, so positional zip is exact.
    sparse_path = out / "corpus_sparse.jsonl"
    sparse_f = sparse_path.open(encoding="utf-8") if sparse_path.exists() else None
    meta_f = (out / "corpus_meta.jsonl").open(encoding="utf-8")
    try:
        for j, line in enumerate(meta_f):
            meta = json.loads(line)
            payload = payload_from_legacy_meta(meta)
            sparse: dict[int, float] = {}
            if sparse_f is not None:
                s_line = sparse_f.readline()
                if s_line:
                    d = json.loads(s_line)
                    sparse = {int(t): float(w) for t, w in d["sparse"].items()}
            yield StoredChunk(
                chunk_id=payload["chunk_id"],
                dense=[float(x) for x in vecs[j]],
                sparse=sparse,
                payload=payload,
            )
    finally:
        meta_f.close()
        if sparse_f is not None:
            sparse_f.close()
