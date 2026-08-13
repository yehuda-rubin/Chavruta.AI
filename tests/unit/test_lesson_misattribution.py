"""The lesson path's misattribution caveat — the branch that hid a NameError.

`misattribution_note` was used at the caveat site but left out of the function-local import, and the
whole suite stayed green: the branch only executes when a misattribution is actually found, and no
test had ever produced one. A guard that crashes exactly when it fires is worse than no guard, so
this drives the real lesson assembly to the point where the caveat is appended.
"""
from __future__ import annotations

from types import SimpleNamespace

import app.api as api


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


def test_lesson_misattribution_caveat_is_appended(monkeypatch):
    monkeypatch.setattr(api, "_fix_bleeding_sentences", lambda t, he, llm: t)
    hits = [
        _hit("Rashi_on_Sukkah.41.1.1", "מקדש העתיד שאנו מצפין בנוי ומשוכלל הוא יגלה ויבא מן השמים"),
        _hit("Tosafot_on_Sukkah.41.1.1",
             "ולעולם יבנה בידי אדם ואין סתירה בין הדברים שהמלאכה מסורה לבשר ודם"),
    ]
    res = api._generate_lesson_from_hits(
        "בניין בית המקדש", hits, "he", True, audience="yeshiva", grade_band="", length="medium",
        tpl=None, history=None, owner_id="local", llm=_StubLLM())

    joined = " ".join(res.caveats)
    assert "רש" in joined and "תוספות" in joined, f"no misattribution caveat: {res.caveats}"
