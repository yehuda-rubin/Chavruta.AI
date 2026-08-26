"""After a lesson finishes, follow-up chat should discuss it — not silently rebuild one.

Real gap found 2026-08-21, reading the code with the founder: sticky mode (`_prepare_continue`)
locks a chat into `intent="lesson"` forever, and `_run_lesson` had no notion of "this is a
follow-up, not a new topic" beyond the narrow audience/length clarify-echo (`_is_clarify_answer`)
— so a plain follow-up question fell straight into `_run_lesson`, which retrieved sources for the
follow-up's OWN wording and built an unrelated second lesson, silently spending a real weekly
lesson-pool charge on garbage. See specs/007-lesson-followup-routing/plan.md.
"""
from __future__ import annotations

import app.api as api
from chavruta.corpus.schema import Turn


def _lesson_turn() -> Turn:
    return Turn(role="assistant", text="השיעור המלא על שניים אוחזין בטלית...", refs=[], lesson=True)


def _user_turn(text: str) -> Turn:
    return Turn(role="user", text=text)


# ── Turn.lesson ──────────────────────────────────────────────────────────────
def test_turn_lesson_defaults_false():
    assert Turn(role="assistant", text="x").lesson is False


# ── _lesson_turn_text ──────────────────────────────────────────────────────────
def test_lesson_turn_text_leaves_an_ordinary_turn_untouched():
    text, is_lesson = api._lesson_turn_text({"text": "תשובה רגילה", "files": []})
    assert text == "תשובה רגילה"
    assert is_lesson is False


def test_lesson_turn_text_pulls_the_full_lesson_file_when_text_is_empty():
    m = {"text": "", "files": [
        {"name": "דף_מקורות.doc", "content": "מקורות..."},
        {"name": "מהלך_השיעור.doc", "content": "מהלך..."},
        {"name": "השיעור_המלא.doc", "content": "השיעור המלא בפועל"},
    ]}
    text, is_lesson = api._lesson_turn_text(m)
    assert text == "השיעור המלא בפועל"
    assert is_lesson is True


def test_lesson_turn_text_falls_back_to_the_last_file_if_the_full_lesson_name_is_missing():
    m = {"text": "", "files": [{"name": "דף_מקורות.doc", "content": "רק מקורות"}]}
    text, is_lesson = api._lesson_turn_text(m)
    assert text == "רק מקורות"
    assert is_lesson is True


def test_lesson_turn_text_with_no_files_and_no_text_stays_empty_not_a_lesson():
    text, is_lesson = api._lesson_turn_text({"text": "", "files": []})
    assert text == ""
    assert is_lesson is False


# ── _is_lesson_build_request ──────────────────────────────────────────────────
def test_build_request_matches_new_lesson_phrasing():
    assert api._is_lesson_build_request("תבנה לי שיעור חדש על פרשת השבוע")
    assert api._is_lesson_build_request("אני רוצה שיעור נוסף")
    assert api._is_lesson_build_request("build a new lesson about Yoma")


def test_build_request_matches_change_the_existing_lesson_phrasing():
    assert api._is_lesson_build_request("תקצר את השיעור")
    assert api._is_lesson_build_request("תוסיף בשיעור עוד על תוספות")
    assert api._is_lesson_build_request("please shorten the lesson")


def test_build_request_does_not_match_a_plain_followup_question():
    assert not api._is_lesson_build_request('תסביר לי יותר על מה שרש"י אמר')
    assert not api._is_lesson_build_request("למה תוספות חולקים על רש\"י?")
    assert not api._is_lesson_build_request("what does the Rambam say about this?")


def test_build_request_does_not_fire_on_a_bare_mention_of_the_word_lesson():
    assert not api._is_lesson_build_request("מה היה השיעור הזה בעצם?")


# ── _run_query_impl dispatch ────────────────────────────────────────────────
def test_a_followup_after_a_finished_lesson_goes_to_chavruta_not_a_new_lesson(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "_run_lesson",
                        lambda *a, **k: calls.append("lesson") or
                        api.QueryResponse(answer="", citations=[], grounded=False, intent="lesson", files=[]))
    monkeypatch.setattr(api, "_run_chavruta",
                        lambda *a, **k: calls.append("chavruta") or
                        api.QueryResponse(answer="תשובה", citations=[], grounded=True, intent="chavruta", files=[]))
    history = [_user_turn("שניים אוחזין בטלית"), _lesson_turn()]
    api._run_query_impl('תסביר לי יותר על מה שרש"י אמר', "he", "lesson", history)
    assert calls == ["chavruta"]


def test_an_explicit_new_lesson_request_after_a_finished_lesson_still_builds_one(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "_run_lesson",
                        lambda *a, **k: calls.append("lesson") or
                        api.QueryResponse(answer="", citations=[], grounded=False, intent="lesson", files=[]))
    monkeypatch.setattr(api, "_run_chavruta",
                        lambda *a, **k: calls.append("chavruta") or
                        api.QueryResponse(answer="x", citations=[], grounded=True, intent="chavruta", files=[]))
    history = [_user_turn("שניים אוחזין בטלית"), _lesson_turn()]
    api._run_query_impl("תבנה לי שיעור חדש על פרשת השבוע", "he", "lesson", history)
    assert calls == ["lesson"]


def test_the_first_turn_of_a_lesson_session_is_unaffected(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "_run_lesson",
                        lambda *a, **k: calls.append("lesson") or
                        api.QueryResponse(answer="", citations=[], grounded=False, intent="lesson", files=[]))
    monkeypatch.setattr(api, "_run_chavruta",
                        lambda *a, **k: calls.append("chavruta") or
                        api.QueryResponse(answer="x", citations=[], grounded=True, intent="chavruta", files=[]))
    api._run_query_impl("שניים אוחזין בטלית", "he", "lesson", [])
    assert calls == ["lesson"]
