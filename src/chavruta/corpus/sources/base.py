"""SourceAdapter — pluggable per-source ingestion (Principle III).

A new corpus is brought in by implementing this interface (or reusing the Sefaria adapter)
and registering a Work — no change to retrieval/generation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from chavruta.corpus.schema import Chunk, Link, Work


@runtime_checkable
class SourceAdapter(Protocol):
    def fetch_chunks(self, work: Work, refs: Iterable[str] | None = None) -> Iterable[Chunk]: ...

    def fetch_links(self, work: Work, refs: Iterable[str] | None = None) -> Iterable[Link]: ...
