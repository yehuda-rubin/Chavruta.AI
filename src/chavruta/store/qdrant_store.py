"""QdrantStore — deployment-agnostic vector store (research D4).

Embedded mode (local path) and server mode (URL) behind one interface, chosen by config
(Principle II). Named vectors: `dense` (cosine) + `sparse` (lexical) enable hybrid search
fused server-side via RRF. Upsert is idempotent by `chunk_id` (mapped to a deterministic
UUID point id). qdrant-client is imported lazily so the module imports without it installed.
"""

from __future__ import annotations

import uuid
from typing import Optional

from chavruta.store.base import Filter, Hit, HybridQuery, StoredChunk

_NAMESPACE = uuid.UUID("c4a5f0de-0000-4000-8000-000000000001")  # stable, for chunk_id → point id


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


class QdrantStore:
    def __init__(self, mode: str = "embedded", path: str = "", url: str = "",
                 api_key: str = ""):
        self.mode = mode
        self.path = path
        self.url = url
        self.api_key = api_key
        self._client = None  # lazy

    def _client_(self):
        if self._client is None:
            from qdrant_client import QdrantClient  # heavy; lazy

            if self.mode == "server":
                kwargs = {"url": self.url, "timeout": 300}
                if self.api_key:
                    kwargs["api_key"] = self.api_key
                self._client = QdrantClient(**kwargs)
            else:
                self._client = QdrantClient(path=self.path)
        return self._client

    def ensure_collection(self, name: str, dim: int) -> None:
        from qdrant_client import models

        client = self._client_()
        if client.collection_exists(name):
            return
        client.create_collection(
            collection_name=name,
            vectors_config={"dense": models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )

    def upsert(self, name: str, chunks: list[StoredChunk]) -> None:
        from qdrant_client import models

        if not chunks:
            return
        points = []
        for c in chunks:
            vector = {"dense": c.dense}
            if c.sparse:
                idx = list(c.sparse.keys())
                vals = [c.sparse[i] for i in idx]
                vector["sparse"] = models.SparseVector(indices=idx, values=vals)
            points.append(
                models.PointStruct(id=_point_id(c.chunk_id), vector=vector, payload=c.payload)
            )
        self._client_().upsert(collection_name=name, points=points)

    def _build_filter(self, filters: Optional[Filter]):
        if not filters:
            return None
        from qdrant_client import models

        must = []
        for key, value in filters.items():
            if isinstance(value, dict) and "$text" in value:
                # Full-text (tokenised) match against a text-indexed payload field — every
                # token must be present (AND). Used for nikud/ktiv-insensitive lexical lookup.
                must.append(models.FieldCondition(key=key, match=models.MatchText(text=value["$text"])))
            elif isinstance(value, (list, tuple)):
                must.append(models.FieldCondition(key=key, match=models.MatchAny(any=list(value))))
            else:
                must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        return models.Filter(must=must)

    def ensure_text_index(self, name: str, field: str = "search_he") -> None:
        """Create a full-text payload index on `field` (idempotent) so MatchText works.

        Word tokeniser, lowercased, min token length 1 (Hebrew has 2-letter words). The
        indexed field holds the nikud/ktiv-normalised search form (see corpus.normalize).
        """
        from qdrant_client import models

        try:
            self._client_().create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=models.TextIndexParams(
                    type=models.TextIndexType.TEXT,
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=1,
                    lowercase=True,
                ),
            )
        except Exception:
            pass  # already exists / index in place

    def search(
        self, name: str, query: HybridQuery, top_k: int, filters: Optional[Filter] = None
    ) -> list[Hit]:
        from qdrant_client import models

        qfilter = self._build_filter(filters)
        if query.sparse:
            # Hybrid: prefetch dense + sparse candidates, fuse with RRF server-side.
            idx = list(query.sparse.keys())
            vals = [query.sparse[i] for i in idx]
            prefetch = [
                models.Prefetch(query=query.dense, using="dense", limit=top_k * 4, filter=qfilter),
                models.Prefetch(
                    query=models.SparseVector(indices=idx, values=vals),
                    using="sparse", limit=top_k * 4, filter=qfilter,
                ),
            ]
            res = self._client_().query_points(
                collection_name=name,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )
        else:
            res = self._client_().query_points(
                collection_name=name,
                query=query.dense,
                using="dense",
                limit=top_k,
                query_filter=qfilter,
                with_payload=True,
            )
        return [
            Hit(chunk_id=(p.payload or {}).get("chunk_id", str(p.id)), score=p.score, payload=p.payload or {})
            for p in res.points
        ]

    def count(self, name: str, filters: Optional[Filter] = None) -> int:
        res = self._client_().count(
            collection_name=name, count_filter=self._build_filter(filters), exact=True
        )
        return res.count

    def delete(self, name: str, filters: Filter) -> None:
        from qdrant_client import models

        self._client_().delete(
            collection_name=name,
            points_selector=models.FilterSelector(filter=self._build_filter(filters)),
        )

    def fetch_by_refs(
        self, name: str, refs: list[str], filters: Optional[Filter] = None
    ) -> list[Hit]:
        """Non-vector lookup: chunks whose `ref` OR `anchor_ref` is in `refs`.

        Returns the verses plus everything anchored on them (commentaries) — used by
        link-based retrieval and named-ref anchoring. Uses scroll + filter.
        """
        from qdrant_client import models

        if not refs:
            return []
        base = self._build_filter(filters)
        ref_or_anchor = models.Filter(should=[
            models.FieldCondition(key="ref", match=models.MatchAny(any=list(refs))),
            models.FieldCondition(key="anchor_ref", match=models.MatchAny(any=list(refs))),
        ])
        combined = models.Filter(
            must=([*base.must, ref_or_anchor] if base else [ref_or_anchor])
        )
        points, _ = self._client_().scroll(
            collection_name=name,
            scroll_filter=combined,
            limit=max(len(refs) * 16, 64),
            with_payload=True,
        )
        return [
            Hit(chunk_id=(p.payload or {}).get("chunk_id", str(p.id)), score=1.0, payload=p.payload or {})
            for p in points
        ]
