"""Unit tests for the Source Sheet parser (Spec 008 Phase 2)."""

from __future__ import annotations

import pytest

from chavruta.sourcesheet.parser import (
    ParsedSourceItem,
    extract_sheet_text,
    parse_source_sheet,
)


def test_parse_source_sheet_basic_talmud():
    raw = """
    1. בבא מציעא דף כ"א ע"א:
    אמר רבא: ייאוש שלא מדעת לא הוי ייאוש. אביי אמר: הוי ייאוש.

    2. רש"י שם ד"ה ייאוש שלא מדעת:
    כגון שנפלה ממנו אבידה ועדיין לא ידע שנפלה ממנו.

    3. תוספות ד"ה שמע מינה:
    ואם תאמר, והא אמרינן לקמן בפירקין... (וצ"ע ברמב"ם)
    """
    items = parse_source_sheet(raw)
    assert len(items) == 3

    # Item 1: Talmud
    assert items[0].index == 1
    assert items[0].ref == "Bava Metzia 21a"
    assert "אמר רבא" in items[0].cleaned_text

    # Item 2: Rashi relative "שם"
    assert items[1].index == 2
    assert "Rashi on Bava Metzia 21a" in items[1].ref
    assert items[1].dibur_hamatchil == "ייאוש שלא מדעת"

    # Item 3: Tosafot relative and author note
    assert items[2].index == 3
    assert "Tosafot on Bava Metzia 21a" in items[2].ref
    assert items[2].dibur_hamatchil == "שמע מינה"
    assert items[2].author_note_text == '(וצ"ע ברמב"ם)'


def test_parse_source_sheet_hebrew_numbering():
    raw = """
    [א] שמות פרק כ פסוק ב:
    אנכי ה' אלקיך אשר הוצאתיך מארץ מצרים.

    [ב] רמב"ם הלכות יסודי התורה פרק א הלכה א:
    יסוד היסודות ועמוד החכמות לידע שיש שם מצוי ראשון.
    """
    items = parse_source_sheet(raw)
    assert len(items) == 2
    assert items[0].index == 1
    assert items[0].ref == "Exodus.20.2"
    assert items[1].index == 2


def test_parse_source_sheet_empty_text():
    assert parse_source_sheet("") == []
    assert parse_source_sheet("   ") == []


def test_extract_sheet_text_plain():
    res = extract_sheet_text("טקסט פשוט", filename="sheet.txt")
    assert res == "טקסט פשוט"


# ── A sheet with an outline up top and the sources in full below it ──────────
# Synthetic, shaped like a real teacher's handout: a title, a line naming the masechta, a short
# outline, a stray start-time line, then each outline letter repeated with its source in full.
_OUTLINE_SHEET = """### 05 שיעור לדוגמה.docx
קריאת שמע בלילה – שיעור שני
אנחנו לומדים מסכת ברכות ולכן נפתח בפרק הראשון.
מקורות מרכזיים:
א. שמות יג פסוקים ג – ז.
ב. דברים ו השוו לפסוק הקודם
ג. סוגיית הגמרא מהמשנה עד ג', ב "מאימתי קורין"
ד. תוס' ד"ה מאימתי
שיעור ב 20:30 בעזרת ה' בביהמ"ד
א.
שמות פרק יג פסוקים ג-ז.
ב.
דברים פרק ו.
ג.
גמרא ב, א "מאימתי קורין את שמע בערבין" ו-ב, ב "עד סוף האשמורת".
ג', א: "ר' אליעזר אומר עד סוף האשמורת הראשונה".
ד.
"תוספות ד"ה מאימתי: ופרש"י דבשעה שכהנים נכנסים לאכול בתרומתם, והקשה הר"י"
"""


def test_outline_sheet_keeps_outline_line_as_header_and_drops_logistics():
    items = parse_source_sheet(_OUTLINE_SHEET)
    assert len(items) == 4
    assert [i.header[:2] for i in items] == ["א.", "ב.", "ג.", "ד."]
    assert "20:30" not in items[3].raw_text


def test_sheet_title_is_the_first_prose_line_not_the_filename():
    from chavruta.sourcesheet.parser import extract_sheet_title

    assert extract_sheet_title(_OUTLINE_SHEET) == "קריאת שמע בלילה – שיעור שני"
    assert extract_sheet_title("1. בבא מציעא דף כ\"א ע\"א") == ""


def test_pasuk_range_anchors_on_those_verses_not_the_whole_chapter():
    first = parse_source_sheet(_OUTLINE_SHEET)[0]
    assert first.ref == "Exodus.13.3"
    assert first.metadata["ref_range"] == [f"Exodus.13.{v}" for v in range(3, 8)]


def test_bare_letter_chapter_in_an_outline_header_resolves():
    second = parse_source_sheet(_OUTLINE_SHEET)[1]
    assert second.ref == "Deuteronomy.6"


def test_gemara_stations_use_the_masechta_the_sheet_announced():
    third = parse_source_sheet(_OUTLINE_SHEET)[2]
    assert third.ref == "Berakhot 2a"
    assert third.metadata["ref_range"] == ["Berakhot 2a", "Berakhot 2b", "Berakhot 3a", "Berakhot 3b"]


def test_gemara_cue_without_an_announced_masechta_stays_unresolved():
    items = parse_source_sheet("א. סוגיית הגמרא מהמשנה עד ג', ב\nב. דברים ו")
    assert items[0].ref is None


def test_tosafot_does_not_inherit_a_pasuk():
    raw = "1. שמות פרק 13 פסוק 3:\nזכור את היום הזה.\n\n2. תוספות ד\"ה זכור:\nדברי תוספות כאן."
    items = parse_source_sheet(raw)
    assert items[0].ref == "Exodus.13.3"
    assert items[1].ref is None


def test_quoted_lines_become_the_items_own_text():
    items = parse_source_sheet(_OUTLINE_SHEET)
    assert "ופרש\"י" in items[3].metadata["quoted_text"]
    assert "quoted_text" not in items[0].metadata
