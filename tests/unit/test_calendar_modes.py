"""Parshat HaShavua / Daf Yomi: the beta allowlist gate and the calendar-cache bucket key.

_run_parsha/_run_daf_yomi's happy path needs a real pipeline (Qdrant + LLM) and is exercised
manually against the live corpus (see the feature's rollout notes); what's unit-testable in
isolation is the gate itself (an unlisted owner must never reach the pipeline at all) and the
cache-key logic.
"""

from __future__ import annotations

from datetime import date

import app.api as api
import app.db as db
import app.devhelpers as devhelpers
import pytest

import chavruta.calendar.sefaria_calendar as cal
from chavruta.retrieval.base import RankedHit


def _hit(cid, comm=None):
    return RankedHit(chunk_id=cid, ref=cid, text=f"text of {cid}", score=1.0, commentator_id=comm)


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "calendar_helpers.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def test_calendar_modes_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_CALENDAR_BETA_OWNERS", raising=False)
    assert api._calendar_modes_enabled("anyone") is False
    assert api._calendar_modes_enabled("local") is False


def test_calendar_modes_enabled_for_a_dev_helper_granted_the_feature(monkeypatch, fresh_db):
    """The env var is the blunt, redeploy-to-edit allowlist; a dev helper granted the "calendar"
    feature from the admin panel (app/devhelpers.py) must reach the same gate WITHOUT being on that
    env var — this is the whole point of per-person grants (mirrors _sugya_enabled's fallback)."""
    monkeypatch.delenv("CHAVRUTA_CALENDAR_BETA_OWNERS", raising=False)
    devhelpers.invite("helper-cal", by="operator-1", features=["calendar"])
    assert api._calendar_modes_enabled("helper-cal") is False   # not yet accepted — nothing applies
    devhelpers.accept("helper-cal")
    assert api._calendar_modes_enabled("helper-cal") is True
    # A helper granted only the unrelated "sugya" feature must NOT get the calendar modes too.
    devhelpers.invite("helper-other", by="operator-1", features=["sugya"])
    devhelpers.accept("helper-other")
    assert api._calendar_modes_enabled("helper-other") is False


def test_calendar_modes_enabled_only_for_listed_owners(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CALENDAR_BETA_OWNERS", "owner-a, owner-b")
    assert api._calendar_modes_enabled("owner-a") is True
    assert api._calendar_modes_enabled("owner-b") is True
    assert api._calendar_modes_enabled("owner-c") is False


def test_calendar_modes_wildcard_enables_everyone(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_CALENDAR_BETA_OWNERS", "*")
    assert api._calendar_modes_enabled("anyone") is True
    assert api._calendar_modes_enabled("local") is True


def test_daf_yomi_is_open_to_everyone_but_parsha_is_still_beta(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_CALENDAR_BETA_OWNERS", raising=False)
    assert api._calendar_modes_enabled("not-listed", "dafyomi") is True
    assert api._calendar_modes_enabled("not-listed", "parsha") is False
    assert api._calendar_modes_enabled("not-listed") is False      # what /me reports: the parsha beta


def test_unlisted_owner_reaches_daf_yomi(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_CALENDAR_BETA_OWNERS", raising=False)
    called = {}

    def _fake(question, lang, history=None, owner_id="local", llm=None):
        called["ok"] = True
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent="dafyomi", files=[])

    monkeypatch.setattr(api, "_run_daf_yomi", _fake)
    monkeypatch.setattr(api, "classify_and_distill", lambda *a, **k: __import__("types").SimpleNamespace(
        action="study", answer="", distilled_query="", requested_files=[]))
    res = api._run_query_impl("מה הדף היום?", "he", "dafyomi", [], owner_id="not-listed")
    assert called.get("ok") and res.answer == "ok"


@pytest.mark.parametrize("intent_str", ["parsha"])
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
    ("parsha", date(2026, 8, 5), "2026-08-05"),        # daily bucket = today's own date
    ("parsha", date(2026, 8, 2), "2026-08-02"),        # Sunday -> same day
    ("parsha", date(2026, 8, 8), "2026-08-08"),        # Saturday -> same day
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
    # The internal number appears ONLY as an explicit mapping back to the real daf (a model told merely
    # "it is not the daf" sometimes decided the sources were about another daf and refused) ...
    assert "Chullin.194.* = Chullin 97b" in note
    # ... and the model is told never to print it.
    assert "אל תכתוב מספר פנימי" in note


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


# Decision (2026-08-05): Parshat HaShavua's default (non-lesson) turn changed from the Socratic
# chavruta style to direct Q&A — _run_daf_yomi is untouched and still defaults to chavruta.
def test_run_parsha_defaults_to_qa_turn_not_chavruta(monkeypatch):
    info = cal.ParshaInfo(name_en="Re'eh", name_he="ראה", ref_range="Deuteronomy 11:26-16:17")
    monkeypatch.setattr(api, "_get_pipeline", lambda: __import__("types").SimpleNamespace(llm="llm"))
    monkeypatch.setattr(api, "_resolve_parsha_cached", lambda: info)
    monkeypatch.setattr(api, "_fetch_ranked_hits", lambda *a, **k: [_hit("Deuteronomy.11.26")])
    monkeypatch.setattr(api, "_wants_full_lesson", lambda *a, **k: False)

    def _boom_chavruta(*a, **k):
        raise AssertionError("parsha's default turn must not go through _generate_chavruta_turn")

    called = {}

    def _fake_qa_turn(question, hits, lang, he, history, llm):
        called["hit"] = True
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent="qa", files=[])

    monkeypatch.setattr(api, "_generate_chavruta_turn", _boom_chavruta)
    monkeypatch.setattr(api, "_generate_qa_turn_from_hits", _fake_qa_turn)

    res = api._run_parsha("מה מיוחד בפרשה?", "he")
    assert called.get("hit") is True
    assert res.answer == "ok"


# Decision (2026-08-05): the Haftarah is a secondary reading relative to the parsha (whose full text
# IS preloaded) — only its opening and closing pasuk are fetched up front, no commentaries at all;
# the turn can self-fetch the rest via ===NEED_SOURCES=== if it actually needs them.
def test_run_parsha_haftarah_gets_only_boundary_verses_no_commentary(monkeypatch):
    info = cal.ParshaInfo(name_en="Re'eh", name_he="ראה", ref_range="Deuteronomy 11:26-16:17",
                          haftarah_ref="Isaiah 54:11-55:5")
    monkeypatch.setattr(api, "_get_pipeline", lambda: __import__("types").SimpleNamespace(llm="llm"))
    monkeypatch.setattr(api, "_resolve_parsha_cached", lambda: info)
    monkeypatch.setattr(api, "_wants_full_lesson", lambda *a, **k: False)
    monkeypatch.setattr(api, "_generate_qa_turn_from_hits",
                        lambda *a, **k: api.QueryResponse(answer="ok", citations=[], grounded=True,
                                                          intent="qa", files=[]))

    fetch_calls = []

    def _fake_fetch(targets, **k):
        fetch_calls.append(list(targets))
        return [_hit(t) for t in targets]

    monkeypatch.setattr(api, "_fetch_ranked_hits", _fake_fetch)

    api._run_parsha("שאלה", "he")

    # First call is the parsha's own full range+commentary; the SECOND is the haftarah fetch.
    assert len(fetch_calls) == 2
    haftarah_targets = fetch_calls[1]
    # Isaiah 54:11-55:5 is many verses — only 2 distinct base pesukim (opening + closing) requested,
    # never the full range and never a "Rashi on ..." style commentary ref among them.
    assert len(haftarah_targets) <= 4          # the 2 boundary verses + their Sefaria ref variants
    assert not any(" on " in t for t in haftarah_targets)
    assert any("54.11" in t or "54:11" in t for t in haftarah_targets)   # opening verse
    assert any("55.5" in t or "55:5" in t for t in haftarah_targets)     # closing verse


def test_cap_hits_preserves_min_commentaries_when_base_exceeds_cap():
    base = [_hit(f"base{i}") for i in range(15)]
    commentary = [_hit(f"c{i}", comm="rashi") for i in range(10)]
    out = api._cap_hits(base + commentary, max_total=10, min_commentaries=5)
    assert len(out) == 20  # 15 base + 5 commentary
    assert sum(1 for h in out if not h.commentator_id) == 15
    assert sum(1 for h in out if h.commentator_id) == 5


def test_run_daf_yomi_defaults_to_qa_turn_like_parsha(monkeypatch):
    info = cal.DafYomiInfo(tractate="Chullin", daf=123)
    monkeypatch.setattr(api, "_get_pipeline", lambda: __import__("types").SimpleNamespace(llm="llm"))
    monkeypatch.setattr(api, "_resolve_daf_yomi_cached", lambda: info)
    monkeypatch.setattr(api, "_wants_full_lesson", lambda *a, **k: False)

    def _boom_chavruta(*a, **k):
        raise AssertionError("daf yomi default turn must now go through _generate_qa_turn_from_hits like parsha")

    called = {}

    def _fake_qa_turn(question, hits, lang, he, history, llm):
        called["hit"] = True
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent="qa", files=[])

    monkeypatch.setattr(api, "_generate_chavruta_turn", _boom_chavruta)
    monkeypatch.setattr(api, "_generate_qa_turn_from_hits", _fake_qa_turn)
    monkeypatch.setattr(api, "_fetch_ranked_hits", lambda targets, **k: [_hit(t) for t in targets])

    res = api._run_daf_yomi("שאלה על הדף", "he")
    assert called.get("hit") is True
    assert res.answer == "ok"


def test_run_daf_yomi_fetches_boundary_segments_and_rashi(monkeypatch):
    info = cal.DafYomiInfo(tractate="Chullin", daf=123)
    monkeypatch.setattr(api, "_get_pipeline", lambda: __import__("types").SimpleNamespace(llm="llm"))
    monkeypatch.setattr(api, "_resolve_daf_yomi_cached", lambda: info)
    monkeypatch.setattr(api, "_wants_full_lesson", lambda *a, **k: False)
    monkeypatch.setattr(api, "_generate_qa_turn_from_hits",
                        lambda *a, **k: api.QueryResponse(answer="ok", citations=[], grounded=True,
                                                          intent="qa", files=[]))

    fetch_calls = []

    def _fake_fetch(targets, **k):
        fetch_calls.append(list(targets))
        return [_hit(t) for t in targets]

    monkeypatch.setattr(api, "_fetch_ranked_hits", _fake_fetch)

    api._run_daf_yomi("למה רב אומר כך כאן?", "he")      # a specific ask: boundary floor only

    # Two lookups: the base boundary segments, then Rashi/Tosafot on the segments that exist.
    assert len(fetch_calls) == 2
    targets = fetch_calls[0] + fetch_calls[1]
    # Verify boundary segments for both amud a (245) and amud b (246) are included
    assert any("Chullin.245.1" in t or "Chullin 245.1" in t for t in targets)
    assert any("Chullin.246.1" in t or "Chullin 246.1" in t for t in targets)
    # Rashi AND Tosafot are preloaded on the boundary segments; nothing else is
    assert any("Rashi_on_Chullin.245.1" in t for t in targets)
    assert any("Tosafot_on_Chullin.245.1" in t for t in targets)
    assert not any("Ritva_on_Chullin" in t for t in targets)


def test_requested_daf_prefers_a_daf_named_in_the_message():
    assert api._requested_daf("מה הדף היום?") is None
    tract, daf, amudim, explicit = api._requested_daf("תלמד איתי סנהדרין כה ע\"א")
    assert (tract, daf, amudim, explicit) == ("Sanhedrin", 25, ["a"], True)
    # a bare daf names both sides of the page
    assert api._requested_daf("אני בדף עט בחולין")[:3] == ("Chullin", 79, ["a", "b"])


def test_run_daf_yomi_uses_the_named_daf_not_todays_and_pulls_dispute_commentary(monkeypatch):
    monkeypatch.setattr(api, "_get_pipeline", lambda: __import__("types").SimpleNamespace(llm="llm"))
    monkeypatch.setattr(api, "_resolve_daf_yomi_cached",
                        lambda: (_ for _ in ()).throw(AssertionError("today's daf must not be resolved")))
    monkeypatch.setattr(api, "_wants_full_lesson", lambda *a, **k: False)
    monkeypatch.setattr(api, "_generate_qa_turn_from_hits",
                        lambda *a, **k: api.QueryResponse(answer="ok", citations=[], grounded=True,
                                                          intent="qa", files=[]))
    calls = []

    def _fake_fetch(targets, **k):
        calls.append(list(targets))
        return [_hit(t) for t in targets if " " not in t]

    monkeypatch.setattr(api, "_fetch_ranked_hits", _fake_fetch)
    api._run_daf_yomi("מה המחלוקת בין רש\"י לתוספות בסנהדרין כה ע\"א?", "he")
    flat = [t for c in calls for t in c]
    assert any(t.startswith("Sanhedrin.49.") for t in flat)            # 25a → corpus n=49
    assert not any(t.startswith("Sanhedrin.50.") for t in flat)        # amud b was not asked for
    assert any(t.startswith("Tosafot_on_Sanhedrin.49.") for t in flat)


def test_wants_full_lesson_requires_lesson_keywords():
    # User's actual question that falsely triggered lesson generation in production:
    assert not api._wants_full_lesson("מה הקריאה היום ולמה קוראים אותה?")
    assert not api._wants_full_lesson("מה הפרשה השבוע?")
    assert not api._wants_full_lesson("מה הדף היומי היום?")
    assert not api._wants_full_lesson("ספר לי על רש״י על הפסוק הראשון")

    # Questions that do contain lesson keywords should proceed to LLM:
    class FakeLLM:
        def generate(self, prompt, **kwargs):
            return __import__("types").SimpleNamespace(text="כן")

    assert api._wants_full_lesson("תבנה לי שיעור על הפרשה", llm=FakeLLM())
    assert api._wants_full_lesson("אני רוצה מערך שיעור על הדף", llm=FakeLLM())
    assert api._wants_full_lesson("תכין דף מקורות לשבת", llm=FakeLLM())



def test_daf_phrase_he_is_detected_back_as_the_same_daf():
    from chavruta.intents.hebrew_refs import detect_hebrew_refs

    assert detect_hebrew_refs(api._daf_phrase_he("Sanhedrin", 25, ["a"])) == ["Sanhedrin.25a"]
    assert detect_hebrew_refs(api._daf_phrase_he("Chullin", 79, None)) == ["Chullin.79a", "Chullin.79b"]


def test_run_daf_yomi_lesson_goes_through_the_regular_lesson_path_seeded_with_the_boundary(monkeypatch):
    info = cal.DafYomiInfo(tractate="Chullin", daf=123)
    monkeypatch.setattr(api, "_get_pipeline", lambda: __import__("types").SimpleNamespace(llm="llm"))
    monkeypatch.setattr(api, "_resolve_daf_yomi_cached", lambda: info)
    monkeypatch.setattr(api, "_wants_full_lesson", lambda *a, **k: True)
    monkeypatch.setattr(api, "_fetch_ranked_hits", lambda targets, **k: [_hit(t) for t in targets])
    seen = {}

    def _fake_lesson(question, lang, **kw):
        seen.update(question=question, seed=kw.get("seed_hits"))
        return api.QueryResponse(answer="lesson", citations=[], grounded=True, intent="lesson", files=[])

    monkeypatch.setattr(api, "_run_lesson", _fake_lesson)
    res = api._run_daf_yomi("תבנה לי שיעור על הדף", "he")
    assert res.answer == "lesson"
    assert "חולין" in seen["question"]
    assert seen["seed"], "the daf boundary must seed the lesson"


def test_generic_study_request_reads_the_whole_daf_but_a_specific_question_does_not(monkeypatch):
    info = cal.DafYomiInfo(tractate="Chullin", daf=123)
    monkeypatch.setattr(api, "_get_pipeline", lambda: __import__("types").SimpleNamespace(llm="llm"))
    monkeypatch.setattr(api, "_resolve_daf_yomi_cached", lambda: info)
    monkeypatch.setattr(api, "_wants_full_lesson", lambda *a, **k: False)
    monkeypatch.setattr(api, "_generate_qa_turn_from_hits",
                        lambda *a, **k: api.QueryResponse(answer="ok", citations=[], grounded=True,
                                                          intent="qa", files=[]))

    def _run(question):
        calls = []
        monkeypatch.setattr(api, "_fetch_ranked_hits",
                            lambda targets, **k: calls.append(list(targets)) or [_hit(t) for t in targets if " " not in t])
        api._run_daf_yomi(question, "he")
        return [t for c in calls for t in c]

    assert any(t.startswith("Chullin.245.30") for t in _run("תלמד איתי את הדף היומי"))   # whole daf
    assert not any(t.startswith("Chullin.245.30") for t in _run("למה רב אומר כך?"))      # boundary only


def test_follow_up_without_a_daf_stays_on_the_daf_of_the_conversation():
    from chavruta.corpus.schema import Turn

    # an earlier answer cited Bava Metzia amud-linear 3 and 4 = daf 2a / 2b
    hist = [Turn(role="user", text="תלמד אותי את בבא מציעא ב ע\"א"),
            Turn(role="assistant", text="...", refs=["Bava_Metzia.3.1", "Rashi_on_Bava_Metzia.3.1.1"])]
    assert api._daf_from_history(hist)[:2] == ("Bava Metzia", 2)
    # refs only (the user turn named nothing): converted back from the corpus numbering
    hist = [Turn(role="user", text="תלמד אותי"), Turn(role="assistant", text="...", refs=["Sanhedrin.49.5"])]
    assert api._daf_from_history(hist)[:2] == ("Sanhedrin", 25)
    assert api._daf_from_history([]) is None
    assert api._daf_from_history([Turn(role="assistant", text="x", refs=["Genesis.1.1"])]) is None


def test_empty_parentheses_left_by_stripped_markers_are_removed():
    assert api._strip_markers("חכמים חולקים [S1] (): עד חצות", he=True) == "חכמים חולקים: עד חצות"
    out = api._strip_markers("מבאר (,[S1]) ועוד ([S2]) וכן (רש\"י) שם", he=True)
    assert "()" not in out and "(,)" not in out
    assert '(רש"י)' in out          # a parenthesis with real content is untouched


def test_requested_daf_reads_english_references():
    assert api._requested_daf("Explain Bava Metzia 2a please")[:3] == ("Bava Metzia", 2, ["a"])
    assert api._requested_daf("what is Sanhedrin 25 about")[:3] == ("Sanhedrin", 25, ["a", "b"])
    assert api._requested_daf("what is the daf today") is None


def test_prefer_tractate_keeps_the_daf_tractate_first_and_caps_the_rest():
    hits = [_hit("Responsa.1"), _hit("Sanhedrin.49.3"), _hit("Rashi_on_Sanhedrin.49.1.1")] + \
           [_hit(f"Other.{i}") for i in range(9)]
    out = api._prefer_tractate(hits, "Sanhedrin", other_cap=4)
    assert [h.ref for h in out[:2]] == ["Sanhedrin.49.3", "Rashi_on_Sanhedrin.49.1.1"]
    assert len(out) == 2 + 4


def test_segments_are_ordered_numerically_not_alphabetically(monkeypatch):
    seen = {}
    monkeypatch.setattr(api, "_fetch_ranked_hits",
                        lambda targets, **k: seen.setdefault("n", 0) or seen.update(n=1) or
                        [_hit(f"Chullin.245.{i}") for i in (10, 2, 1)] if seen.get("n") is None else
                        (seen.update(second=list(targets)) or []))
    api._daf_hits("Chullin", 123, ["a"], ["rashi"], whole=True)
    second = seen["second"]
    assert second.index("Rashi_on_Chullin.245.2.1") < second.index("Rashi_on_Chullin.245.10.1")


def test_annotated_markers_are_stripped_whole():
    out = api._strip_markers('המדרש על קין והבל [S4 מצטט מדרש רבה]: "קשה הדבר" וכן [S5 בשם מדרש שמואל]: עוד', he=True)
    assert "[S" not in out and "מצטט" not in out
    assert 'המדרש על קין והבל: "קשה הדבר"' in out


def test_hebrew_wikisource_tier_is_cc_by_sa_not_unknown():
    from chavruta.corpus.refs import license_for_ref

    wiki = "https://he.wikisource.org/wiki/%D7%A1"
    for ref in ("ספר תולדות אדם, אות 192", "ברטנורא על בבא מציעא א, אות 1", 'רמב"ם הלכות תשובה ה ה'):
        assert license_for_ref(ref, "he", wiki) == ("CC-BY-SA", "ויקיטקסט העברי")
        # a Hebrew label alone is NOT evidence of Wikisource — fail closed (unknown)
        assert license_for_ref(ref, "he") == ("", "")
        assert license_for_ref(ref, "he", "https://example.org/x") == ("", "")
    assert license_for_ref("Genesis.1.1", "he")[0] == "Public Domain"        # Sefaria refs untouched
    assert license_for_ref("Totally_Unknown_Work.1.1", "he") == ("", "")     # an English unknown stays unknown
