"""Grounded generation + citation enforcement (Constitution Principle I) — task T018.

This module is where grounding is *enforced*, not merely requested:
  • `build_prompt` gives the model ONLY the retrieved sources, each tagged with a marker.
  • `enforce_citations` maps the answer's [S#] markers back to real retrieved chunks, builds
    verifiable Citations, and drops any fabricated marker.
  • `no_source_answer` is the honest empty state when retrieval found nothing relevant.
"""

from __future__ import annotations

import re

from chavruta.corpus.schema import Answer, Citation, Intent, LessonPlan, LessonSection
from chavruta.llm.base import GroundedPrompt, SourceBlock
from chavruta.llm.base import Turn as LLMTurn
from chavruta.retrieval.base import RankedHit

_MARKER_RE = re.compile(r"\[S(\d+)\]")
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Remove reasoning traces emitted by thinking-variant models (e.g. DictaLM-3.0
    Thinking / Qwen3). The user sees the answer, not the scratchpad; citation
    enforcement runs on the final answer only. Harmless for non-thinking models."""
    cleaned = _THINK_RE.sub("", text)
    # Unclosed <think> (generation cut off mid-reasoning) → nothing usable after it.
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>")[0]
    return cleaned.strip()

SYSTEM_QA = (
    "You are Chavruta, a trustworthy Torah study partner. You answer ONLY from the sources "
    "provided to you. Every factual claim MUST cite its source by marker, e.g. [S1]. "
    "Quote the Hebrew source text where relevant. You MUST NOT invent sources, citations, "
    "attributions, or content that is not in the provided sources. If the sources do not "
    "answer the question, say so plainly. Attribute each statement to the correct commentator."
)

SYSTEM_EXPLAIN = SYSTEM_QA + (
    " When explaining or comparing commentators, present each view grounded in that "
    "commentator's words, attribute it correctly, and surface disagreements rather than "
    "flattening them into one opinion."
)

SYSTEM_LESSON = SYSTEM_QA + (
    " When preparing a lesson, produce a clear structure: the key sources to study, a "
    "suggested flow, and discussion points — every source cited by marker."
)

HALACHA_CAVEAT_HE = "הערה: זו אינה פסיקה הלכתית מחייבת ואינה תחליף לרב מוסמך."
HALACHA_CAVEAT_EN = "Note: this is not a binding halachic ruling and is not a substitute for a competent rav."


def _system_for(intent: Intent) -> str:
    if intent in (Intent.EXPLAIN, Intent.COMPARE):
        return SYSTEM_EXPLAIN
    if intent is Intent.LESSON:
        return SYSTEM_LESSON
    return SYSTEM_QA


def build_prompt(
    question: str, hits: list[RankedHit], *, intent: Intent = Intent.QA, history=None
) -> tuple[GroundedPrompt, dict[str, RankedHit]]:
    """Build a grounded prompt and the marker→hit map used to enforce citations."""
    sources: list[SourceBlock] = []
    marker_map: dict[str, RankedHit] = {}
    for i, h in enumerate(hits, start=1):
        marker = f"S{i}"
        marker_map[marker] = h
        sources.append(SourceBlock(
            marker=marker, ref=h.ref, commentator_id=h.commentator_id, text=h.text
        ))
    llm_history = [LLMTurn(role=t.role, text=t.text) for t in (history or [])]
    prompt = GroundedPrompt(
        system=_system_for(intent), sources=sources, question=question, history=llm_history
    )
    return prompt, marker_map


def enforce_citations(
    text: str, marker_map: dict[str, RankedHit]
) -> tuple[str, list[Citation], bool]:
    """Map [S#] markers to real chunks; drop fabricated markers; report grounded-ness.

    Returns (clean_text, citations, grounded). `grounded` is True iff at least one valid
    citation backs the answer (Principle I).
    """
    text = strip_thinking(text)
    used: dict[str, RankedHit] = {}
    fabricated: set[str] = set()
    for m in _MARKER_RE.finditer(text):
        marker = f"S{m.group(1)}"
        if marker in marker_map:
            used[marker] = marker_map[marker]
        else:
            fabricated.add(marker)

    # Remove any fabricated markers from the text (the model referenced a source that
    # was never provided — must not stand).
    clean = text
    for marker in fabricated:
        clean = clean.replace(f"[{marker}]", "")

    citations = [
        Citation(
            chunk_id=h.chunk_id,
            ref=h.ref,
            deep_link=h.deep_link,
            quote=h.text[:280],
            commentator_id=h.commentator_id,
        )
        for h in used.values()
    ]
    grounded = len(citations) > 0
    return clean.strip(), citations, grounded


def work_not_loaded_answer(lang: str, missing_works: list[str], intent: Intent) -> Answer:
    """Honest answer when the question asks about a work that is not in the library yet
    (the spec's out-of-corpus edge case). Similar-sounding hits from other works must not
    masquerade as the requested source (Principle I)."""
    names = ", ".join(missing_works)
    if lang == "he":
        msg = (f"השאלה מתייחסת ל־{names}, שעדיין אינו טעון בספרייה הנוכחית. "
               f"איני עונה ממקור אחר כאילו היה המקור המבוקש — ניתן להוסיף את הקורפוס "
               f"הזה (פעולת data/config) ואז אענה ממנו ישירות.")
    else:
        msg = (f"This question refers to {names}, which is not loaded in the current "
               f"library. I will not answer from a different source as if it were the "
               f"requested one — that corpus can be added (a data/config operation), "
               f"and then I will answer from it directly.")
    return Answer(text=msg, citations=[], grounded=False, no_source=True, intent=intent)


def no_commentator_answer(lang: str, missing: list[str], intent: Intent) -> Answer:
    """Honest answer when every requested commentator lacks a comment here (FR-006/007)."""
    names = ", ".join(missing)
    if lang == "he":
        msg = (f"לא נמצא בקורפוס פירוש של {names} על המקום הזה. "
               f"איני ממציא פירוש — ייתכן שהמפרש לא כתב כאן, או שהטקסט טרם נטען.")
    else:
        msg = (f"No comment by {names} on this passage was found in the corpus. "
               f"I will not invent one — the commentator may not comment here, "
               f"or the text is not loaded yet.")
    return Answer(text=msg, citations=[], grounded=False, no_source=True, intent=intent)


def missing_commentator_note(lang: str, missing: list[str]) -> str:
    names = ", ".join(missing)
    if lang == "he":
        return f"הערה: לא נמצא בקורפוס פירוש של {names} על המקום הזה."
    return f"Note: no comment by {names} on this passage was found in the corpus."


def no_source_answer(lang: str, intent: Intent = Intent.QA) -> Answer:
    if lang == "he":
        msg = ("לא נמצא מקור מעוגן בקורפוס הנוכחי שעונה על השאלה. "
               "איני ממציא תשובה — אפשר לנסח מחדש או להוסיף את המקור הרלוונטי לקורפוס.")
    else:
        msg = ("No grounded source in the current corpus answers this question. "
               "I will not invent one — try rephrasing, or add the relevant corpus.")
    return Answer(text=msg, citations=[], grounded=False, no_source=True, intent=intent)


def build_lesson_plan(topic: str, hits: list[RankedHit]) -> LessonPlan:
    """Structure the retrieved sources into a lesson scaffold (FR-008/008a, task T036/T036a).

    Sections are grouped by anchor pasuk and ordered along the chain of transmission:
    within each section the pasuk comes first, then its commentaries (and, as corpora are
    loaded, Acharonim/Halacha reached via link expansion). Every section carries resolving
    citations; the LLM narrative (discussion points, flow) is generated separately and
    grounded by the same sources.
    """
    by_anchor: dict[str, list[RankedHit]] = {}
    for h in hits:
        anchor = h.anchor_ref or h.ref
        by_anchor.setdefault(anchor, []).append(h)

    sections: list[LessonSection] = []
    for anchor, group in by_anchor.items():
        # pasuk (no commentator) first, then commentaries — the chain order
        group_sorted = sorted(group, key=lambda h: (h.commentator_id is not None, h.work_id))
        sections.append(LessonSection(
            heading=anchor,
            source_refs=[h.ref for h in group_sorted],
            citations=[
                Citation(chunk_id=h.chunk_id, ref=h.ref, deep_link=h.deep_link,
                         quote=h.text[:280], commentator_id=h.commentator_id)
                for h in group_sorted
            ],
        ))
    return LessonPlan(topic=topic, sections=sections)


def maybe_halacha_caveat(answer: Answer, lang: str) -> Answer:
    """Attach the halachic caveat (Principle VIII). Reserved until a halachic corpus exists."""
    if answer.intent is Intent.HALACHA:
        answer.caveats.append(HALACHA_CAVEAT_HE if lang == "he" else HALACHA_CAVEAT_EN)
    return answer
