"""Retriever interface (contracts/retriever.md).

Turns a question into a ranked, grounded set of source chunks. Composes EmbeddingBackend +
VectorStore + optional Reranker + optional LinkExpander.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from chavruta.corpus.schema import Query


@dataclass
class RankedHit:
    chunk_id: str
    ref: str
    text: str
    score: float
    commentator_id: str | None = None
    deep_link: str = ""
    work_id: str = ""
    anchor_ref: str | None = None
    period: str | None = None      # halachic era for sources w/o a commentator (e.g. responsa)
    # Language of this chunk ('he' / 'en') — the language its retrieval text is indexed in.
    lang: str = "he"
    # The SAME passage, split by language. `text` above is the indexed blob: a "[label] Ref" header
    # line, then the Hebrew, then the English translation, all concatenated — great for embedding,
    # wrong for anything a reader sees, because a Hebrew source sheet built from it prints every
    # source twice, once in each language (reported 2026-08-11). The corpus already stores the two
    # separately; carrying them through is what lets a reader-facing surface pick one.
    text_he: str = ""
    text_en: str = ""
    # Rights of the edition this chunk's text came from — carried through so the caller can credit
    # it (CC-BY requires TASL) and so a paid tier can refuse to reproduce what it may not.
    # Empty = unknown = treat as all-rights-reserved (see corpus/rights.py).
    license: str = ""
    version_title: str = ""


@dataclass
class RetrievalResult:
    hits: list[RankedHit] = field(default_factory=list)
    anchor_refs: list[str] = field(default_factory=list)   # the primary pesukim the answer hangs on
    is_empty: bool = False                                  # True → honest "no grounded source"


@runtime_checkable
class Retriever(Protocol):
    def retrieve(self, query: Query, *, top_k: int) -> RetrievalResult: ...
