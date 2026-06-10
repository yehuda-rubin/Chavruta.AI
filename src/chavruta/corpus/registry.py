"""CorpusRegistry — adding a Work is a data/config operation (Constitution Principle III).

The registry describes every body of texts (Tanakh today; Gemara/Halacha/Emunah later) and
how to ingest it. Retrieval/ranking/generation never change when a Work is added — they read
the registry and scope by `work_id`.
"""

from __future__ import annotations

import json
from pathlib import Path

from chavruta.corpus.schema import Work


class CorpusRegistry:
    def __init__(self) -> None:
        self._works: dict[str, Work] = {}

    def register(self, work: Work) -> None:
        if work.work_id in self._works:
            # Idempotent re-register (e.g. re-running ingestion) updates metadata.
            pass
        self._works[work.work_id] = work

    def get(self, work_id: str) -> Work:
        return self._works[work_id]

    def has(self, work_id: str) -> bool:
        return work_id in self._works

    def list_ids(self) -> list[str]:
        return list(self._works.keys())

    def list_works(self) -> list[Work]:
        return list(self._works.values())

    # ── persistence (the registry is data) ──
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [vars(w) | {"languages": list(w.languages)} for w in self._works.values()]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "CorpusRegistry":
        reg = cls()
        p = Path(path)
        if not p.exists():
            return reg
        for d in json.loads(p.read_text(encoding="utf-8")):
            d["languages"] = tuple(d.get("languages", ("he", "en")))
            reg.register(Work(**d))
        return reg


# The default Tanakh work registered for the MVP.
TANAKH = Work(
    work_id="tanakh",
    title_he="תנ\"ך",
    title_en="Tanakh",
    kind="scripture",
    languages=("he", "en"),
    reference_scheme="book/chapter/verse",
    source_adapter="sefaria",
    license="CC0 / Sefaria",
    attribution="Sefaria (sefaria.org)",
)


def default_registry() -> CorpusRegistry:
    reg = CorpusRegistry()
    reg.register(TANAKH)
    return reg
