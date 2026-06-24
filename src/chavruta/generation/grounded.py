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
_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")   # any bracket group (may hold several markers)
_SNUM_RE = re.compile(r"S(\d+)")              # an individual source marker inside a bracket
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def source_body(text: str) -> str:
    """Drop the internal "[label] Ref daf:seg" header line a stored document carries, leaving
    the source's actual text. The header is prompt scaffolding (and may hold a pre-correction
    daf label) — never the thing to quote back to the user."""
    if text.startswith("["):
        nl = text.find("\n")
        if nl != -1:
            return text[nl + 1:]
    return text


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
    "suggested flow, and discussion points — every source cited by marker. Match the length "
    "to the lesson's purpose — be as thorough as the topic genuinely needs (a deep sugya may "
    "be long) — but never pad, repeat, or add filler. Stop when the lesson is complete."
)

# Hebrew system prompts — Hebrew-first models follow Hebrew instructions far better
# (Principle IV; measured with DictaLM-3.0-1.7B which looped on the English protocol).
SYSTEM_BASE_HE = (
    "אתה חברותא — שותף לימוד תורה אמין. ענה אך ורק מתוך המקורות שסופקו לך. "
    "כל טענה חייבת ציון מקור בסוגריים, לדוגמה [S1]. צטט את לשון המקור העברית כשרלוונטי. "
    "אסור להמציא מקורות, ציטוטים או ייחוסים שאינם במקורות שסופקו. "
    "אם המקורות אינם עונים על השאלה — אמור זאת בפשטות. ייחס כל דבר לפרשן הנכון."
)

# QA stays short and direct; explain/lesson must NOT inherit that brevity instruction.
SYSTEM_QA_HE = SYSTEM_BASE_HE + " ענה תשובה קצרה וישירה, בלי הקדמות."

SYSTEM_EXPLAIN_HE = SYSTEM_BASE_HE + (
    " כשאתה מסביר או משווה פרשנים — הצג כל שיטה מתוך דברי הפרשן עצמו, ייחס נכון, "
    "והצג מחלוקות כפי שהן, בלי לטשטש."
)

SYSTEM_LESSON_HE = SYSTEM_BASE_HE + (
    " כשאתה מכין שיעור — בנה מבנה ברור: המקורות המרכזיים ללימוד, סדר הלימוד, "
    "ונקודות לדיון — כל מקור עם ציון [S#]. התאם את אורך השיעור למטרתו: הרחב כפי שהנושא "
    "באמת מצריך (סוגיא עמוקה עשויה להיות ארוכה), אבל אל תבזבז טוקנים על מילוי, חזרות "
    "או אריכות מיותרת — סיים כשהשיעור שלם."
)

# Walkthrough: the lesson is delivered as the flowing shiur itself (the "מהלך"), stage by
# stage along the arc, not as a bullet list of sources. Sources still gate every claim.
SYSTEM_LESSON_WALKTHROUGH_HE = SYSTEM_BASE_HE + (
    " אתה מגיד שיעור. כתוב את מהלך השיעור המלא כפרוזה רציפה וזורמת, שלב אחר שלב לפי "
    "הקשת שנמסרה לך: פַתֵּחַ כל כיוון מתוך לשון מקורו (הבא את דברי הפרשן עצמו, ייחס נכון), "
    "הראה את הקושיות והתירוצים, וסכם למסקנות או השאר את הסוגיא פתוחה אם כך היא. זה הטקסט "
    "שהמגיד-שיעור אומר בפועל — לא רשימת מקורות. "
    "אל תפתח בחזרה על השאלה או הנושא — המשתמש שאל זה עתה; גש ישירות אל המקור והדיון. "
    "כל טענה עם [S#], אך ורק מן המקורות שסופקו. התאם את האורך למטרת השיעור, בלי מילוי."
)
SYSTEM_LESSON_WALKTHROUGH = SYSTEM_QA + (
    " You are a maggid shiur. Write the full lesson as flowing prose, stage by stage along "
    "the given arc: open from the opening source and pose the question, develop each "
    "direction from its own source's language (attribute correctly), show the difficulties "
    "and resolutions, and converge to conclusions — or leave the sugya open if it is. This "
    "is the lesson as actually delivered, not a list of sources. Cite every claim with [S#], "
    "only from the provided sources. Right-size the length to the lesson's purpose; no filler."
)

# Responsa (שו"ת) voice — the answer is a teshuva: source & framing → the poskim's positions
# → a clear ruling le-ma'aseh (or an honest "depends / ask a rav"). Same grounding discipline.
SYSTEM_SHUT_WALKTHROUGH_HE = SYSTEM_BASE_HE + (
    " אתה משיב הלכתי. כתוב את התשובה כתשובת שו\"ת רציפה, שלב אחר שלב לפי הקשת שנמסרה: פתח "
    "מן המקור והגדרת הנדון, הצג את שיטות הראשונים והפוסקים מתוך לשונם (ייחס נכון), שקול את "
    "הצדדים, והכרע למעשה בבירור — או ציֵין בכנות היכן הדבר תלוי וצריך שאלת חכם. "
    "אל תפתח בחזרה על השאלה — השואל שאל זה עתה; גש ישירות אל המקור והדיון. "
    "כל טענה עם [S#], אך ורק מן המקורות שסופקו; אל תמציא פסק שאינו עולה מהם."
)
SYSTEM_SHUT_WALKTHROUGH = SYSTEM_QA + (
    " You are a halachic respondent (a posek). Write the answer as a flowing teshuva, stage "
    "by stage along the given arc: open from the source and framing of the matter, present "
    "the rishonim and poskim from their own language (attribute correctly), weigh the sides, "
    "and rule clearly le-ma'aseh — or honestly say where it depends and a rav must be asked. "
    "Do not restate the question — the asker just asked it; go straight to the source and the "
    "discussion. Cite every claim with [S#], only from the provided sources; invent no ruling."
)

HALACHA_CAVEAT_HE = "הערה: זו אינה פסיקה הלכתית מחייבת ואינה תחליף לרב מוסמך."
HALACHA_CAVEAT_EN = "Note: this is not a binding halachic ruling and is not a substitute for a competent rav."


def _system_for(intent: Intent, lang: str = "en") -> str:
    if lang == "he":
        if intent in (Intent.EXPLAIN, Intent.COMPARE):
            return SYSTEM_EXPLAIN_HE
        if intent is Intent.LESSON:
            return SYSTEM_LESSON_HE
        return SYSTEM_QA_HE
    if intent in (Intent.EXPLAIN, Intent.COMPARE):
        return SYSTEM_EXPLAIN
    if intent is Intent.LESSON:
        return SYSTEM_LESSON
    return SYSTEM_QA


MAX_SOURCE_CHARS = 600   # keep prompts small-model-friendly; citations carry the deep-link


def build_prompt(
    question: str, hits: list[RankedHit], *, intent: Intent = Intent.QA, history=None,
    lang: str = "en",
) -> tuple[GroundedPrompt, dict[str, RankedHit]]:
    """Build a grounded prompt and the marker→hit map used to enforce citations."""
    sources: list[SourceBlock] = []
    marker_map: dict[str, RankedHit] = {}
    for i, h in enumerate(hits, start=1):
        marker = f"S{i}"
        marker_map[marker] = h
        text = h.text if len(h.text) <= MAX_SOURCE_CHARS else h.text[:MAX_SOURCE_CHARS] + "…"
        sources.append(SourceBlock(
            marker=marker, ref=h.ref, commentator_id=h.commentator_id, text=text
        ))
    llm_history = [LLMTurn(role=t.role, text=t.text) for t in (history or [])]
    prompt = GroundedPrompt(
        system=_system_for(intent, lang), sources=sources, question=question,
        history=llm_history,
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

    # A bracket group may hold one or more markers in any separator the model picks:
    # "[S1]", "[S1, S2]", "[S1; S3]", "[S1 S2]" — extract every S# from each bracket.
    for bm in _BRACKET_RE.finditer(text):
        for n in _SNUM_RE.findall(bm.group(1)):
            marker = f"S{n}"
            if marker in marker_map:
                used[marker] = marker_map[marker]

    # Rebuild each bracket keeping only valid markers; drop wholly-fabricated brackets
    # (the model referenced a source that was never provided — must not stand).
    def _clean_bracket(bm: "re.Match") -> str:
        nums = _SNUM_RE.findall(bm.group(1))
        if not nums:
            return bm.group(0)                       # not a citation bracket — leave as-is
        valid = [f"S{n}" for n in nums if f"S{n}" in marker_map]
        return f"[{', '.join(valid)}]" if valid else ""

    clean = _BRACKET_RE.sub(_clean_bracket, text)

    citations = [
        Citation(
            chunk_id=h.chunk_id,
            ref=h.ref,
            deep_link=h.deep_link,
            # marker_map values may be RankedHit (.text) or Citation (.quote)
            quote=source_body(getattr(h, "text", None) or getattr(h, "quote", "") or "")[:280],
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


def build_lesson_walkthrough_prompt(plan: LessonPlan, question: str, lang: str = "he",
                                    shut: bool = False):
    """Prompt the model to deliver the lesson — or responsa (`shut=True`) — as a flowing
    walkthrough (the "מהלך"), laying out the arc's stages in order with sources as [S#].

    Returns (GroundedPrompt, marker_map) — marker_map values are the plan's Citations, so
    enforce_citations resolves the cited sources and lets the caller keep only those.
    """
    seen: dict[str, str] = {}
    sources: list[SourceBlock] = []
    marker_map: dict[str, Citation] = {}
    stages: list[tuple[str, list[str]]] = []
    for sec in plan.sections:
        markers: list[str] = []
        for cit in sec.citations:
            m = seen.get(cit.chunk_id)
            if m is None:
                m = f"S{len(seen) + 1}"
                seen[cit.chunk_id] = m
                marker_map[m] = cit
                text = cit.quote or ""
                if len(text) > MAX_SOURCE_CHARS:
                    text = text[:MAX_SOURCE_CHARS] + "…"
                sources.append(SourceBlock(marker=m, ref=cit.ref,
                                           commentator_id=cit.commentator_id, text=text))
            markers.append(m)
        stages.append((sec.heading, markers))

    if lang == "he":
        lines = [f"(הקשר בלבד — אל תחזור על זה) הנושא שנשאל: {question}",
                 "", "שלבי המהלך, לפי הסדר:"]
        lines += [f"• {h} — מקורות: {', '.join(ms) if ms else '—'}" for h, ms in stages]
        lines += ["", "כתוב כעת את המהלך המלא לפי השלבים — פתח ישר מן המקור, בלי לחזור על השאלה."]
        system = SYSTEM_SHUT_WALKTHROUGH_HE if shut else SYSTEM_LESSON_WALKTHROUGH_HE
    else:
        lines = [f"(context only — do not restate it) The question asked: {question}",
                 "", "Arc, in order:"]
        lines += [f"• {h} — sources: {', '.join(ms) if ms else '—'}" for h, ms in stages]
        lines += ["", "Now write the full walkthrough following these stages — open straight "
                  "from the source, without restating the question."]
        system = SYSTEM_SHUT_WALKTHROUGH if shut else SYSTEM_LESSON_WALKTHROUGH
    prompt = GroundedPrompt(system=system, sources=sources, question="\n".join(lines), history=[])
    return prompt, marker_map


def prune_lesson_to_cited(plan: LessonPlan, citations: list[Citation]) -> LessonPlan:
    """Keep, in each section, only the sources the walkthrough actually cited — the lesson
    holds the material it uses, not every retrieved hit. Sections left empty are dropped.
    If nothing was cited (ungrounded), the arc is returned unchanged."""
    cited = {c.chunk_id for c in citations}
    if not cited:
        return plan
    sections: list[LessonSection] = []
    for s in plan.sections:
        kept = [c for c in s.citations if c.chunk_id in cited]
        if kept:
            sections.append(LessonSection(heading=s.heading, role=s.role,
                                          source_refs=[c.ref for c in kept], citations=kept))
    if not sections:
        return plan
    is_open = not any(s.role == "convergence" for s in sections)
    return LessonPlan(topic=plan.topic, sections=sections,
                      template_id=plan.template_id, is_open=is_open)


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
