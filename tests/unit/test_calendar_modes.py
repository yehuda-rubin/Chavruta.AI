"""Parshat HaShavua / Daf Yomi: the beta allowlist gate and the calendar-cache bucket key.

_run_parsha/_run_daf_yomi's happy path needs a real pipeline (Qdrant + LLM) and is exercised
manually against the live corpus (see the feature's rollout notes); what's unit-testable in
isolation is the gate itself (an unlisted owner must never reach the pipeline at all) and the
cache-key logic.
"""

from __future__ import annotations

from datetime import date

import app.api as api
import chavruta.calendar.sefaria_calendar as cal
import pytest
from chavruta.retrieval.base import RankedHit


def _hit(cid, comm=None):
    return RankedHit(chunk_id=cid, ref=cid, text=f"text of {cid}", score=1.0, commentator_id=comm)


def test_calendar_modes_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_CALENDAR_BETA_OWNERS", raising=False)
    assert api._calendar_modes_enabled("anyone") is False
    assert api._calendar_modes_enabled("local") is False


def test_calendar_modes_enabled_only_for_listed_owners(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CALENDAR_BETA_OWNERS", "owner-a, owner-b")
    assert api._calendar_modes_enabled("owner-a") is True
    assert api._calendar_modes_enabled("owner-b") is True
    assert api._calendar_modes_enabled("owner-c") is False


def test_calendar_modes_wildcard_enables_everyone(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CALENDAR_BETA_OWNERS", "*")
    assert api._calendar_modes_enabled("anyone") is True
    assert api._calendar_modes_enabled("local") is True


@pytest.mark.parametrize("intent_str", ["parsha", "dafyomi"])
def test_unlisted_owner_gets_a_friendly_message_not_the_pipeline(monkeypatch, intent_str):
    """The gate must short-circuit BEFORE touching _get_pipeline()/_run_parsha/_run_daf_yomi —
    an unlisted owner's request must never reach the (real, heavy) generation path at all."""
    monkeypatch.delenv("CHAVRUTA_CALENDAR_BETA_OWNERS", raising=False)

    def _boom():
        raise AssertionError("pipeline must not be touched for a gated-out owner")

    monkeypatch.setattr(api, "_get_pipeline", _boom)
    monkeypatch.setattr(api, "_run_parsha", lambda *a, **k: _boom())
    monkeypatch.setattr(api, "_run_daf_yomi", lambda *a, **k: _boom())

    res = api._run_query_impl("שאלה", "he", intent_str, [], owner_id="not-listed")
    assert res.grounded is False
    assert res.intent == intent_str
    assert res.answer  # a friendly message, not empty and not a raised exception


def test_listed_owner_reaches_the_calendar_path(monkeypatch):
    """The inverse check: a listed owner's request DOES reach _run_parsha, not the gate message."""
    monkeypatch.setenv("CHAVRUTA_CALENDAR_BETA_OWNERS", "owner-a")
    called = {}

    def _fake_run_parsha(question, lang, history=None, owner_id="local", llm=None):
        called["question"] = question
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent="parsha", files=[])

    monkeypatch.setattr(api, "_run_parsha", _fake_run_parsha)
    res = api._run_query_impl("מה הפרשה השבוע?", "he", "parsha", [], owner_id="owner-a")
    assert called["question"] == "מה הפרשה השבוע?"
    assert res.answer == "ok"


@pytest.mark.parametrize("kind,today,expected", [
    ("daf_yomi", date(2026, 8, 5), "2026-08-05"),      # daily bucket = today's own date
    ("parsha", date(2026, 8, 5), "2026-08-02"),        # Wednesday -> that week's Sunday
    ("parsha", date(2026, 8, 2), "2026-08-02"),        # Sunday itself -> same day
    ("parsha", date(2026, 8, 8), "2026-08-02"),        # Saturday -> the Sunday that started the week
])
def test_calendar_cache_key_buckets(kind, today, expected):
    assert api._calendar_cache_key(kind, today) == expected


# _cap_hits: caught live — an uncapped parsha/daf-yomi fetch (a whole parsha's verses, or a whole
# daf, times every commentator) produced a real 400/context-overflow from the provider, and on a
# smaller-but-still-oversized daf-yomi request, a response that echoed its own instructions with
# unbalanced ** markers. The fix keeps every base-text hit and trims only commentary.
def test_cap_hits_noop_under_the_limit():
    hits = [_hit("a"), _hit("b", comm="rashi")]
    assert api._cap_hits(hits, max_total=10) == hits


def test_cap_hits_keeps_all_base_text_and_trims_commentary():
    base = [_hit(f"base{i}") for i in range(5)]
    commentary = [_hit(f"c{i}", comm="rashi") for i in range(20)]
    out = api._cap_hits(base + commentary, max_total=10)
    assert len(out) == 10
    assert all(h in out for h in base)          # every base hit survives
    assert sum(1 for h in out if not h.commentator_id) == 5
    assert sum(1 for h in out if h.commentator_id) == 5


def test_cap_hits_base_text_alone_can_exceed_the_cap():
    """If there's more base text than the cap (a long parsha), every base hit still survives —
    trimming the primary text itself would be worse than a slightly larger prompt."""
    base = [_hit(f"base{i}") for i in range(15)]
    commentary = [_hit(f"c{i}", comm="rashi") for i in range(5)]
    out = api._cap_hits(base + commentary, max_total=10)
    assert len(out) == 15
    assert all(not h.commentator_id for h in out)


# Caught live (2026-08-05): asked "what daf are we on", the model answered with the corpus's
# internal amud-linear chunk number (194) instead of the real daf (97) — it has no way to tell the
# two apart from the citation refs alone. _daf_yomi_context_note tells it the real number directly.
def test_daf_yomi_context_note_states_the_real_daf_number_hebrew():
    note = api._daf_yomi_context_note("Chullin", 97, True)
    assert "Chullin" in note
    assert "97" in note
    assert "194" not in note   # never mentions the corpus-internal linear number


def test_daf_yomi_context_note_states_the_real_daf_number_english():
    note = api._daf_yomi_context_note("Chullin", 97, False)
    assert "Chullin 97" in note


# Caught live (2026-08-05): the model conflated the Maftir (the final verses of the Torah portion
# itself) with the Haftarah (a separate Nevi'im reading) when discussing the parsha.
# _parsha_context_note states both explicitly so the model has no reason to guess.
def test_parsha_context_note_distinguishes_maftir_from_haftarah_hebrew():
    info = cal.ParshaInfo(name_en="Re'eh", name_he="ראה", ref_range="Deuteronomy 11:26-16:17",
                          haftarah_ref="Isaiah 54:11-55:5")
    note = api._parsha_context_note(info, True)
    assert "Deuteronomy 11:26-16:17" in note
    assert "Isaiah 54:11-55:5" in note
    assert "מפטיר" in note
    assert "הפטרה" in note


def test_parsha_context_note_omits_haftarah_clause_when_none_resolved():
    info = cal.ParshaInfo(name_en="Re'eh", name_he="ראה", ref_range="Deuteronomy 11:26-16:17")
    note = api._parsha_context_note(info, True)
    assert "הפטרה" not in note
    assert "Deuteronomy 11:26-16:17" in note
