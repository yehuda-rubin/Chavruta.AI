# -*- coding: utf-8 -*-
"""Query-understanding recall gate (Phase 6, spec 002).

Runs the router over a labelled set of indirect/analytical questions and checks that
every EXPECTED ref is resolved into `named_refs`. Deterministic and offline (no Qdrant,
no LLM) — it measures the query-understanding layer, the part this feature added.

    python scripts/eval_recall.py            # prints recall, exits non-zero below the gate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.corpus.schema import Query
from chavruta.intents.router import Router

DATA = Path(__file__).resolve().parents[1] / "tests" / "eval" / "indirect_questions.jsonl"
GATE = 0.9


def evaluate() -> tuple[int, int, list[tuple]]:
    router = Router()
    rows = [json.loads(ln) for ln in DATA.read_text(encoding="utf-8").splitlines() if ln.strip()]
    passed, fails = 0, []
    for r in rows:
        refs = set(Router.route(router, Query(text=r["q"])).named_refs or [])
        expected = set(r["expect"])
        if expected <= refs:
            passed += 1
        else:
            fails.append((r["q"], sorted(expected), sorted(refs)))
    return passed, len(rows), fails


def main() -> int:
    passed, total, fails = evaluate()
    for q, exp, got in fails:
        print(f"FAIL: {q}\n      expected ⊆ {exp}\n      got        {got}")
    rate = passed / total if total else 0.0
    print(f"recall@router: {passed}/{total} = {rate:.0%}  (gate {GATE:.0%})")
    return 0 if rate >= GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
