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
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from chavruta.corpus.schema import Intent, Query, Turn
from chavruta.generation.grounded import unverified_quotes


def _turns(item: EvaluationItem) -> list[Turn]:
    """The item's prior turns as the pipeline's own Turn objects (user side only — what a follow-up
    is following up ON is the user's previous question)."""
    return [Turn(role="user", text=t) for t in (item.history or []) if (t or "").strip()]


@dataclass
class EvaluationItem:
    qid: str
    question: str
    lang: str
    expected_refs: list[str] = field(default_factory=list)   # empty ⇒ expect honest no-source
    intent: str = "qa"
    note: str = ""
    # Prior user turns, oldest first. A follow-up ("תנסה", "ולמה?") means nothing on its own — it
    # only retrieves correctly when the conversation is carried into the search text
    # (pipeline.py::_anchor_followup). Without this field that whole class of failure — the one a
    # real user hit on 2026-08-11 — could not be written down as an eval case at all.
    history: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> EvaluationItem:
        return cls(
            qid=d["qid"], question=d["question"], lang=d.get("lang", "he"),
            expected_refs=d.get("expected_refs", []), intent=d.get("intent", "qa"),
            note=d.get("note", ""), history=d.get("history", []),
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
    # Separator-agnostic: space / underscore / dot / colon / comma all denote a segment boundary, so a
    # space-form expected ref ('Bava Metzia') matches the commercial corpus's underscore form
    # ('Bava_Metzia.3.1') and vice-versa. Without this, cross-format refs silently never match.
    e = [s for s in re.split(r"[ _.:,]+", expected.strip().lower()) if s]
    g = [s for s in re.split(r"[ _.:,]+", got.strip().lower()) if s]
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
    fabricated_quotes: int = 0       # answers quoting text found in no retrieved source
    n_quote_checked: int = 0         # answers the quote check actually ran on (generation only)
    expected_found: int = 0          # expected refs that DID surface, summed over items
    expected_total: int = 0          # expected refs asked for, summed over items
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

    @property
    def source_coverage(self) -> float:
        """Of every source an item expected, what share actually surfaced.

        `retrieval_at_k` answers "did we find something?" and saturates at 1.0 while half the
        relevant material is still missing; this answers "did we find it ALL?". The two diverging is
        the signature of a system whose answers are accurate but under-sourced.
        """
        return self.expected_found / self.expected_total if self.expected_total else 0.0

    @property
    def quote_faithfulness(self) -> float:
        """Share of generated answers whose every verbatim quote was found in a retrieved source.
        1.0 when nothing was checked (retrieval-only runs), so it never reads as a failure."""
        if not self.n_quote_checked:
            return 1.0
        return (self.n_quote_checked - self.fabricated_quotes) / self.n_quote_checked

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset, "profile": self.profile, "top_k": self.top_k,
            "n_items": self.n_items,
            "retrieval_at_k": round(self.retrieval_at_k, 4),
            "source_coverage": round(self.source_coverage, 4),
            "grounding_rate": round(self.grounding_rate, 4),
            "honesty_rate": round(self.honesty_rate, 4),
            "quote_faithfulness": round(self.quote_faithfulness, 4),
            "n_answerable": self.n_answerable, "n_unanswerable": self.n_unanswerable,
            "fabricated_quotes": self.fabricated_quotes,
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
        turns = _turns(item)
        query = Query(text=item.question, lang=item.lang, intent=Intent(item.intent))
        if pipeline.router is not None:
            query = pipeline.router.route(query)
        # Same anchoring the live path applies, so a follow-up item is retrieved the way a real
        # follow-up is rather than as a bare, topicless phrase.
        anchor = getattr(pipeline, "_anchor_followup", None)
        if turns and anchor is not None:
            query = anchor(query, turns)
        result = pipeline.retriever.retrieve(query, top_k=profile.top_k)

        if item.expected_refs:
            report.n_answerable += 1
            got_refs = [h.ref for h in result.hits] + (result.anchor_refs or [])
            # In generation mode, count what the ANSWER actually rested on, not only round one.
            # Most sources now arrive through the agentic loop, which runs during generation — so
            # scoring `result.hits` alone measures the first retrieval attempt and calls the loop's
            # work a miss. That is why the full run reproduced the retrieval-only numbers to the
            # decimal: the instrument could not see the mechanism under test.
            answer = None
            if not retrieval_only:
                answer = pipeline.ask(Query(text=item.question, lang=item.lang,
                                            intent=Intent(item.intent)), history=turns)
                got_refs = got_refs + [c.ref for c in (answer.citations or [])]
            found = [e for e in item.expected_refs if any(_ref_matches(e, g) for g in got_refs)]
            hit = bool(found)
            if hit:
                report.retrieval_hits += 1
            else:
                report.failures.append({"qid": item.qid, "kind": "retrieval",
                                        "expected": item.expected_refs, "got": got_refs[:8]})
            # COVERAGE, as distinct from the hit above: retrieval_at_k asks "did anything expected
            # show up?", which an item listing five sources passes on the strength of one. That
            # hides the failure mode the answers actually have once they're accurate — the sources
            # that were relevant and simply never came (observed by the operator 2026-08-11:
            # "the answers are near-perfect; what may still be missing is all the related sources").
            report.expected_total += len(item.expected_refs)
            report.expected_found += len(found)
            missing = [e for e in item.expected_refs if e not in found]
            if missing and hit:      # a partial hit — invisible in retrieval_at_k by construction
                report.failures.append({"qid": item.qid, "kind": "coverage",
                                        "missing": missing, "found": found})

            if retrieval_only:
                if hit:
                    report.grounded_ok += 1   # retrieval-only proxy
            else:
                if answer.grounded and answer.citations:
                    report.grounded_ok += 1
                else:
                    report.failures.append({"qid": item.qid, "kind": "grounding",
                                            "grounded": answer.grounded,
                                            "n_citations": len(answer.citations)})
                # Citation FAITHFULNESS, separate from citation presence: a quoted line that appears
                # in no retrieved source is the failure grounding-rate cannot see, because such an
                # answer still carries valid [S#] markers and counts as grounded.
                #
                # Check against the answer's CITATIONS as well as the first-round hits. Most sources
                # now arrive through the agentic loop, and they are absent from `result.hits` — so
                # checking those alone flags faithful quotes from correctly-fetched sources as
                # fabricated. Measured: this reported "quote fidelity 16.7%" on a shard whose
                # flagged lines included text verbatim from B'Mareh HaBazak VII.29.17. pipeline.py
                # already carries this exact warning for the live path; the harness repeated the bug.
                report.n_quote_checked += 1
                bad = unverified_quotes(answer.text, list(result.hits) + list(answer.citations or []))
                if bad:
                    report.fabricated_quotes += 1
                    report.failures.append({"qid": item.qid, "kind": "quote",
                                            "unverified": bad[:2]})
        else:
            # Unanswerable by design — the honest path must hold (never fabricate).
            report.n_unanswerable += 1
            registry = getattr(pipeline, "registry", None)
            asks_unloaded_work = bool(
                registry is not None and query.requested_works
                and not any(registry.has(w) for w in query.requested_works)
            )
            if asks_unloaded_work or result.is_empty:
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
