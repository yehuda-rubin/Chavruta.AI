"""The watching guards on the lesson path — the branch that once hid a NameError.

`misattribution_note` was used at a caveat site and left out of the function-local import, and the
whole suite stayed green: the branch only executes when a finding exists, and no test had ever
produced one. A guard that crashes exactly when it fires is worse than no guard.

The guards are INTERNAL ONLY (decision 2026-08-13) — they log and add nothing a user sees. That is
precisely why they need a test that drives the real lesson assembly through them: an internal check
nobody reads and nothing exercises would rot silently, and its first symptom would be a 500 on the
day it finally matched something.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import app.api as api
from chavruta.generation import guards


class _StubLLM:
    """Returns a lesson whose prose credits Rashi with Tosafot's words. No network, no model."""

    def request(self, job, lang="he", token_budget=0):
        return (
            "===SOURCE_SHEET===\nמקורות\n"
            "===LESSON_FLOW===\nמהלך\n"
            "===FULL_LESSON===\n"
            'רש"י כותב במפורש [S2]: "ולעולם יבנה בידי אדם ואין סתירה בין הדברים שהמלאכה מסורה לבשר ודם".\n'
            "===ORDER===\nS1, S2\n"
        ), []

    def complete(self, *a, **k):
        return ""


def _hit(ref, text):
    return SimpleNamespace(ref=ref, text=text, text_he=text, text_en="", chunk_id=ref,
                           deep_link="", commentator_id=None, license="", version_title="")


def _build(monkeypatch):
    monkeypatch.setattr(api, "_fix_bleeding_sentences", lambda t, he, llm: t)
    hits = [
        _hit("Rashi_on_Sukkah.41.1.1", "מקדש העתיד שאנו מצפין בנוי ומשוכלל הוא יגלה ויבא מן השמים"),
        _hit("Tosafot_on_Sukkah.41.1.1",
             "ולעולם יבנה בידי אדם ואין סתירה בין הדברים שהמלאכה מסורה לבשר ודם"),
    ]
    return api._generate_lesson_from_hits(
        "בניין בית המקדש", hits, "he", True, audience="yeshiva", grade_band="", length="medium",
        tpl=None, history=None, owner_id="local", llm=_StubLLM())


def test_misattribution_is_recorded_not_shown(monkeypatch, caplog):
    """Both halves matter, and the recorded half matters more than the logged one: the admin panel
    reads the STORED finding, so an assertion on log wording would pass while the screen stayed
    empty. The finding must reach the sink — and must NOT reach the teacher, because the guard has
    not yet earned the right to put a warning on someone's lesson."""
    seen: list[tuple[str, str, dict]] = []
    guards.set_sink(lambda kind, intent, detail: seen.append((kind, intent, detail)))
    try:
        with caplog.at_level(logging.WARNING, logger="chavruta.guards"):
            res = _build(monkeypatch)
    finally:
        guards.set_sink(None)

    assert seen, "the guard recorded nothing — the admin panel would show an empty screen"
    kind, intent, detail = seen[0]
    assert (kind, intent) == ("misattribution", "lesson")
    assert detail["claimed"] == "rashi" and "tosafot" in detail["found_in"]
    # A string, not a list: `found_in` is a tuple at the source and the panel renders it as text.
    assert isinstance(detail["found_in"], str), detail
    assert not any("רש" in c and "תוספות" in c for c in res.caveats), \
        f"internal-only guard leaked into a user-visible caveat: {res.caveats}"


def test_the_lesson_is_still_produced(monkeypatch):
    """A watching guard must never cost the teacher their files."""
    res = _build(monkeypatch)
    assert res.files, "the lesson lost its files"
