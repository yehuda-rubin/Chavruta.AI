"""Unit tests for smart lesson follow-up classification and single-file editing (Gemma-3-27B)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app import api
from app.api import CitationOut, FileOut, QueryResponse, _edit_lesson_file, _recover_lesson_topic
from chavruta.corpus.schema import Intent, Turn
from chavruta.intents.llm_planner import (
    DISTILLER_MODEL,
    LessonFollowupDecision,
    _heuristic_fallback_classify,
    classify_lesson_followup,
)
from chavruta.llm import metering


class FakeChatCompletion:
    def __init__(self, content: str, prompt_tokens: int = 150, completion_tokens: int = 35):
        self.choices = [MagicMock(message=MagicMock(content=content))]
        self.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


# ── 1. Heuristic Fallback Tests ───────────────────────────────────────────────

def test_heuristic_fallback_classify_chat():
    """Questions about the lesson route to chat/chavruta discussion."""
    res = _heuristic_fallback_classify("למה רש\"י פירש כך ולא כתוספות?", last_lesson_topic="סוכה")
    assert res.action == "chat"
    assert res.target_file is None
    assert res.topic == "סוכה"


def test_heuristic_fallback_classify_edit_flow():
    """Requests targeting lesson flow/stages route to edit_file with target_file='flow'."""
    res = _heuristic_fallback_classify("תקצר את שלב הפתיחה במהלך השיעור", last_lesson_topic="סוכה")
    assert res.action == "edit_file"
    assert res.target_file == "flow"
    assert res.topic == "סוכה"


def test_heuristic_fallback_classify_edit_full():
    """Requests targeting the full lesson text route to edit_file with target_file='full'."""
    res = _heuristic_fallback_classify("תרחיב יותר בשיעור המלא על שיטת רבי מאיר", last_lesson_topic="דיני ממונות")
    assert res.action == "edit_file"
    assert res.target_file == "full"
    assert res.topic == "דיני ממונות"


def test_heuristic_fallback_classify_rebuild_all():
    """Requests to rebuild the lesson from scratch route to rebuild_all with recovered topic."""
    res = _heuristic_fallback_classify("תכין את השיעור מחדש", last_lesson_topic="דיני ממונות בשלושה")
    assert res.action == "rebuild_all"
    assert res.target_file is None
    assert res.topic == "דיני ממונות בשלושה"


# ── 2. LLM Classifier with Gemma-3-27B ─────────────────────────────────────────

def test_classify_lesson_followup_llm_call_and_metering():
    """LLM classifier parses JSON, returns decision, and records metering for DISTILLER_MODEL."""
    fake_json = json.dumps({
        "action": "edit_file",
        "target_file": "flow",
        "topic": "סוגיית פועלים בבבא מציעא",
        "instruction": "להוסיף פעילות חקר בשלב השני",
    })
    client = MagicMock()
    client.chat.completions.create.return_value = FakeChatCompletion(fake_json, prompt_tokens=120, completion_tokens=30)

    with metering.meter() as usage:
        decision = classify_lesson_followup(
            "תוסיף פעילות חקר במהלך השיעור",
            last_lesson_topic="פועלים",
            client=client,
        )

    assert decision.action == "edit_file"
    assert decision.target_file == "flow"
    assert decision.topic == "סוגיית פועלים בבבא מציעא"
    assert decision.instruction == "להוסיף פעילות חקר בשלב השני"

    client.chat.completions.create.assert_called_once()
    call_kwargs = client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == DISTILLER_MODEL
    assert call_kwargs["temperature"] == 0.0

    # Metering check for Gemma-3-27B: 120 * 0.40 + 30 * 1.25 = 48 + 37.5 = 86 billed tokens
    assert usage["calls"] == 1
    assert usage["prompt_tokens"] == 120
    assert usage["completion_tokens"] == 30
    assert usage["billed_tokens"] == 86


def test_classify_lesson_followup_fallback_on_invalid_json():
    """When LLM returns non-JSON or fails, fallback cleanly to heuristic classification."""
    client = MagicMock()
    client.chat.completions.create.return_value = FakeChatCompletion("I cannot parse this", prompt_tokens=50, completion_tokens=10)

    decision = classify_lesson_followup(
        "תשנה את מהלך השיעור",
        last_lesson_topic="פסח",
        client=client,
    )
    assert decision.action == "edit_file"
    assert decision.target_file == "flow"
    assert decision.topic == "פסח"


# ── 3. Topic Recovery Tests ───────────────────────────────────────────────────

def test_recover_lesson_topic_from_file_titles():
    """Topic is cleanly recovered from the 'מהלך השיעור — {topic} · {tag}' title format."""
    files = [
        {"name": "דף_מקורות.doc", "title": "דף מקורות — הלכות שבת פרק א · כיתות ד-ו", "content": "מקורות..."},
        {"name": "מהלך_השיעור.doc", "title": "מהלך השיעור — הלכות שבת פרק א · כיתות ד-ו", "content": "מהלך..."},
        {"name": "השיעור_המלא.doc", "title": "שיעור מלא — הלכות שבת פרק א · כיתות ד-ו", "content": "שיעור..."},
    ]
    history = [
        Turn(role="user", text="תכין לי שיעור על שבת"),
        Turn(role="assistant", text="", lesson=True, files=files),
    ]

    topic = _recover_lesson_topic(history)
    assert topic == "הלכות שבת פרק א"


def test_recover_lesson_topic_fallback_to_user_query():
    """If file titles have no delimiter, topic falls back to earliest substantive user query."""
    history = [
        Turn(role="user", text="אני רוצה להכין שיעור על דיני ממונות בשלושה"),
        Turn(role="assistant", text="", lesson=True, files=[]),
    ]
    topic = _recover_lesson_topic(history)
    assert topic == "אני רוצה להכין שיעור על דיני ממונות בשלושה"


# ── 4. Single-File Edit Engine Tests ──────────────────────────────────────────

def test_edit_lesson_file_updates_only_target_file():
    """_edit_lesson_file modifies ONLY the target file, leaving the other two 100% untouched."""
    initial_files = [
        {"name": "דף_מקורות.doc", "title": "דף מקורות — סוכה", "content": "תוכן דף מקורות מקורי [S1]"},
        {"name": "מהלך_השיעור.doc", "title": "מהלך השיעור — סוכה", "content": "מהלך מקורי שלב א [S1]"},
        {"name": "השיעור_המלא.doc", "title": "שיעור מלא — סוכה", "content": "שיעור מלא מקורי בהרחבה [S1]"},
    ]
    initial_cits = [
        CitationOut(ref="Sukkah.2a", ref_he="סוכה ב' ע\"א", text_he="סוכה שהיא גבוהה", text_en="", commentator="", deep_link="", license="CC-BY", version_title="")
    ]
    history = [
        Turn(role="user", text="שיעור על סוכה"),
        Turn(role="assistant", text="", lesson=True, files=initial_files, citations=[c.model_dump() for c in initial_cits]),
    ]

    decision = LessonFollowupDecision(
        action="edit_file",
        target_file="flow",
        topic="סוכה",
        instruction="תקצר את שלב א ל-5 דקות",
    )

    mock_llm = MagicMock()
    mock_llm.request.return_value = ("מהלך מעודכן ומקוצר שלב א 5 דקות [S1]", [])

    with patch("app.db.save_lesson") as mock_save:
        res = _edit_lesson_file(
            question="תקצר את שלב א ל-5 דקות",
            lang="he",
            history=history,
            decision=decision,
            llm=mock_llm,
        )

    # Verify response structure
    assert isinstance(res, QueryResponse)
    assert res.intent == "lesson"
    assert "עדכנתי את מהלך השיעור" in res.answer
    assert len(res.files) == 3

    # Check that flow (index 1) changed
    assert res.files[1].name == "מהלך_השיעור.doc"
    assert res.files[1].content == "מהלך מעודכן ומקוצר שלב א 5 דקות"

    # Check that source sheet (index 0) and full lesson (index 2) are COMPLETELY IDENTICAL
    assert res.files[0].content == initial_files[0]["content"]
    assert res.files[2].content == initial_files[2]["content"]

    # Check citations preserved
    assert len(res.citations) == 1
    assert res.citations[0].ref == "Sukkah.2a"
    assert res.grounded is True

    # Check DB save was called with updated files
    mock_save.assert_called_once()
    saved_files = mock_save.call_args.kwargs.get("files") or mock_save.call_args[0][6]
    assert saved_files[1]["content"] == "מהלך מעודכן ומקוצר שלב א 5 דקות"
    assert saved_files[0]["content"] == initial_files[0]["content"]


def test_edit_lesson_file_full_lesson():
    """Editing full lesson updates only full_lesson.doc and preserves flow and sources."""
    initial_files = [
        {"name": "דף_מקורות.doc", "title": "דף מקורות", "content": "מקורות"},
        {"name": "מהלך_השיעור.doc", "title": "מהלך השיעור", "content": "מהלך"},
        {"name": "השיעור_המלא.doc", "title": "שיעור מלא", "content": "שיעור מלא ישן"},
    ]
    history = [
        Turn(role="assistant", text="", lesson=True, files=initial_files, citations=[]),
    ]

    decision = LessonFollowupDecision(
        action="edit_file",
        target_file="full",
        topic="חנוכה",
        instruction="תוסיף הסבר על מהדרין מן המהדרין",
    )

    mock_llm = MagicMock()
    mock_llm.request.return_value = ("שיעור מלא מעודכן עם מהדרין מן המהדרין", [])

    with patch("app.db.save_lesson"):
        res = _edit_lesson_file(
            question="תוסיף הסבר על מהדרין מן המהדרין",
            lang="he",
            history=history,
            decision=decision,
            llm=mock_llm,
        )

    assert "עדכנתי את השיעור המלא" in res.answer
    assert res.files[2].content == "שיעור מלא מעודכן עם מהדרין מן המהדרין"
    assert res.files[0].content == "מקורות"
    assert res.files[1].content == "מהלך"
