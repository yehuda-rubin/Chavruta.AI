"""Grounded generation + citation enforcement (Constitution Principle I) — task T018.

This module is where grounding is *enforced*, not merely requested:
  • `build_prompt` gives the model ONLY the retrieved sources, each tagged with a marker.
  • `enforce_citations` maps the answer's [S#] markers back to real retrieved chunks, builds
    verifiable Citations, and drops any fabricated marker.
  • `no_source_answer` is the honest empty state when retrieval found nothing relevant.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from chavruta.corpus.refs import COMMENTATOR_HE, commentator_from_ref, commentator_title
from chavruta.corpus.schema import Answer, Citation, Intent, LessonPlan, LessonSection
from chavruta.llm.base import GroundedPrompt, SourceBlock
from chavruta.llm.base import Turn as LLMTurn
from chavruta.retrieval.base import RankedHit

_MARKER_RE = re.compile(r"\[S(\d+)\]")
_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")   # any bracket group (may hold several markers)
_SNUM_RE = re.compile(r"S(\d+)")              # an individual source marker inside a bracket
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def marker_numbers_in(text: str) -> list[int]:
    """Every [S#] marker number in `text`, across every bracket shape the model actually uses —
    "[S1]", "[S1, S2]", "[S1; S3]", and non-standard ones like "[source S1]" (the bracket content
    only needs S# to appear SOMEWHERE inside it, not be the whole content).

    Exists so a caller outside enforce_citations does not reinvent this extraction with a
    narrower regex. app/api.py::_generate_chavruta_turn used to do exactly that (a bare
    `\\[\\s*S(\\d+)\\s*\\]`), which missed "[source S1]" outright — found live 2026-08-19 in a real
    answer (session 11190b1b) that credited a citation to a marker its own narrower regex never
    even saw, silently dropping it from the citation list instead of resolving or rejecting it."""
    nums: list[int] = []
    for bm in _BRACKET_RE.finditer(text or ""):
        nums.extend(int(n) for n in _SNUM_RE.findall(bm.group(1)))
    return nums


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
    "answer the question, say so plainly. Attribute each statement to the correct commentator. "
    "When a claim characterizes a specific real, identifiable person (a historical figure, a "
    "posek, a living or recently-deceased rabbi) — especially their conduct, motives, or "
    "character — stay close to that source's own wording rather than your own paraphrase, and "
    "do not add evaluative or judgmental language the source itself does not state. "
    "The interface renders plain text plus **bold** and line breaks ONLY — never use Markdown "
    "headers (#, ##, ###) or leading '>' blockquote lines; they show up as literal, ugly "
    "characters. Use a **bold** phrase instead of a header, and put quotes inline in regular "
    "quotation marks, not on their own '>' line. If a source's own text is in a different "
    "language than your answer (e.g. an English-translated responsum in an otherwise-Hebrew "
    "answer), translate it into the answer's language rather than quoting it verbatim in the "
    "other language — the citation marker still links the reader to the original. "
    "Do not require a literal word-match between the question and a source: if the question is "
    "about a modern case or a term that never appears verbatim in the sources (a device, a "
    "situation, a present-day action), infer the underlying principle FROM the sources you were "
    "given and apply it to the case asked — the way a real posek reasons from precedent — rather "
    "than only answering when the exact case is named. That kind of inference (a fortiori, a "
    "shared underlying principle) is legitimate as long as every step still traces back to what a "
    "provided source actually says — it is not the same as inventing a source or a ruling that "
    "doesn't follow from them. "
    "This is one continuous conversation, not a series of unrelated questions. Read the "
    "conversation so far before answering: a short follow-up ('and what about…', 'why?') refers to "
    "what was just discussed, and the sources already quoted earlier still count — don't make the "
    "user repeat themselves. Each turn, choose deliberately: answer from what you already have "
    "(this conversation and its sources) if that genuinely suffices; ask for more sources if it "
    "doesn't; or, when the request is truly ambiguous and the answer would differ materially "
    "depending on the reading, ask the user one short clarifying question instead of guessing."
)

SYSTEM_EXPLAIN = SYSTEM_QA + (
    " When explaining or comparing commentators, present each view grounded in that "
    "commentator's words, attribute it correctly, and surface disagreements rather than "
    "flattening them into one opinion. But do not treat 'is there a dispute?' as a yes/no "
    "question: very often two commentators are not disagreeing at all but speaking on different "
    "levels — one about the spiritual dimension and the other the physical, one peshat and the "
    "other derash, one the cause and the other the effect. Where the sources show two directions "
    "that do not contradict, present them as exactly that and say plainly that these are "
    "complementary layers rather than opposed opinions — that is itself the reconciliation when "
    "one is asked for. And never answer 'no dispute was found' merely because no source used the "
    "word 'disagrees': show what each one says, and where precisely they part."
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
    "אם המקורות אינם עונים על השאלה — אמור זאת בפשטות. ייחס כל דבר לפרשן הנכון. "
    "כשטענה מתארת דמות מזוהה וממשית (דמות היסטורית, פוסק, רב חי או שנפטר לאחרונה) — במיוחד "
    "לגבי התנהגותו, כוונותיו או אופיו — הישאר קרוב ללשון המקור עצמו ולא לניסוח חופשי משלך, "
    "ואל תוסיף הערכה או שיפוט שאינם עולים מן המקור עצמו. "
    "הממשק מציג טקסט רגיל ועוד **מודגש** וירידות שורה בלבד — לעולם אל תשתמש בכותרות Markdown "
    "(#, ##, ###) או בשורת ציטוט שמתחילה ב-'>'; הם מוצגים כתווים גולמיים ומכוערים. השתמש "
    "בביטוי **מודגש** במקום כותרת, והבא ציטוטים בתוך הטקסט במרכאות רגילות, לא בשורת '>' נפרדת. "
    "אם לשון מקור מסוים כתובה בשפה שונה משפת התשובה (למשל תשובה שתורגמה לאנגלית, בתוך תשובה "
    "בעברית) — תרגם אותה לשפת התשובה במקום לצטט אותה כלשונה בשפה הזרה; סימון ה-[S#] עדיין "
    "מקשר את הקורא למקור המקורי. "
    "אל תדרוש התאמת-מילים מילולית בין השאלה למקור: אם השאלה עוסקת במקרה מודרני או במונח שלא "
    "מופיע כלשונו במקורות (מכשיר, מצב, או פעולה עכשווית) — הסק את העיקרון העולה מן המקורות "
    "שסופקו והחל אותו על המקרה הנשאל, כפי שפוסק אמיתי מסיק מתקדים, ולא רק כשהמקרה עצמו נזכר "
    "במפורש. הסקה כזו (קל וחומר, עיקרון משותף) לגיטימית כל עוד כל צעד בה נשען בפועל על לשון "
    "מקור שסופק — וזה שונה לגמרי מהמצאת מקור או פסק שאינו עולה מהם. "
    "זו שיחה אחת מתמשכת, לא רצף שאלות מנותקות. קרא את השיחה שעד כה לפני שאתה עונה: שאלת המשך "
    "קצרה ('ומה אם…', 'למה?') מתייחסת למה שנדון זה עתה, והמקורות שכבר הובאו קודם עדיין עומדים — "
    "אל תגרום למשתמש לחזור על עצמו. בכל תור בחר במודע: ענה ממה שכבר יש לך (השיחה הזו והמקורות "
    "שבה) אם זה באמת מספיק; בקש מקורות נוספים אם לא; או, כשהבקשה באמת דו-משמעית והתשובה תשתנה "
    "מהותית לפי הפירוש — שאל את המשתמש שאלת הבהרה אחת קצרה במקום לנחש."
)

# QA stays short and direct; explain/lesson must NOT inherit that brevity instruction.
SYSTEM_QA_HE = SYSTEM_BASE_HE + " ענה תשובה קצרה וישירה, בלי הקדמות."

SYSTEM_EXPLAIN_HE = SYSTEM_BASE_HE + (
    " כשאתה מסביר או משווה פרשנים — הצג כל שיטה מתוך דברי הפרשן עצמו, ייחס נכון, "
    "והצג מחלוקות כפי שהן, בלי לטשטש. "
    "אבל אל תתייחס ל'מחלוקת' כשאלת כן/לא: הרבה פעמים שני פרשנים אינם חולקים כלל אלא מדברים "
    "ברבדים שונים — האחד בכיוון הרוחני והשני בגשמי, האחד בפשט והשני בדרש, האחד בסיבה והשני "
    "בתוצאה. אם המקורות מראים שני כיוונים שאינם סותרים — הצג אותם ככאלה ואמור במפורש שאין כאן "
    "חולקים אלא רבדים משלימים; זהו גם היישוב עצמו כשמבקשים ליישב. ואל תאמר 'לא נמצאה מחלוקת' "
    "רק משום שאף מקור לא כתב את המילה 'חולק' — הַראה מה כל אחד אומר, ובמה בדיוק הם נבדלים."
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


MAX_SOURCE_CHARS = 1500  # Talmud/Rishonim/responsa segments often exceed 600 and the relevant clause
#                          sits past the cut, starving grounding; the bridge (Claude) and Llama-3.3
#                          (128k ctx) have ample room. Citations still carry the full text + deep-link.


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
    def _clean_bracket(bm: re.Match) -> str:
        nums = _SNUM_RE.findall(bm.group(1))
        if not nums:
            return bm.group(0)                       # not a citation bracket — leave as-is
        valid = [f"S{n}" for n in nums if f"S{n}" in marker_map]
        return f"[{', '.join(valid)}]" if valid else ""

    clean = _BRACKET_RE.sub(_clean_bracket, text)

    citations = [
        Citation(
            # marker_map values may be RankedHit / Citation / SourceBlock (agentically-fetched) —
            # read every field defensively so any of them resolves.
            chunk_id=getattr(h, "chunk_id", "") or "",
            ref=h.ref,
            deep_link=getattr(h, "deep_link", "") or "",
            # Full source text (no truncation) — the UI shows the complete quote on expand.
            quote=source_body(getattr(h, "text", None) or getattr(h, "quote", "") or ""),
            commentator_id=getattr(h, "commentator_id", None),
        )
        for h in used.values()
    ]
    grounded = len(citations) > 0
    return clean.strip(), citations, grounded


_NIQQUD_RE = re.compile(r"[֑-ׇ]")            # Hebrew vowels + cantillation
_NONHEB_RE = re.compile(r"[^א-ת]")           # keep only Hebrew letters
_QUOTE_RE = re.compile(r'["“„״]([^"“”״\n]{12,})["”״]')  # gershayim / quote marks

# A gershayim/" sitting directly between two Hebrew letters (no space either side) is almost always
# a Hebrew ABBREVIATION mark (ר"ה, ואע"ג, סק"א…), not a quote boundary — real quote marks are always
# preceded or followed by whitespace/punctuation (the start/end of the quoted span). _QUOTE_RE can't
# tell the two apart on its own, so a quote spanning source text that itself contains an abbreviation
# (extremely common in halachic sources) gets split at the abbreviation's internal mark, producing a
# truncated fragment that then — correctly, but for the wrong reason — fails the corpus-containment
# check: a real, faithfully-quoted source gets flagged as fabricated. _protect_abbreviations masks
# those internal marks before matching so only genuine quote boundaries are treated as delimiters.
#
# "between two Hebrew letters" alone is NOT enough, though, and getting that wrong cost the guard its
# teeth. Hebrew attaches one-letter prefixes straight onto an opening quote — ש"אסור לטלטל…",
# ו"היה אם שמוע…", ה"כלל הגדול…" — and that opening mark also sits between two Hebrew letters. Masking
# it deleted the opening delimiter, so the whole quotation went invisible to the checker and a
# FABRICATED quote written that way passed unflagged (reproduced 2026-08-11 on realistic halachic
# prose). A false negative here is far worse than the false positive the mask was added for.
#
# What separates the two is what FOLLOWS the mark: an abbreviation ends almost immediately (רש"י,
# רמב"ם, שו"ע, ב"ק — one letter, occasionally two), while a quotation runs on into a word. So the
# mask applies only when at most two Hebrew letters remain before the next boundary.
_ABBREV_MARK_RE = re.compile(r'(?<=[א-ת])["״](?=[א-ת]{1,2}(?![א-ת]))')


def _protect_abbreviations(s: str) -> str:
    return _ABBREV_MARK_RE.sub("", s)  # 1-for-1 so positions still line up with the original


def _heb_skeleton(s: str) -> str:
    return _NONHEB_RE.sub("", _NIQQUD_RE.sub("", s or ""))


def unverified_quotes(text: str, sources, min_len: int = 14) -> list[str]:
    """Citation-faithfulness guard: return VERBATIM Hebrew quotes in `text` (inside quote marks) whose
    opening does NOT appear in any retrieved source — a strong sign the quote was fabricated or drifted
    from its source. Paraphrase is not checked; only quoted spans must actually exist in the corpus.
    Cheap (string only), so it can run on every grounded answer."""
    corpus = _heb_skeleton(" ".join((getattr(s, "text", None) or getattr(s, "quote", "") or "")
                                    for s in (sources or [])))
    if not corpus:
        return []
    text = text or ""
    bad = []
    for start, end in _quoted_spans(_protect_abbreviations(text)):
        raw = text[start:end]             # same span, original characters (abbreviation marks intact)
        q = _heb_skeleton(raw)
        if len(q) >= min_len and q[:min_len] not in corpus:   # opening not found in any source
            bad.append(raw.strip()[:60])
    return bad


def _quoted_spans(masked: str) -> list[tuple[int, int]]:
    """Spans between quote marks, paired IN ORDER — 1st with 2nd, 3rd with 4th, and so on.

    The regex this replaces let any mark pair with any later mark, so one short quoted word threw
    the parity off and every following pair was wrong: the guard then reported the model's OWN prose
    as a fabricated quote. Real examples from a 26-question run —
        "(ייאוש, ויתור על החפץ) כבר קיים באופן עקרוני"      ← not a quote at all
        "מתייחסת לכל ערי ארץ ישראל חוץ מירושלים [S14], והתקנה הורחבה"
    Sequential pairing is how quotation actually nests in a sentence, and it keeps the parity honest.

    A span containing a citation marker is never a quote: [S#] markers are written by the model
    AROUND its sources, never inside one, so a span that swallows one is a mis-pairing by
    construction. Same for a span crossing a line break.
    """
    marks = [i for i, ch in enumerate(masked) if ch in '"“”„״']
    spans: list[tuple[int, int]] = []
    for a, b in zip(marks[0::2], marks[1::2]):
        inner_start, inner_end = a + 1, b
        inner = masked[inner_start:inner_end]
        if "\n" in inner or _MARKER_RE.search(inner):
            continue
        # An ELLIPSIS means the writer abridged — the span is deliberately not verbatim, so holding
        # it to a verbatim-containment check reports honest abridgement as fabrication.
        if "…" in inner or "..." in inner:
            continue
        # A span opening on punctuation or markdown is a mis-pairing, not a quotation: no one starts
        # a quote with a comma or a dash. (", בניגוד לניסיונות האחרים…", "– כלומר, די בהשערה…")
        if inner.lstrip()[:1] in {",", "–", "-", ":", ";", ".", "*", ")"}:
            continue
        spans.append((inner_start, inner_end))
    return spans


# ── Attribution faithfulness: the quote is real — but is it THIS commentator's? ─────────────────
# `unverified_quotes` only asks whether a quoted span exists in SOME retrieved source. That leaves a
# hole with teeth, reproduced 2026-08-13 against these very functions with two Sukkah 41a chunks:
#
#     רש"י כותב במפורש [S1]: "ולעולם יבנה בידי אדם ואין סתירה בין הדברים"
#
# where that wording is the TOSAFOT chunk's, not Rashi's. Every guard passed — the marker resolved,
# `grounded` was True, `unverified_quotes` returned []. The reader was shown a fabrication in the one
# dimension a beis midrash cares about most: who said it. Quoting a real source under the wrong name
# is not a lesser error than inventing one; it is the same error wearing a citation.
#
# The whole design here is biased toward SILENCE. A false positive — telling a user that a faithful,
# correctly-attributed answer misquotes a commentator — would destroy trust in the guard and get it
# switched off, at which point it catches nothing at all. So every ambiguity below resolves to "say
# nothing", and the check fires only when the mismatch is demonstrable against the sources the model
# was actually handed.

# Sefaria/corpus commentator ids are the join key on both sides: the source side derives its id from
# the ref (`commentator_from_ref` — the payload field is empty on all 2.4M points), and the prose side
# resolves a Hebrew/English NAME to the same id. Two name tables already exist and neither alone is
# enough: refs.COMMENTATOR_HE is broad (tosafot, ran, meiri, bartenura…) but holds one spelling each,
# while router.COMMENTATOR_ALIASES carries the gershayim-less and English variants a model actually
# writes (רשי / רמבן / "Rashi"). Merged, with collisions dropped — see `_attribution_aliases`.
_GERSHAYIM_TRANS = str.maketrans({"״": '"', "”": '"', "“": '"', "„": '"'})

_ATTR_WINDOW = 60   # chars of prose before the opening quote that count as its introduction
_ATTR_TRAIL = 40    # …and after the closing one, for a trailing "(תוספות שם)" attribution
_ATTR_BREAKS = ("\n", ". ", "! ", "? ")   # a name in a PREVIOUS sentence introduces nothing here

_attr_aliases: list[tuple[re.Pattern[str], str]] | None = None


def _alias_pattern(alias: str) -> re.Pattern[str]:
    """A whole-word matcher for one commentator name, tolerating Hebrew's glued one-letter prefixes.

    Mirrors intents/router.py::_alias_hit, including its warning: ש is NOT a safe prefix on a bare
    name, because 'שרשי' would then match 'רשי' (and 'שרשי' is an ordinary word). It IS safe on a name
    carrying gershayim — no Hebrew word contains one — and 'שרש"י כותב' is how a model writes it, so
    the prefix set widens only for those.
    """
    a = alias.strip().translate(_GERSHAYIM_TRANS)
    if re.search(r"[א-ת]", a):
        pre = "והבכלמש" if '"' in a else "והבכלמ"
        return re.compile(f"(?<![א-ת])[{pre}]{{0,2}}{re.escape(a)}(?![א-ת])")
    return re.compile(rf"(?<![a-z]){re.escape(a.lower())}(?![a-z])", re.IGNORECASE)


def _attribution_aliases() -> list[tuple[re.Pattern[str], str]]:
    """name-pattern → commentator id, built once from the two existing tables.

    A name claimed by TWO different ids is dropped rather than resolved to either — 'תרגום יונתן' is
    both `targum_yonatan` (refs) and `targum_jonathan` (router), and picking the loser would invent a
    mismatch against a source that is in fact exactly the work named: a false positive manufactured
    out of our own duplicate bookkeeping.
    """
    global _attr_aliases
    if _attr_aliases is None:
        # Lazy: the intent layer is a peer of generation, not a dependency of it — importing it at
        # module scope would make `generation` un-importable on its own the day router grows an import.
        from chavruta.intents.router import COMMENTATOR_ALIASES

        by_name: dict[str, str | None] = {}

        def _put(name: str, cid: str) -> None:
            n = (name or "").strip().translate(_GERSHAYIM_TRANS)
            if not n:
                return
            if n in by_name and by_name[n] != cid:
                by_name[n] = None                       # ambiguous → refuse to resolve it at all
            else:
                by_name.setdefault(n, cid)

        for cid, he in COMMENTATOR_HE.items():
            _put(he, cid)
        for cid, aliases in COMMENTATOR_ALIASES.items():
            for a in aliases:
                _put(a, cid)
        _attr_aliases = [(_alias_pattern(n), cid) for n, cid in by_name.items() if cid]
    return _attr_aliases


def _names_in(window: str) -> set[str]:
    return {cid for pat, cid in _attribution_aliases() if pat.search(window)}


def _attribution_window(text: str, start: int) -> str:
    """The prose that introduces the quote opening at `start`: back to the previous sentence end."""
    win = text[max(0, start - _ATTR_WINDOW):start]
    cut = 0
    for b in _ATTR_BREAKS:
        i = win.rfind(b)
        if i != -1:
            cut = max(cut, i + len(b))
    return win[cut:]


class Misattribution(NamedTuple):
    """A quoted span whose prose credits one commentator while the words belong to another.

    `found_in` is the id(s) of the retrieved source(s) that actually carry the wording — plural
    because two commentaries can share a phrase, and reporting all of them keeps the note honest.
    """

    quote: str
    claimed: str
    found_in: tuple[str, ...]


def misattributed_quotes(text: str, sources, min_len: int = 24) -> list[Misattribution]:
    """Attribution guard: verbatim quotes credited to a named commentator whose words they are not.

    Complements `unverified_quotes` and never overlaps it: a quote found in NO source is that
    function's finding and is skipped here, so a single fabrication is never reported twice.

    Fires ONLY when all of the following hold — each condition removed a class of false positive:
      • the quoted span is long enough to identify a source (≥ `min_len` Hebrew letters);
      • it is carried by at least one retrieved source, and by no BASE text. A commentator quoting
        the pasuk or daf he is commenting on is the normal shape of Torah prose, not a misquote, and
        base texts have no commentator to disagree with (constraint: never flag a bare pasuk);
      • exactly ONE commentator is named in the introducing sentence. 'רש"י ותוספות נחלקו… וכתב: "…"'
        is genuinely ambiguous about whose words follow, and guessing there is how a guard earns a
        reputation for crying wolf;
      • that commentator is not among the sources holding the quote, and is not named again right
        after the quote ('…" (תוספות שם)' is a trailing attribution, not a contradiction);
      • a source BY the named commentator was actually retrieved. This is the strictest condition and
        the reason the finding is worth showing: the model had that commentator's own text in front of
        it, and the words it put in his mouth are visibly someone else's. Without a source by him we
        cannot distinguish a misquote from a nested attribution ('כפי שהביא הרמב"ן בשם רש"י') or from
        an author quoting his own dibbur hamatchil, so we stay quiet.

    Consequently this is blind to works filed WITHOUT the '<Title>_on_<Base>' commentary form —
    Shulchan Arukh, Mishnah Berurah, Mishneh Torah — because `commentator_from_ref` correctly yields
    None for them and they are treated as base texts. Widening that would mean guessing an author out
    of a work title, which is exactly the guesswork this guard refuses elsewhere.
    """
    text = text or ""
    # Derive each source's commentator from its ref, NOT from the payload field: `commentator_id` is
    # empty on every point in the commercial corpus and is a read-time derivation (docs/CORPUS.md
    # §7.2b). The payload is still consulted as a fallback for sources built by other paths.
    by_cid: list[tuple[str | None, str]] = []
    for s in (sources or []):
        body = getattr(s, "text", None) or getattr(s, "quote", "") or ""
        cid = commentator_from_ref(getattr(s, "ref", "") or "") or (
            getattr(s, "commentator_id", None) or None)
        by_cid.append((cid, _heb_skeleton(body)))
    retrieved = {cid for cid, _ in by_cid if cid}
    if not retrieved:
        return []

    # Quote-mark variants folded to ASCII so a name written רש״י resolves like רש"י. 1-for-1, so the
    # span offsets computed on the original text still index this string correctly.
    normalized = text.translate(_GERSHAYIM_TRANS)

    out: list[Misattribution] = []
    for start, end in _quoted_spans(_protect_abbreviations(text)):
        raw = text[start:end]
        q = _heb_skeleton(raw)
        if len(q) < min_len:
            continue
        key = q[:min_len]
        holders = {cid for cid, skel in by_cid if key in skel}
        if not holders or None in holders:
            continue
        named = _names_in(_attribution_window(normalized, start))
        if len(named) != 1:
            continue
        claimed = next(iter(named))
        if claimed in holders or claimed not in retrieved:
            continue
        if _names_in(normalized[end + 1:end + 1 + _ATTR_TRAIL].split("\n")[0]) & holders:
            continue
        out.append(Misattribution(raw.strip()[:60], claimed, tuple(sorted(str(c) for c in holders))))
    return out


class MismatchedCitation(NamedTuple):
    """A quoted Hebrew phrase cited with two different Tanakh chapter:verse refs in the same
    answer — one confirmed against the phrase by the corpus, the other contradicted by it."""

    phrase: str
    correct_ref: str
    wrong_ref: str


def mismatched_tanakh_citations(text: str, fetch_refs) -> list[MismatchedCitation]:
    """Citation guard: a Hebrew phrase cited with a chapter:verse ref that contradicts what the
    SAME phrase is cited as elsewhere in the same answer, where the corpus itself can say which one
    is right.

    Caught live 2026-08-20: one real QA answer quoted "והאבדתי את הנפש ההיא" correctly as
    (ויקרא כג,ל) earlier in the response, then cited the identical phrase as (ויקרא יג,ל) — Leviticus
    13, tzaraat, unrelated — a few lines later. `unverified_quotes` did not catch this: the quoted
    words genuinely ARE in the retrieved Gemara, verbatim. What was wrong is the PARENTHETICAL
    CROSS-REFERENCE back to the Torah pasuk itself, which is not an [S#]-marked citation at all and
    is not what `unverified_quotes` checks.

    Deliberately conservative: this fires ONLY when a citation's own ref shows almost NO n-gram
    overlap with the text around it, while a DIFFERENT ref cited elsewhere in the same answer shows
    clear overlap — i.e. only when the corpus itself can be fetched and shown to confirm one
    candidate and contradict the other. A citation with no such internal contradiction is never
    flagged — there is nothing here confident enough to call it wrong on its own, only "this answer
    disagrees with itself, and the corpus can settle which side is right."

    n-gram overlap, not an exact substring match: reproduced live, even the CORRECT citation in the
    2026-08-20 case was not a verbatim quote of the pasuk (word order shifted, one word swapped for
    a similar-sounding one) — an LLM paraphrasing/misremembering a Hebrew verse even while citing the
    right chapter:verse is normal, not a separate error, and an exact-substring check flags both the
    right and the wrong citation as unconfirmed, giving no way to tell them apart. Shared 6-character
    substrings survive that kind of noise far better.

    Same-chapter alternatives are excluded from "better ref" on purpose: a long multi-verse quotation
    (e.g. citing Leviticus 23:27 through 23:33 as one continuous block) makes ADJACENT verses' content
    bleed into each other's surrounding window — reproduced live, (ויקרא כג,לא) scored genuine but
    unrelated overlap against verse 30's content purely from being quoted one line above it. That is
    normal multi-verse citation, not an error, and without this exclusion it read identically to the
    real cross-chapter mismatch (Leviticus 13 vs 23) this function exists to catch.

    The surrounding window is taken from BOTH sides of the citation, not just before it: Gemara-style
    phrasing sometimes puts the reference BEFORE its quote ("הרי הוא אומר (ref) quote…") and
    sometimes after ("quote… (ref)") — a before-only window missed the live case, where the wrong
    citation preceded its quote while the correct one, earlier in the same answer, followed it.

    `fetch_refs` is a callable(refs: list[str]) -> list[hit-like] (payload or attribute access to
    `ref`/`text`), same shape as app/api.py::_fetch_refs — kept as a parameter so this stays free of
    any store import, like sugya.check.
    """
    from chavruta.intents.hebrew_refs import detect_parenthetical_tanakh_citations

    spans = detect_parenthetical_tanakh_citations(text or "")
    refs = sorted({ref for ref, _, _ in spans})
    if len(refs) < 2:
        return []
    try:
        hits = fetch_refs(refs)
    except Exception:
        return []
    content: dict[str, str] = {}
    for h in hits:
        payload = getattr(h, "payload", None) or {}
        r = getattr(h, "ref", None) or payload.get("ref")
        body = getattr(h, "text", None) or payload.get("text") or ""
        if r:
            content[r] = _heb_skeleton(body)

    _WIN, _NGRAM = 100, 6            # window radius; n-gram length for the overlap score
    # Cited ref's own overlap must be near-zero (barely more than coincidence) before this even
    # looks for an alternative; the alternative then needs a real, non-trivial score of its own —
    # both calibrated against the live 2026-08-20 case (own=0.000, correct alt=0.072) with margin.
    _OWN_MAX, _ALT_MIN = 0.03, 0.05

    def _ngrams(s: str) -> set[str]:
        return {s[i:i + _NGRAM] for i in range(len(s) - _NGRAM + 1)} if len(s) >= _NGRAM else set()

    def _overlap(window_grams: set[str], ref: str) -> float:
        skel_grams = _ngrams(content.get(ref, ""))
        if not window_grams or not skel_grams:
            return 0.0
        return len(window_grams & skel_grams) / len(window_grams)

    def _book_chapter(ref: str) -> str:
        parts = ref.split(".")
        return ".".join(parts[:2]) if len(parts) >= 2 else ref

    out: list[MismatchedCitation] = []
    seen_refs: set[str] = set()
    for ref, start, end in spans:
        if ref in seen_refs:
            continue
        window = _heb_skeleton(text[max(0, start - _WIN):min(len(text), end + _WIN)])
        window_grams = _ngrams(window)
        if not window_grams or _overlap(window_grams, ref) > _OWN_MAX:
            continue                            # self-supported, or too little context to judge
        best_ref, best_score = None, 0.0
        for other in refs:
            if other == ref or _book_chapter(other) == _book_chapter(ref):
                continue                        # same chapter — normal multi-verse spillover, not an error
            score = _overlap(window_grams, other)
            if score > best_score:
                best_ref, best_score = other, score
        if best_ref and best_score >= _ALT_MIN:
            out.append(MismatchedCitation(window[:_NGRAM * 3], best_ref, ref))
            seen_refs.add(ref)                  # one finding per wrong ref is enough to act on
    return out


_TALMUD_SEGMENT_RE: re.Pattern | None = None


def _talmud_segment_re() -> re.Pattern:
    """Built lazily (needs HE_TRACTATES from hebrew_refs, a corpus/ -> intents/ dependency this
    module otherwise avoids at import time) and cached — the alternation is the same on every call."""
    global _TALMUD_SEGMENT_RE
    if _TALMUD_SEGMENT_RE is None:
        from chavruta.intents.hebrew_refs import HE_TRACTATES

        names = "|".join(re.escape(n) for n in sorted(HE_TRACTATES, key=len, reverse=True))
        _TALMUD_SEGMENT_RE = re.compile(
            rf"(?P<prefix>[בלכמו]{{0,2}})(?P<tractate>{names})\s+(?P<n>\d+)[:.]\d+")
    return _TALMUD_SEGMENT_RE


# A real daf citation is always "<tractate> <daf-letters> ע\"<א|ב>" or "<tractate> <daf-letters>:" —
# the amud is a LETTER, never a second integer. Two consecutive integers joined by ':' or '.' right
# after a tractate name is therefore an unambiguous fingerprint of this specific leak, not something
# that could also match a correctly-written citation.
_MAX_SANE_DAF = 180   # Bava Batra, the longest tractate, tops out at 176 — 180 leaves margin


def fix_raw_talmud_segment_refs(text: str) -> str:
    """Replace a raw internal corpus segment number that leaked into prose (e.g. 'ביומא 148:10')
    with the real daf:amud a reader recognizes ('ביומא עד ע"ב') — or, if the number does not decode
    to a plausible daf, drop the confusing digits rather than guess.

    Caught live 2026-08-20: a real QA answer wrote "הגמרא ביומא 148:10 קובעת" and "רש"י על ההמשך
    (יומא 148:10) מבהיר" — 148 is the corpus's own flat amud-linear number for the source header the
    model was shown ('יומא — Yoma.148.10'), and it copied that number straight into the answer
    instead of converting it. The arithmetic checks out exactly: N=148 is even -> daf 74, amud b —
    Yoma 74b, which is what the user's OWN question named. The model invented nothing; it just
    exposed an internal identifier that was never meant to reach a reader. See
    corpus/refs.py::corpus_n_to_daf_amud for the conversion (the inverse of the corpus's own
    daf_amud_to_corpus_n) and the prompt-side fix in llm/base.py::render_messages /
    app/api.py::_chavruta_job_md, which this backs up rather than replaces.
    """
    from chavruta.corpus.refs import corpus_n_to_daf_amud, hebrew_numeral

    def _replace(m: re.Match) -> str:
        n = int(m.group("n"))
        try:
            daf, amud = corpus_n_to_daf_amud(n)
        except Exception:
            return f"{m.group('prefix')}{m.group('tractate')}"
        if not (2 <= daf <= _MAX_SANE_DAF):
            return f"{m.group('prefix')}{m.group('tractate')}"      # not a plausible daf — drop it
        amud_label = 'ע"א' if amud == "a" else 'ע"ב'
        return f"{m.group('prefix')}{m.group('tractate')} {hebrew_numeral(daf)} {amud_label}"

    return _talmud_segment_re().sub(_replace, text or "")


def misattribution_note(lang: str, findings: list[Misattribution]) -> str:
    """Caveat text for a misattribution. Names BOTH sides on purpose: 'unverified quote' would be a
    lie here — the quote is in the corpus, it just isn't the commentator's the answer credits, and
    telling the reader which source does carry it is what lets them check in one click."""
    if not findings:
        return ""
    f = findings[0]
    if lang == "he":
        claimed = COMMENTATOR_HE.get(f.claimed, f.claimed)
        actual = ", ".join(COMMENTATOR_HE.get(c, c) for c in f.found_in)
        return (f"הערה: הציטוט «{f.quote}» יוחס ל{claimed}, אך לשון זו נמצאת במקור של {actual} "
                f"— יש לאמת את הייחוס.")
    claimed = commentator_title(f.claimed).replace("_", " ")
    actual = ", ".join(commentator_title(c).replace("_", " ") for c in f.found_in)
    return (f"Note: the quote «{f.quote}» is attributed to {claimed}, but that wording appears in "
            f"the {actual} source — verify the attribution.")


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
                                    shut: bool = False, history=None):
    """Prompt the model to deliver the lesson — or responsa (`shut=True`) — as a flowing
    walkthrough (the "מהלך"), laying out the arc's stages in order with sources as [S#].

    Returns (GroundedPrompt, marker_map) — marker_map values are the plan's Citations, so
    enforce_citations resolves the cited sources and lets the caller keep only those.

    `history` (the conversation so far) is carried onto the prompt so a lesson/responsa turn can
    be a follow-up rather than a standalone question — this used to be hard-coded empty.
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
    llm_history = [LLMTurn(role=t.role, text=t.text) for t in (history or [])]
    prompt = GroundedPrompt(system=system, sources=sources, question="\n".join(lines),
                            history=llm_history)
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
