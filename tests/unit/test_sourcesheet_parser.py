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
