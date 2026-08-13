"""deontic_conflicts (internal deontic consistency, src/chavruta/generation/deontic.py).

The false-positive tests come first and outnumber the true positive, because they are what decides
whether this check is usable at all. Firing on a machloket ("בית שמאי אוסרים ובית הלל מתירים") or on
an ordinary qualified ruling ("אסור בשבת ומותר ביום חול") would not merely be noise — it would be a
tool telling an operator that correct halachic writing is an error, and it would be switched off
within a day, taking with it the one case it should have caught.

Deterministic and offline: no LLM, no network. Every input here is prose of the kind the generator
actually produces.
"""

from __future__ import annotations

from chavruta.generation.deontic import deontic_conflicts, normative_statements

# ── The false positives: prose that is RIGHT and must stay silent ────────────────────────────────


def test_machloket_between_two_authorities_is_not_a_contradiction():
    """Principle VIII requires surfacing a disagreement rather than flattening it. Two names holding
    opposite verdicts is the disagreement itself, described correctly."""
    answer = ("בית שמאי אוסרים להדליק את הנר. "
              "בית הלל מתירים להדליק את הנר.")
    assert deontic_conflicts(answer) == []


def test_anonymous_plural_voice_holding_both_sides_is_a_machloket_too():
    """'יש אומרים' is a crowd. A crowd disagreeing with itself is what the phrase means."""
    answer = ("יש אומרים שאסור לטלטל מוקצה בשבת. "
              "ויש אומרים שמותר לטלטל מוקצה בשבת.")
    assert deontic_conflicts(answer) == []


def test_same_authority_with_a_time_qualifier_is_not_a_contradiction():
    answer = ("הרמב\"ם אוסר לבשל את התבשיל בשבת. "
              "הרמב\"ם מתיר לבשל את התבשיל ביום חול.")
    assert deontic_conflicts(answer) == []


def test_same_authority_with_a_lechatchila_bedieved_qualifier_is_not_a_contradiction():
    answer = ("השולחן ערוך אוסר לכתחילה להשתמש בכלי הזה. "
              "השולחן ערוך מתיר בדיעבד להשתמש בכלי הזה.")
    assert deontic_conflicts(answer) == []


def test_same_authority_at_two_halachic_levels_is_not_a_contradiction():
    answer = ("הרמב\"ם אוסר את הדבר מדרבנן. "
              "הרמב\"ם מתיר את הדבר מדאורייתא.")
    assert deontic_conflicts(answer) == []


def test_quoting_an_opposing_view_before_rejecting_it_is_not_a_contradiction():
    """The classic teshuva shape. 'אך' and 'למעשה' both mark the shift explicitly, and the opening
    view belongs to an anonymous plural voice in the first place."""
    answer = "יש אומרים שמותר להשתמש בזה, אך למעשה אסור להשתמש בזה."
    assert deontic_conflicts(answer) == []


def test_patur_aval_asur_crosses_axes_and_is_coherent():
    """A famous phrase: exempt from liability yet forbidden. Two different questions, not two
    answers to one — pairing across axes would flag the Talmud itself."""
    answer = ("הרמב\"ם פוטר את העושה כן מן החיוב הממוני. "
              "הרמב\"ם אוסר את המעשה הזה לכתחילה.")
    assert deontic_conflicts(answer) == []


def test_liability_split_between_the_two_forums_is_not_a_contradiction():
    answer = ("השולחן ערוך פוטר את המזיק בדיני אדם. "
              "השולחן ערוך מחייב את המזיק בדיני שמים.")
    assert deontic_conflicts(answer) == []


def test_a_heter_for_a_specific_need_is_a_distinction_not_a_reversal():
    """'לצורך מקומו' is the distinction, spelled out — and the extra words are also what keeps the
    two cases from looking identical."""
    answer = ("הרמב\"ם אוסר לטלטל מוקצה. "
              "הרמב\"ם מתיר לטלטל מוקצה לצורך מקומו.")
    assert deontic_conflicts(answer) == []


def test_two_different_cases_under_one_authority_are_not_a_contradiction():
    answer = ("הרמב\"ם אוסר לאכול בשר עוף בחלב. "
              "הרמב\"ם מתיר לאכול דגים עם חלב.")
    assert deontic_conflicts(answer) == []


def test_an_answer_with_no_normative_statements_yields_nothing():
    answer = ("רש\"י מפרש שהפסוק עוסק במעשה בראשית, "
              "והרמב\"ן מוסיף שיש כאן רמז לעתיד לבוא. "
              "שני הפירושים משלימים זה את זה.")
    assert normative_statements(answer) == []
    assert deontic_conflicts(answer) == []


def test_a_negated_verdict_is_dropped_rather_than_flipped():
    """'אינו אסור' is not read as a heter — deciding what a negation licenses is interpretation,
    which is exactly what this module refuses to do."""
    answer = ("הרמב\"ם סובר שאין הדבר הזה אסור כלל בטלטול. "
              "הרמב\"ם מתיר את הדבר הזה בטלטול.")
    assert deontic_conflicts(answer) == []


def test_a_hedged_statement_is_not_an_assertion():
    answer = ("הרמב\"ם אוסר לטלטל מוקצה בשבת. "
              "לכאורה מותר לטלטל מוקצה בשבת.")
    assert deontic_conflicts(answer) == []


def test_both_poles_in_one_breath_rule_on_nothing():
    """'בין אסור למותר' names the two poles; it does not hold either of them."""
    answer = "הרמב\"ם מבחין כאן בין מה שאסור לבין מה שמותר בטלטול מוקצה בשבת."
    assert deontic_conflicts(answer) == []


def test_an_unlisted_distinction_silences_the_check():
    """The qualifier table can never be complete — halacha distinguishes on anything. An unlisted
    distinction arrives as one extra word, which is why the same case must be described in the SAME
    words rather than merely similar ones."""
    answer = ("הרמב\"ם אוסר לטלטל מוקצה בשבת. "
              "הרמב\"ם מתיר לטלטל מוקצה בשבת לתינוק.")
    assert deontic_conflicts(answer) == []


def test_rambam_and_ramban_are_not_the_same_authority():
    """One letter apart, and merging them would manufacture a contradiction out of a machloket —
    the one direction of error this check must never make. Both gershayim spellings included, since
    folding ״ onto \" is what lets the same name match itself."""
    for answer in ("הרמב\"ם אוסר לטלטל מוקצה בשבת. הרמב\"ן מתיר לטלטל מוקצה בשבת.",
                   "הרמב״ם אוסר לטלטל מוקצה בשבת. הרמב״ן מתיר לטלטל מוקצה בשבת."):
        assert [s.authority for s in normative_statements(answer)] == ["rambam", "ramban"]
        assert deontic_conflicts(answer) == []


def test_the_same_name_spelled_with_either_gershayim_is_one_authority():
    answer = "הרמב״ם אוסר לטלטל מוקצה בשבת. ולפיכך הרמב\"ם מתיר לטלטל מוקצה בשבת."
    assert [c.authority for c in deontic_conflicts(answer)] == ["rambam"]


def test_an_unrecognised_posek_does_not_inherit_someone_elses_name():
    """The second ruling belongs to a rav this module cannot identify. Crediting it to the last
    name that happened to match would manufacture a contradiction out of a machloket."""
    answer = ("הרמב\"ם אוסר לטלטל מוקצה בשבת. "
              "הרב יעקב כהן פסק שמותר לטלטל מוקצה בשבת.")
    assert deontic_conflicts(answer) == []


# ── The true positive: one authority, one case, both verdicts, nothing explaining the shift ──────


def test_same_authority_reversed_on_the_same_case_is_reported():
    answer = ("הרמב\"ם אוסר לטלטל מוקצה בשבת. "
              "ולפיכך הרמב\"ם מתיר לטלטל מוקצה בשבת.")
    conflicts = deontic_conflicts(answer)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.authority == "rambam"
    assert c.axis == "permission"
    assert {c.first.polarity, c.second.polarity} == {"forbid", "permit"}
    assert c.attribution == "explicit"
    # The report is two spans of text, not a ruling on which of them is right.
    assert "אוסר" in c.first.sentence and "מתיר" in c.second.sentence


def test_an_unattributed_conclusion_inherits_the_only_speaker_and_is_marked_as_such():
    """The motivating shape: a conclusion that reverses the premise with nothing but 'לפיכך' in
    between. It is reported, but flagged 'inherited' — the name was carried, not written."""
    answer = ("הרמב\"ם אוסר לטלטל מוקצה בשבת. "
              "לפיכך מותר לטלטל מוקצה בשבת.")
    conflicts = deontic_conflicts(answer)
    assert len(conflicts) == 1
    assert conflicts[0].authority == "rambam"
    assert conflicts[0].attribution == "inherited"


def test_one_pair_per_authority_and_axis_even_when_the_answer_flips_repeatedly():
    answer = ("הרמב\"ם אוסר לטלטל מוקצה בשבת. "
              "הרמב\"ם מתיר לטלטל מוקצה בשבת. "
              "הרמב\"ם אוסר לטלטל מוקצה בשבת.")
    assert len(deontic_conflicts(answer)) == 1


def test_the_result_is_a_list_and_never_a_verdict_on_the_answer():
    """Guards the design constraint itself: the module reports suspected pairs and stops. Anything
    that returned a boolean would be a judgement on the halacha, which belongs to a rav."""
    clean = "רש\"י מפרש שהפסוק עוסק במעשה בראשית."
    assert isinstance(deontic_conflicts(clean), list)
    assert deontic_conflicts(clean) == []
