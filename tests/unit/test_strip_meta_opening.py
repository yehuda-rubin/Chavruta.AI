"""The walkthrough instruction must not reach the reader as the answer's first line."""

from chavruta.generation.grounded import strip_meta_opening


def test_drops_echoed_instruction_line():
    raw = ("הנה המהלך המלא לפי השלבים שסיפקת, מתוך המקורות הרלוונטיים בלבד:\n\n"
           "ברכת שהחיינו על פרי חדש בבין המצרים\n\nיסוד הדין מובא בכף החיים [S1].")
    assert strip_meta_opening(raw).startswith("ברכת שהחיינו")


def test_drops_english_echo():
    raw = "Here is the walkthrough following the stages you provided:\n\nThe Mishnah opens [S1]."
    assert strip_meta_opening(raw).startswith("The Mishnah opens")


def test_keeps_a_real_opening():
    raw = "הנה דברי רש״י על הפסוק: \"אין המקרא הזה אומר אלא דרשני\" [S1].\nועוד."
    assert strip_meta_opening(raw) == raw


def test_keeps_a_stage_word_deep_in_a_long_first_line():
    raw = "יסוד הדין " + "מובא בגמרא " * 20 + "בשלבים.\nהמשך."
    assert strip_meta_opening(raw) == raw


def test_drops_an_opening_that_talks_about_the_supplied_sources():
    raw = "אני רואה שהמקורות שסופקו כוללים את רוב הקטעים מהדף. נתחיל בלימוד המשנה.\n\n---\n\nהמשנה פותחת [S1]."
    assert strip_meta_opening(raw).startswith("---")


def test_keeps_an_opening_that_merely_starts_with_i_see():
    raw = "אני רואה שרש\"י מפרש כאן את המילה בדרך אחרת.\nוהתוספות חולקים."
    assert strip_meta_opening(raw) == raw


def test_empty():
    assert strip_meta_opening("") == ""


# ── finalize_raw: the quote-reference pass every generation tail now runs ──
from types import SimpleNamespace

from chavruta.generation.grounded import finalize_raw


def _marker_map():
    return {"S1": SimpleNamespace(text="[x] Bekhorot 29a\nהנוטל שכר לדון דיניו בטלים להעיד עדותיו בטלים:", ref="Bekhorot.57.1"),
            "S2": SimpleNamespace(text="מקבלין אותו שנחזיקנו כחבר וכנאמן לכל דבריו", ref="Rashi_on_Bekhorot.60.6.2")}


def test_quote_reference_is_pasted_with_the_verbatim_source_text():
    raw, stats = finalize_raw("המשנה: {{S1: הנוטל שכר … עדותיו בטלים}} ועוד.", _marker_map())
    assert '"הנוטל שכר לדון דיניו בטלים להעיד עדותיו בטלים" [S1]' in raw
    assert stats["ok"] == 1


def test_quote_reference_with_the_wrong_marker_is_moved_to_the_right_source():
    raw, stats = finalize_raw("{{S1: מקבלין אותו … לכל דבריו}}", _marker_map())
    assert raw.endswith("[S2]") and stats["moved"] == 1


def test_unmatchable_quote_reference_is_not_presented_as_a_quote():
    raw, stats = finalize_raw("{{S1: מילים שלא קיימות … בשום מקור}}", _marker_map())
    assert '"' not in raw and "[S" not in raw and stats["unmatched"] == 1


def test_finalize_raw_also_drops_the_meta_opening():
    raw, _ = finalize_raw("הנה המהלך לפי השלבים שסיפקת:\n\nהמשנה פותחת [S1].", _marker_map())
    assert raw.startswith("המשנה")
