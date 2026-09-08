"""Unit tests for Part 3: query distillation, normalized token metering, and prompt sandwiching."""

from __future__ import annotations

from unittest.mock import MagicMock

from chavruta.corpus.schema import Intent, Query, Turn
from chavruta.generation import grounded
from chavruta.intents.llm_planner import DISTILLER_MODEL, distill_query
from chavruta.llm import metering
from chavruta.llm.base import GroundedPrompt, SourceBlock, render_messages
from chavruta.retrieval.base import RankedHit


class FakeChatCompletion:
    def __init__(self, content: str, prompt_tokens: int = 50, completion_tokens: int = 15):
        self.choices = [MagicMock(message=MagicMock(content=content))]
        self.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


def _mock_client(return_content: str = "מה דין חמץ בפסח?", p_tokens: int = 50, c_tokens: int = 15):
    client = MagicMock()
    client.chat.completions.create.return_value = FakeChatCompletion(
        return_content, prompt_tokens=p_tokens, completion_tokens=c_tokens
    )
    return client


# ── Distillation tests ─────────────────────────────────────────────────────────

def test_distill_query_short_and_direct_bypasses_llm():
    """Short and direct query (<= 10 words) should return text directly without an LLM call."""
    client = _mock_client()
    text = "מה דין חמץ שעבר עליו הפסח?"
    assert len(text.split()) <= 10

    with metering.meter() as usage:
        result = distill_query(text, client=client)

    assert result == text
    client.chat.completions.create.assert_not_called()
    assert usage["calls"] == 0


def test_distill_query_long_calls_distiller_and_meters():
    """Long query (> 10 words) calls google/gemma-3-27b-it and records metering."""
    client = _mock_client(return_content="האם מותר לטלטל מוקצה בשבת לצורך גופו ומקומו?",
                          p_tokens=60, c_tokens=20)
    text = "שלום רב אשמח לדעת בהרחבה מה ההלכה לגבי טלטול חפץ מוקצה בשבת כאשר יש צורך גדול בגופו או במקומו"
    assert len(text.split()) > 10

    with metering.meter() as usage:
        result = distill_query(text, client=client)

    assert result == "האם מותר לטלטל מוקצה בשבת לצורך גופו ומקומו?"
    client.chat.completions.create.assert_called_once()
    call_kwargs = client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == DISTILLER_MODEL
    assert call_kwargs["temperature"] == 0.0
    # Check metering
    assert usage["prompt_tokens"] == 60
    assert usage["completion_tokens"] == 20
    assert usage["calls"] == 1
    # Billed tokens for distiller: round(60 * 0.40 + 20 * 1.25) = round(24.0 + 25.0) = 49
    assert usage["billed_tokens"] == 49


def test_distill_query_conversational_triggers_distillation():
    """Conversational phrases (אני רוצה לדעת, תוכל להסביר לי) trigger distillation even if short."""
    client = _mock_client(return_content="מהם דיני שמיטה?")
    text = "אני רוצה לדעת על שמיטה"

    result = distill_query(text, client=client)

    assert result == "מהם דיני שמיטה?"
    client.chat.completions.create.assert_called_once()


def test_distill_query_with_history():
    """Distillation incorporates prior conversation turns for follow-ups."""
    client = _mock_client(return_content='טעמו של רש"י באיסור בורר')
    history = [
        Turn(role="user", text="מה ההבדל בין בורר לדש?"),
        Turn(role="assistant", text="בורר הוא הפרדת אוכל מתוך פסולת..."),
    ]
    text = 'ומה לגבי רש"י?'

    result = distill_query(text, history=history, client=client)

    assert result == 'טעמו של רש"י באיסור בורר'
    client.chat.completions.create.assert_called_once()


def test_distill_query_fallback_on_exception():
    """If the LLM client errors, distill_query falls back cleanly to the raw text without crashing."""
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("Nebius API timeout")
    text = "שאלה ארוכה מאוד מאוד מאוד מאוד מאוד מאוד מאוד מאוד מאוד מאוד"

    result = distill_query(text, client=client)

    assert result == text


# ── Prompt Sandwiching tests ──────────────────────────────────────────────────

def test_prompt_sandwiching_in_render_messages_hebrew():
    """When distilled_question is provided, render_messages sandwiches it cleanly in the prompt."""
    sources = [SourceBlock(marker="S1", ref="Genesis.1.1", commentator_id=None, text="בראשית")]
    prompt = GroundedPrompt(
        system="אתה חברותא",
        question="שאלה ארוכה ומסורבלת של משתמש",
        sources=sources,
        distilled_question="מה הפירוש המדויק של בראשית?",
    )
    msgs = render_messages(prompt, "he")
    user_content = msgs[-1]["content"]

    assert "השאלה המקורית:\nשאלה ארוכה ומסורבלת של משתמש" in user_content
    assert "המקורות (הידע היחיד המותר לך):" in user_content
    assert "שאלת המיקוד לתשובה:\nמה הפירוש המדויק של בראשית?" in user_content


def test_prompt_sandwiching_in_render_messages_english():
    """When distilled_question is provided in English, render_messages sandwiches it."""
    sources = [SourceBlock(marker="S1", ref="Genesis.1.1", commentator_id=None, text="In the beginning")]
    prompt = GroundedPrompt(
        system="You are Chavruta",
        question="A long winding question from a learner",
        sources=sources,
        distilled_question="What is the precise meaning of Genesis 1:1?",
    )
    msgs = render_messages(prompt, "en")
    user_content = msgs[-1]["content"]

    assert "ORIGINAL QUESTION:\nA long winding question from a learner" in user_content
    assert "SOURCES (the only knowledge you may use):" in user_content
    assert "FOCUS QUESTION:\nWhat is the precise meaning of Genesis 1:1?" in user_content


def test_build_prompt_carries_distilled_question():
    """grounded.build_prompt stores distilled_question in GroundedPrompt."""
    hit = RankedHit(chunk_id="c1", ref="Genesis.1.1", text="בראשית", score=1.0)
    prompt, _ = grounded.build_prompt(
        "שאלה ארוכה", [hit], distilled_question="שאלה ממוקדת"
    )
    assert prompt.distilled_question == "שאלה ממוקדת"


def test_build_lesson_walkthrough_prompt_carries_distilled_question():
    """grounded.build_lesson_walkthrough_prompt includes distilled_question in the walkthrough lines."""
    from chavruta.corpus.schema import Citation, LessonPlan, LessonSection

    cit = Citation(chunk_id="c1", ref="Genesis.1.1", deep_link="", quote="בראשית ברא")
    sec = LessonSection(heading="פתיחה", citations=[cit])
    plan = LessonPlan(topic="בריאת העולם", template_id="t1", sections=[sec])

    prompt, _ = grounded.build_lesson_walkthrough_prompt(
        plan, "שאלה ארוכה של מורה", lang="he", distilled_question="שאלת מיקוד לשיעור"
    )
    assert prompt.distilled_question == "שאלת מיקוד לשיעור"
    assert "שאלת המיקוד: שאלת מיקוד לשיעור" in prompt.question


def test_pipeline_distills_search_text_for_all_intents():
    """ChavrutaPipeline._resolve_query distills query into search_text and distilled_text for all intents."""
    from chavruta.pipeline.pipeline import ChavrutaPipeline

    pipeline = object.__new__(ChavrutaPipeline)
    pipeline.router = None

    intents = [
        Intent.QA, Intent.EXPLAIN, Intent.COMPARE,
        Intent.HALACHA, Intent.LESSON, Intent.SOURCESHEET, Intent.CHAVRUTA,
    ]
    for intent in intents:
        q = Query(text="מה דין חמץ שעבר עליו הפסח?", intent=intent)
        rq = pipeline._resolve_query(q)
        assert rq.distilled_text == "מה דין חמץ שעבר עליו הפסח?"
        assert rq.search_text == "מה דין חמץ שעבר עליו הפסח?"


def test_pipeline_ask_retrieves_with_distilled_search_text():
    """Pipeline.ask() passes the distilled query to retriever for semantic search across intents."""
    from chavruta.pipeline.pipeline import ChavrutaPipeline

    pipeline = object.__new__(ChavrutaPipeline)
    pipeline.profile = MagicMock()
    pipeline.profile.llm_temperature = 0.0
    pipeline.retriever = MagicMock()
    pipeline.registry = MagicMock()
    pipeline.router = None

    fake_hit = RankedHit(chunk_id="c1", ref="Genesis.1.1", text="בראשית ברא", score=0.9)
    pipeline.retriever.retrieve.return_value = MagicMock(hits=[fake_hit], is_empty=False)

    mock_llm = MagicMock()
    mock_llm.request.return_value = ("תשובה [S1]", [])

    # QA
    q = Query(text="מה דין חמץ שעבר עליו הפסח?", intent=Intent.QA)
    pipeline.ask(q, llm=mock_llm)
    called_query = pipeline.retriever.retrieve.call_args[0][0]
    assert called_query.search_text == "מה דין חמץ שעבר עליו הפסח?"
    assert called_query.distilled_text == "מה דין חמץ שעבר עליו הפסח?"

    # Chavruta
    pipeline.retriever.reset_mock()
    q_chav = Query(text="בוא נלמד על חמץ", intent=Intent.CHAVRUTA)
    pipeline.ask(q_chav, llm=mock_llm)
    called_chav = pipeline.retriever.retrieve.call_args[0][0]
    assert called_chav.search_text == "בוא נלמד על חמץ"
    assert called_chav.distilled_text == "בוא נלמד על חמץ"

    # Sourcesheet
    pipeline.retriever.reset_mock()
    q_ss = Query(text="דף מקורות על חמץ", intent=Intent.SOURCESHEET)
    pipeline.ask(q_ss, llm=mock_llm)
    called_ss = pipeline.retriever.retrieve.call_args[0][0]
    assert called_ss.search_text == "דף מקורות על חמץ"
    assert called_ss.distilled_text == "דף מקורות על חמץ"

