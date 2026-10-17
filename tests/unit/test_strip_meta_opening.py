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


def test_empty():
    assert strip_meta_opening("") == ""
