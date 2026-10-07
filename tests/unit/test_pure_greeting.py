"""Unit tests for pure greeting detection and fast-path handling."""

from __future__ import annotations

import pytest

from app.api import _run_query
from chavruta.corpus.schema import Query
from chavruta.intents.router import Router, is_pure_greeting, retrieval_text


@pytest.mark.parametrize(
    "text",
    [
        "שלום",
        "שלום.",
        "היי!",
        "בוקר טוב",
        "ערב טוב",
        "צהריים טובים",
        "מה נשמע",
        "מה שלומך",
        "מה קורה",
        "שלום עליכם",
        "hello",
        "Hello",
        "hi",
        "Hi!",
        "hey",
        " hey! ",
        "שלום!",
        "מה נשמע?",
    ],
)
def test_pure_greetings_detected(text: str):
    assert is_pure_greeting(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "שלום אשמח לדעת האם מותר להתפלל שחרית בצהריים",
        "האם מותר לומר שלום לפני התפילה",
        "מה הדין אם התפללתי בצהריים",
        "בוקר טוב מה הדין כשאדם שכח יעלה ויבוא",
        "hello can you explain what rashi says on genesis 1:1",
        "",
        "   ",
    ],
)
def test_substantive_questions_not_pure_greeting(text: str):
    assert is_pure_greeting(text) is False


def test_substantive_question_not_altered():
    question = "שלום אשמח לדעת האם מותר להתפלל שחרית בצהריים"
    # Verify retrieval_text does not strip or alter any words (especially "שלום" or "צהריים")
    cleaned = retrieval_text(question)
    assert cleaned == question
    assert "שלום" in cleaned
    assert "צהריים" in cleaned

    # Verify Router().route keeps the text intact
    q = Router().route(Query(text=question))
    assert q.text == question
    assert "שלום" in q.search_text
    assert "צהריים" in q.search_text


def test_run_query_fast_path_greeting_hebrew():
    resp = _run_query("שלום", "he", "qa", [])
    assert resp.citations == []
    assert resp.grounded is False
    assert resp.intent == "qa"
    assert resp.files == []
    assert "שלום וברכה! אני חברותא — שותף הלימוד שלך" in resp.answer
    assert "במה נוכל להעמיק היום?" in resp.answer


def test_run_query_fast_path_greeting_english():
    resp = _run_query("Hello!", "en", "qa", [])
    assert resp.citations == []
    assert resp.grounded is False
    assert resp.intent == "qa"
    assert resp.files == []
    assert "Hello" in resp.answer
    assert "study partner" in resp.answer
