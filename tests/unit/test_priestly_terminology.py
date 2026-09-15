"""Unit tests for priestly terminology sanitization and Beit Midrash prompt register."""

from __future__ import annotations

import pytest

from chavruta.corpus.schema import Citation
from chavruta.generation.grounded import (
    SYSTEM_BASE_HE,
    enforce_citations,
    sanitize_priestly_terms,
)
from chavruta.retrieval.base import RankedHit


def test_system_prompt_includes_torah_register_instruction():
    """SYSTEM_BASE_HE must instruct authentic Beit Midrash register (כהנא = כהן) without mentioning כומר."""
    assert "כהנא = כהן" in SYSTEM_BASE_HE
    assert "כומר" not in SYSTEM_BASE_HE


def test_sanitize_leaves_christian_priest_question_untouched():
    """When the user asks about a Christian priest/church, the term כומר must never be altered."""
    question = "האם מותר ללחוץ יד לכומר או להיכנס לבית כומר?"
    text = "לגבי שאלתך על כומר, ישנם פוסקים שהקלו בלחיצת יד של כומר משום דרכי שלום."
    sources = [RankedHit(chunk_id="c1", ref="Yoreh_Deah.150.1", score=1.0, text="דין כומר ונכרי")]

    cleaned = sanitize_priestly_terms(text, question=question, sources=sources)
    assert cleaned == text
    assert "כומר" in cleaned
    assert "כהן" not in cleaned


def test_sanitize_leaves_christian_sources_untouched():
    """Even if question is neutral, if sources discuss church/monks/priests, כומר is not altered."""
    question = "מה הדין בזה?"
    text = "מדברי הפוסקים עולה שאסור לתת מתנה לכומר של עבודה זרה."
    sources = [RankedHit(chunk_id="c1", ref="Avodah_Zarah.10.1", score=1.0, text="בי כנישתא של נוצרים ודין כומר")]

    cleaned = sanitize_priestly_terms(text, question=question, sources=sources)
    assert cleaned == text
    assert "כומר" in cleaned


def test_sanitize_fixes_priest_hallucination_in_kehuna_context():
    """In a Talmudic Kehuna context (Chullin 133 / matnot kehuna), כומר is corrected to כהן / כהונה."""
    question = "תבחר סוגיה אחת בדף ותסביר לי אותה בפירוט"
    sources = [
        RankedHit(
            chunk_id="c1",
            ref="Chullin.133a",
            score=1.0,
            text="אמר רב יוסף האי כהנא דאית ליה צורבא מרבנן בשבבותיה ליזכי ליה מתנתא",
        )
    ]
    raw_text = (
        "כאן כבר רואים עיקרון חשוב: גם אם הכומר לא יזכה במתנה באופן ישיר, מותר להעניק לו מתנה. "
        "רבא מבקש לזכות את הכומר במתנות. "
        "כל זבח חייב במתנות כומר, והמתנות ניתנות לכומר כדין."
    )

    cleaned = sanitize_priestly_terms(raw_text, question=question, sources=sources)

    assert "הכומר" not in cleaned
    assert "מתנות כומר" not in cleaned
    assert "לכומר" not in cleaned
    assert "גם אם הכהן לא יזכה במתנה" in cleaned
    assert "לזכות את הכהן במתנות" in cleaned
    assert "מתנות כהונה" in cleaned
    assert "ניתנות לכהן" in cleaned


def test_enforce_citations_integrates_sanitization():
    """enforce_citations sanitizes priestly mistranslation when question/sources are Kehuna, but preserves for clergy queries."""
    hit = RankedHit(
        chunk_id="c1",
        ref="Chullin.133a",
        score=1.0,
        text="אמר רב יוסף האי כהנא... מתנתא",
    )
    marker_map = {"S1": hit}

    # Kehuna context: should sanitize
    text_kehuna = "רבא זכה במתנה [S1] עבור הכומר."
    clean_kehuna, cites, grounded = enforce_citations(
        text_kehuna, marker_map, question="מה דעת רב יוסף בחולין?"
    )
    assert "עבור הכהן" in clean_kehuna
    assert "הכומר" not in clean_kehuna

    # Priest context: should NOT sanitize
    hit_clergy = RankedHit(
        chunk_id="c2",
        ref="Yoreh_Deah.150",
        score=1.0,
        text="הלכות עבודה זרה",
    )
    marker_map_clergy = {"S1": hit_clergy}
    text_clergy = 'פסק השו"ע [S1] לגבי כומר.'
    clean_clergy, cites, grounded = enforce_citations(
        text_clergy, marker_map_clergy, question="האם כומר נחשב עובד כוכבים?"
    )
    assert "לגבי כומר" in clean_clergy
    assert "לגבי כהן" not in clean_clergy
