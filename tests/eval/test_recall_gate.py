"""Regression gate (Phase 6, spec 002): the router must resolve the expected refs for the
labelled indirect/analytical question set. Deterministic — no Qdrant, no LLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chavruta.corpus.schema import Query
from chavruta.intents.router import Router

DATA = Path(__file__).parent / "indirect_questions.jsonl"
ROWS = [json.loads(ln) for ln in DATA.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.mark.parametrize("row", ROWS, ids=[r["note"] for r in ROWS])
def test_router_resolves_expected_refs(row):
    refs = set(Router().route(Query(text=row["q"])).named_refs or [])
    missing = set(row["expect"]) - refs
    assert not missing, f"{row['q']!r}: missing {sorted(missing)}; got {sorted(refs)}"
