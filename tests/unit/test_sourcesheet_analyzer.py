"""Unit tests for Source Sheet Analyzer (Spec 008 Phase 3)."""

from __future__ import annotations

import pytest

from chavruta.sourcesheet.analyzer import (
    STATUS_MISSING_REF,
    STATUS_USER_PROVIDED,
    STATUS_VERIFIED_CORPUS,
    analyze_source_sheet,
    build_sourcesheet_prompt_context,
)
from chavruta.sourcesheet.parser import parse_source_sheet


def test_analyze_source_sheet_and_markdown_export():
    raw = """
    1. בבא מציעא דף כ"א ע"א:
    אמר רבא: ייאוש שלא מדעת לא הוי ייאוש.

    2. רש"י שם ד"ה ייאוש שלא מדעת:
    כגון שנפלה ממנו אבידה ועדיין לא ידע שנפלה ממנו.

    3. שו"ת חתם סופר אה"ע סימן פ"ג
    """
    items = parse_source_sheet(raw)
    assert len(items) == 3

    corpus_lookup = {
        "Bava Metzia 21a": "משנה: אלו מציאות שלו ואלו חייב להכריז...",
    }

    guide = analyze_source_sheet(items, topic_hint="ייאוש שלא מדעת", corpus_lookup=corpus_lookup)

    assert guide.topic == "ייאוש שלא מדעת"
    assert len(guide.sections) == 3

    # Section 1: Verified in corpus
    assert guide.sections[0].status == STATUS_VERIFIED_CORPUS
    assert guide.sections[0].ref == "Bava Metzia 21a"

    # Section 2: User provided text (Rashi)
    assert guide.sections[1].status == STATUS_USER_PROVIDED

    # Section 3: Missing ref (no text and not in corpus)
    assert guide.sections[2].status == STATUS_MISSING_REF

    # Markdown export
    md = guide.to_markdown()
    assert "# חוברת ליווי לדף מקורות" in md
    assert "```mermaid" in md
    assert "טבלת השוואת שיטות" in md
    assert "שאלות לעיון וחזרת החברותא" in md


def test_build_sourcesheet_prompt_context_xml():
    raw = "1. בבא מציעא דף כ\"א ע\"א:\nאמר רבא ייאוש שלא מדעת."
    items = parse_source_sheet(raw)
    xml = build_sourcesheet_prompt_context(items, corpus_lookup={"Bava Metzia 21a": "טקסט מאומת"})
    assert '<source id="S1" status="VERIFIED_CORPUS"' in xml
    assert "<corpus_verified_text>טקסט מאומת</corpus_verified_text>" in xml


def test_sourcesheet_llm_synthesis_and_clean_topic():
    raw = "1. בבא מציעא דף כ\"א ע\"א:\nאמר רבא ייאוש שלא מדעת."
    items = parse_source_sheet(raw)

    class FakeLLMResponse:
        text = """```json
{
  "topic": "סוגיית ייאוש שלא מדעת",
  "core_inquiry": "האם ייאוש בעלים למפרע מועיל או שמא בעינן ידיעה בפועל.",
  "summary": "הסוגיה בבבא מציעא פותחת במחלוקת אביי ורבא...",
  "sections": [
    {
      "index": 1,
      "title": "בבא מציעא כ\"א ע\"א",
      "role_tag": "מקור יסוד / עובדא דש\"ס",
      "plain_explanation": "העמדת מחלוקת אביי ורבא בדין אבידה שנמצאה קודם שידעו הבעלים.",
      "diyuk": "מדייק רבא דכל שלא ידע לא הוי ייאוש",
      "difficult_words": {}
    }
  ],
  "opinion_table": [
    {"opinion": "רבא", "reason": "לא ידע לא מייאש", "proof": "משנה", "nafka_mina": "חייב להכריז"}
  ],
  "chavruta_questions": {
    "peshat": ["מהי סברת רבא?"],
    "comparison": [],
    "sevara": ["האם ייאוש הוא מעשה קניין או הסרת בעלות?"]
  },
  "flowchart_mermaid": "flowchart TD\\n    A --> B"
}
```"""

    class FakeLLM:
        def generate(self, prompt, **kwargs):
            return FakeLLMResponse()

    # Pass leaked system instruction as topic hint
    leaked_hint = "תסכם את הדף (לא מהמאגר — התייחס אליהם כמקור נוסף)"
    guide = analyze_source_sheet(items, topic_hint=leaked_hint, llm=FakeLLM())

    assert guide.topic == "סוגיית ייאוש שלא מדעת"
    assert "לא מהמאגר" not in guide.topic
    assert "סוגיית ייאוש שלא מדעת" in guide.title
    assert guide.core_inquiry == "האם ייאוש בעלים למפרע מועיל או שמא בעינן ידיעה בפועל."
    assert "העמדת מחלוקת אביי ורבא" in guide.sections[0].plain_explanation
    assert len(guide.opinion_table) == 1
    assert "מהי סברת רבא?" in guide.chavruta_questions["peshat"]


def test_sourcesheet_to_docx_bytes_styled_and_rtl():
    raw = """
    1. בבא מציעא דף כ"א ע"א:
    אמר רבא: ייאוש שלא מדעת לא הוי ייאוש.

    2. רש"י שם ד"ה ייאוש שלא מדעת:
    כגון שנפלה ממנו אבידה ועדיין לא ידע שנפלה ממנו.
    """
    items = parse_source_sheet(raw)
    guide = analyze_source_sheet(items, topic_hint="ייאוש שלא מדעת")

    docx_bytes = guide.to_docx_bytes()
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 5000
    assert docx_bytes.startswith(b"PK\x03\x04")

    import io
    import docx
    from docx.oxml.ns import qn

    doc = docx.Document(io.BytesIO(docx_bytes))
    assert len(doc.paragraphs) > 5
    assert len(doc.tables) >= 1

    # Check for RTL table setting (bidiVisual)
    found_bidi_table = any(t._tbl.tblPr.find(qn("w:bidiVisual")) is not None for t in doc.tables)
    assert found_bidi_table is True

    # Check for RTL paragraph setting (bidi)
    found_bidi_p = any(p._p.pPr is not None and p._p.pPr.find(qn("w:bidi")) is not None for p in doc.paragraphs)
    assert found_bidi_p is True

    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "חוברת ליווי לדף מקורות" in full_text
    assert "ייאוש שלא מדעת" in full_text


def test_sourcesheet_to_html_printable():
    raw = """
    1. בבא מציעא דף כ"א ע"א:
    אמר רבא: ייאוש שלא מדעת לא הוי ייאוש.
    """
    items = parse_source_sheet(raw)
    guide = analyze_source_sheet(items, topic_hint="ייאוש שלא מדעת")

    html_content = guide.to_html_printable()
    assert "<!DOCTYPE html>" in html_content
    assert '<html dir="rtl" lang="he">' in html_content
    assert "@media print" in html_content
    assert "size: A4 portrait" in html_content
    assert "window.print()" in html_content
    assert "Frank Ruhl Libre" in html_content
    assert "ייאוש שלא מדעת" in html_content
    assert "שאלת היסוד וציר החקירה" in html_content
    assert "ביאור מקורות הדף" in html_content


def test_sourcesheet_html_escapes_flowchart_markup():
    """flowchart_mermaid comes from the model or raw sheet headers; markup
    in it must not reach the page as live HTML."""
    payload = "<img src=x onerror=alert(1)>"
    raw = f"""
    1. {payload}
    אמר רבא: ייאוש שלא מדעת לא הוי ייאוש.
    """
    guide = analyze_source_sheet(parse_source_sheet(raw), topic_hint=payload)
    assert guide.flowchart_mermaid  # deterministic fallback built a diagram

    guide.flowchart_mermaid += f'\n    Z["{payload}"]'  # as if the model echoed it
    html_content = guide.to_html_printable()
    assert payload not in html_content
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_content
    assert "securityLevel: 'strict'" in html_content



# ── The model's reply is the single point of failure; these pin how it is read and retried ─────────

from chavruta.sourcesheet.analyzer import (  # noqa: E402
    _build_flowchart,
    _parse_llm_json,
    _synthesis_token_budget,
)


def test_parse_llm_json_survives_straight_quotes_inside_values():
    reply = (
        '{"topic": "סוגיה", "sections": [{"source_id": "S1", '
        '"plain_explanation": "עיין ברש"י ד"ה "דנין פר" ובתוס\' שם", "diyuk": "ר"ת אומר"}]}'
    )
    data = _parse_llm_json(reply)
    assert data is not None
    assert data["sections"][0]["plain_explanation"] == 'עיין ברש"י ד"ה "דנין פר" ובתוס\' שם'
    assert data["sections"][0]["diyuk"] == 'ר"ת אומר'


def test_parse_llm_json_accepts_fences_and_trailing_commas():
    assert _parse_llm_json('```json\n{"topic": "א", "x": [1, 2,],}\n```') == {"topic": "א", "x": [1, 2]}


def test_parse_llm_json_rejects_a_truncated_reply():
    assert _parse_llm_json('{"topic": "א", "sections": [{"source_id": "S1", "plain_expl') is None
    assert _parse_llm_json("") is None
    assert _parse_llm_json("אין כאן JSON") is None


def test_token_budget_grows_with_the_number_of_sources():
    assert _synthesis_token_budget(7) > 3500          # the old fixed cap truncated a 7-source sheet
    assert _synthesis_token_budget(1) < _synthesis_token_budget(7) < _synthesis_token_budget(40)
    assert _synthesis_token_budget(500) <= 9000


class _Reply:
    def __init__(self, text):
        self.text = text
        self.finish_reason = "stop"


class _ScriptedLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        return _Reply(self.replies.pop(0))


_GOOD_REPLY = '{"topic": "נושא", "core_inquiry": "חקירה", "summary": "סיכום", "sections": [], "opinion_table": [], "chavruta_questions": {}}'
_RAW = "1. בבא מציעא דף כ\"א ע\"א:\nאמר רבא ייאוש שלא מדעת."


def test_unparseable_first_reply_is_retried_once_before_giving_up():
    llm = _ScriptedLLM('{"topic": "נחתך באמצע', _GOOD_REPLY)
    guide = analyze_source_sheet(parse_source_sheet(_RAW), topic_hint="נושא", llm=llm)
    assert llm.calls == 2
    assert guide.degraded is False
    assert guide.core_inquiry == "חקירה"


def test_two_bad_replies_give_a_degraded_guide_the_caller_can_detect():
    llm = _ScriptedLLM("לא JSON", "גם לא JSON")
    guide = analyze_source_sheet(parse_source_sheet(_RAW), topic_hint="נושא", llm=llm)
    assert llm.calls == 2
    assert guide.degraded is True


def test_a_good_first_reply_costs_one_call():
    llm = _ScriptedLLM(_GOOD_REPLY)
    guide = analyze_source_sheet(parse_source_sheet(_RAW), topic_hint="נושא", llm=llm)
    assert llm.calls == 1
    assert guide.degraded is False


def test_the_user_instruction_reaches_the_prompt():
    seen = []

    class Spy(_ScriptedLLM):
        def generate(self, prompt, **kwargs):
            seen.append(prompt.question)
            return super().generate(prompt, **kwargs)

    analyze_source_sheet(
        parse_source_sheet(_RAW), topic_hint="נושא", llm=Spy(_GOOD_REPLY), user_instruction="התמקד במחלוקת"
    )
    assert "התמקד במחלוקת" in seen[0]


def test_flowchart_has_every_source_and_no_quote_that_breaks_a_node():
    items = parse_source_sheet(
        "\n".join(f'{n}. בבא מציעא דף {n + 1} ע"א "ציטוט":\nטקסט {n}.' for n in range(1, 8))
    )
    guide = analyze_source_sheet(items, topic_hint='נושא "מצוטט"')
    chart = _build_flowchart(guide.topic, guide.sections)
    for n in range(1, 8):
        assert f"מקור {n}:" in chart
    for line in chart.splitlines()[1:]:
        assert line.count('"') in (0, 2)


def test_quoted_source_text_beats_the_corpus_text_filed_under_its_base_ref():
    raw = (
        "1. פירוש קדמון על בבא מציעא דף כ\"א ע\"א:\n"
        '"אמר רבא ייאוש שלא מדעת לא הוי ייאוש, וכן הלכה למעשה בכל אבידה שנפלה."'
    )
    items = parse_source_sheet(raw)
    guide = analyze_source_sheet(items, corpus_lookup={"Bava Metzia 21a": "משנה: אלו מציאות שלו"})
    sec = guide.sections[0]
    assert sec.status == STATUS_USER_PROVIDED
    assert "ייאוש שלא מדעת" in sec.source_snippet
    assert sec.expanded_context == "משנה: אלו מציאות שלו"   # kept as context, not shown as the source


# ── A bare reference is not text: it must not be explained from the model's memory ────────────────

from chavruta.sourcesheet.analyzer import MISSING_TEXT_NOTE  # noqa: E402

_OUTLINE_WITH_BARE_REFS = """קריאת שמע – שיעור
אנחנו לומדים מסכת ברכות.
מקורות:
א. שמות יג פסוקים ג – ז.
ב. סוגיית הגמרא מהמשנה עד ג', ב ויש לעיין היטב בכל התחנות שבדרך
א.
שמות פרק יג פסוקים ג-ז.
ב.
גמרא ב, א "מאימתי" ו-ב, ב "עד סוף האשמורת" וצריך לעיין בכל אלה לקראת השיעור.
ג', א: מה הדין לפי ר' אליעזר ומה לפי חכמים בענין זה.
"""


def test_bare_pasuk_and_gemara_range_without_corpus_text_are_missing_not_user_provided():
    items = parse_source_sheet(_OUTLINE_WITH_BARE_REFS)
    guide = analyze_source_sheet(items, topic_hint="נושא")
    assert [s.status for s in guide.sections] == [STATUS_MISSING_REF, STATUS_MISSING_REF]


def test_missing_source_explanation_is_fixed_text_whatever_the_model_wrote():
    items = parse_source_sheet(_OUTLINE_WITH_BARE_REFS)
    reply = (
        '{"topic": "נושא", "core_inquiry": "חקירה", "summary": "סיכום", '
        '"sections": [{"source_id": "S1", "plain_explanation": "ציטוט מזיכרון", "diyuk": "דיוק מהזיכרון", '
        '"difficult_words": {"א": "ב"}}], "opinion_table": [], "chavruta_questions": {}}'
    )
    guide = analyze_source_sheet(items, topic_hint="נושא", llm=_ScriptedLLM(reply))
    first = guide.sections[0]
    assert first.status == STATUS_MISSING_REF
    assert first.plain_explanation == MISSING_TEXT_NOTE
    assert first.diyuk is None
    assert first.difficult_words == {}


def test_a_short_repeated_reference_line_is_not_a_body_but_a_real_sentence_is():
    assert parse_source_sheet("1. שמות פרק כ פסוק ב:\nשמות כ ב.")[0].metadata.get("quoted_text") is None
    items = parse_source_sheet("1. בבא מציעא דף כ\"א ע\"א:\nאמר רבא: ייאוש שלא מדעת לא הוי ייאוש.")
    assert analyze_source_sheet(items).sections[0].status == STATUS_USER_PROVIDED


# ── Quotations the sources do not contain are marked, not shipped as quotations ───────────────────

from chavruta.sourcesheet.analyzer import (  # noqa: E402
    UNVERIFIED_QUOTE_MARK,
    _normalize_for_match,
    _scrub_unverified_quotes,
)

_HAY = _normalize_for_match('ואימא צוה צוה דיום הכפורים. "מאימתי קורין את שמע" ... עד סוף האשמורת')


def test_a_quotation_missing_from_the_sources_is_replaced_by_a_marker():
    out, n = _scrub_unverified_quotes("הגמרא לומדת ״צוואה צוואה״ ממלואים", _HAY)
    assert n == 1
    assert UNVERIFIED_QUOTE_MARK in out and "צוואה" not in out


def test_a_quotation_present_in_the_sources_survives_niqqud_and_punctuation_differences():
    out, n = _scrub_unverified_quotes("נאמר ״ואימא צוה צוה, דיום הכפורים״ בגמרא", _HAY)
    assert (out, n) == ("נאמר ״ואימא צוה צוה, דיום הכפורים״ בגמרא", 0)


def test_an_ellipsis_quote_is_checked_piece_by_piece():
    ok, n_ok = _scrub_unverified_quotes("״מאימתי קורין … עד סוף האשמורת״", _HAY)
    assert n_ok == 0 and "מאימתי" in ok
    bad, n_bad = _scrub_unverified_quotes("״מאימתי קורין … ועוד דבר שלא נאמר״", _HAY)
    assert n_bad == 1 and UNVERIFIED_QUOTE_MARK in bad


def test_acronym_gershayim_and_single_word_terms_are_not_treated_as_quotations():
    text = "דעת הרמב״ם והר״ן, וכן ״כתר״ ו״דום״ כמושגים"
    assert _scrub_unverified_quotes(text, _HAY) == (text, 0)


def test_model_text_with_an_invented_quote_is_scrubbed_end_to_end():
    reply = (
        '{"topic": "נושא", "core_inquiry": "חקירה", '
        '"summary": "הסוגיה דנה ב״גזירה שווה צוואה צוואה״ ממלואים", "sections": [], '
        '"opinion_table": [], "chavruta_questions": {}}'
    )
    guide = analyze_source_sheet(parse_source_sheet(_RAW), topic_hint="נושא", llm=_ScriptedLLM(reply))
    assert UNVERIFIED_QUOTE_MARK in guide.summary
    assert "צוואה" not in guide.summary


def test_apostrophe_quotations_are_checked_and_abbreviation_geresh_is_not():
    bad, n_bad = _scrub_unverified_quotes("ביאר 'צוואה צוואה' ממלואים", _HAY)
    assert n_bad == 1 and UNVERIFIED_QUOTE_MARK in bad
    good = "ביאר 'ואימא צוה צוה' ור' אליעזר ותוס' שם"
    assert _scrub_unverified_quotes(good, _HAY) == (good, 0)
