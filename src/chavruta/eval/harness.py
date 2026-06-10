"""Evaluation harness (task T029, Constitution Principle V) — trust is measured, not felt.

Scores two layers over a versioned JSONL dataset of EvaluationItems:
  • retrieval@K — did an expected source appear in the retriever's top-K?
  • grounding   — does the answer carry citations that resolve to retrieved chunks,
                  and does the no-source path stay honest (never fabricate)?

The report is deterministic and comparable across runs (SC-008): a change that lowers the
score is detectable before acceptance. The same harness runs under both profiles (SC-006).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from chavruta.corpus.schema import Intent, Query


@dataclass
class EvaluationItem:
    qid: str
    question: str
    lang: str
    expected_refs: list[str] = field(default_factory=list)   # empty ⇒ expect honest no-source
    intent: str = "qa"
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "EvaluationItem":
        return cls(
            qid=d["qid"], question=d["question"], lang=d.get("lang", "he"),
            expected_refs=d.get("expected_refs", []), intent=d.get("intent", "qa"),
            note=d.get("note", ""),
        )


def load_dataset(path: str | Path) -> list[EvaluationItem]:
    items = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(EvaluationItem.from_dict(json.loads(line)))
    return items


def _ref_matches(expected: str, got: str) -> bool:
    """Segment-wise ref comparison: exact, or one is a structural prefix of the other.

    'Genesis.1' matches 'Genesis.1.3' (chapter-level), but 'Genesis.1.1' does NOT match
    'Genesis.1.10' (no false positives on string prefixes).
    """
    e = expected.strip().lower().replace(" ", ".").split(".")
    g = got.strip().lower().replace(" ", ".").split(".")
    n = min(len(e), len(g))
    return n > 0 and e[:n] == g[:n]


@dataclass
class EvalReport:
    dataset: str
    profile: str
    top_k: int
    n_items: int = 0
    retrieval_hits: int = 0          # items where ≥1 expected ref appeared in top-K
    grounded_ok: int = 0             # answerable items whose answer carried valid citations
    no_source_honest: int = 0        # unanswerable items honestly reported (SC-002)
    n_answerable: int = 0
    n_unanswerable: int = 0
    failures: list[dict] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def retrieval_at_k(self) -> float:
        return self.retrieval_hits / self.n_answerable if self.n_answerable else 0.0

    @property
    def grounding_rate(self) -> float:
        return self.grounded_ok / self.n_answerable if self.n_answerable else 0.0

    @property
    def honesty_rate(self) -> float:
        return self.no_source_honest / self.n_unanswerable if self.n_unanswerable else 1.0

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset, "profile": self.profile, "top_k": self.top_k,
            "n_items": self.n_items,
            "retrieval_at_k": round(self.retrieval_at_k, 4),
            "grounding_rate": round(self.grounding_rate, 4),
            "honesty_rate": round(self.honesty_rate, 4),
            "n_answerable": self.n_answerable, "n_unanswerable": self.n_unanswerable,
            "seconds": round(self.seconds, 1),
            "failures": self.failures,
        }


def evaluate(pipeline, items: list[EvaluationItem], *, dataset_name: str = "",
             retrieval_only: bool = False) -> EvalReport:
    """Run the harness. `retrieval_only=True` skips generation (fast, LLM-free gate)."""
    profile = pipeline.profile
    report = EvalReport(dataset=dataset_name, profile=profile.name, top_k=profile.top_k)
    started = time.time()

    for item in items:
        report.n_items += 1
        query = Query(text=item.question, lang=item.lang, intent=Intent(item.intent))
        if pipeline.router is not None:
            query = pipeline.router.route(query)
        result = pipeline.retriever.retrieve(query, top_k=profile.top_k)

        if item.expected_refs:
            report.n_answerable += 1
            got_refs = [h.ref for h in result.hits] + (result.anchor_refs or [])
            hit = any(_ref_matches(e, g) for e in item.expected_refs for g in got_refs)
            if hit:
                report.retrieval_hits += 1
            else:
                report.failures.append({"qid": item.qid, "kind": "retrieval",
                                        "expected": item.expected_refs, "got": got_refs[:8]})

            if retrieval_only:
                if hit:
                    report.grounded_ok += 1   # retrieval-only proxy
            else:
                answer = pipeline.ask(Query(text=item.question, lang=item.lang,
                                            intent=Intent(item.intent)))
                if answer.grounded and answer.citations:
                    report.grounded_ok += 1
                else:
                    report.failures.append({"qid": item.qid, "kind": "grounding",
                                            "grounded": answer.grounded,
                                            "n_citations": len(answer.citations)})
        else:
            # Unanswerable by design — the honest path must hold (never fabricate).
            report.n_unanswerable += 1
            if result.is_empty:
                report.no_source_honest += 1
            elif not retrieval_only:
                answer = pipeline.ask(Query(text=item.question, lang=item.lang))
                if answer.no_source:
                    report.no_source_honest += 1
                else:
                    report.failures.append({"qid": item.qid, "kind": "honesty",
                                            "got_refs": [h.ref for h in result.hits][:5]})
            else:
                report.failures.append({"qid": item.qid, "kind": "honesty",
                                        "got_refs": [h.ref for h in result.hits][:5]})

    report.seconds = time.time() - started
    return report
