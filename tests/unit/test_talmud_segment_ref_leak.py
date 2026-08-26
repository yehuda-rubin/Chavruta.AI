"""A raw internal Talmud segment number leaking into an answer's prose (2026-08-20).

Real case: a QA answer wrote "הגמרא ביומא 148:10 קובעת" and "רש"י על ההמשך (יומא 148:10) מבהיר" —
148 is the corpus's own flat amud-linear number for the source header the model was shown
('יומא — Yoma.148.10'), copied straight into the answer instead of converted. The arithmetic checks
out exactly against what the USER asked about: N=148 is even -> daf 74, amud b — Yoma 74b, i.e.
"דף עד עמוד ב", word for word what the original question named.

Covers corpus/refs.py::corpus_n_to_daf_amud + hebrew_numeral (the conversion) and
grounded.py::fix_raw_talmud_segment_refs (the guard that applies it to real text).
"""
from __future__ import annotations

from chavruta.corpus.refs import corpus_n_to_daf_amud, daf_amud_to_corpus_n, hebrew_numeral
from chavruta.generation.grounded import fix_raw_talmud_segment_refs


def test_the_real_case_round_trips():
    """N=148 is exactly what the user's own question named: Yoma daf 74, amud beit."""
    assert corpus_n_to_daf_amud(148) == (74, "b")


def test_corpus_n_to_daf_amud_is_the_true_inverse_of_the_forward_conversion():
    for daf in (1, 2, 39, 74, 176):
        for amud in ("a", "b"):
            n = daf_amud_to_corpus_n(daf, amud)
            assert corpus_n_to_daf_amud(n) == (daf, amud)


def test_hebrew_numeral_matches_known_values():
    assert hebrew_numeral(74) == 'ע"ד'
    assert hebrew_numeral(176) == 'קע"ו'          # Bava Batra's last daf
    assert hebrew_numeral(2) == "ב'"


def test_hebrew_numeral_avoids_spelling_the_divine_name():
    """15/16 are the well-known exception — ט"ו / ט"ז, never יה / יו."""
    assert hebrew_numeral(15) == 'ט"ו'
    assert hebrew_numeral(16) == 'ט"ז'


def test_hebrew_numeral_avoids_the_divine_name_past_100_too():
    """Regression: the exception used to check `n == 15`/`n == 16` — true only for 15/16
    themselves — so 115/116 (e.g. Bava Batra/Pesachim daf קט"ו, קט"ז) fell through to the ordinary
    tens+units letters (י + ה / י + ו), spelling the very forms ט"ו/ט"ז exists to avoid, one
    hundreds-letter later. The exception is keyed off the last two digits, not off n itself."""
    assert hebrew_numeral(115) == 'קט"ו'
    assert hebrew_numeral(116) == 'קט"ז'
    assert hebrew_numeral(215) == 'רט"ו'
    assert hebrew_numeral(216) == 'רט"ז'


def test_the_real_bugged_sentences_are_fixed():
    assert (fix_raw_talmud_segment_refs('הגמרא ביומא 148:10 קובעת:')
           == 'הגמרא ביומא ע"ד ע"ב קובעת:')
    assert (fix_raw_talmud_segment_refs('רש"י על ההמשך (יומא 148:10) מבהיר')
           == 'רש"י על ההמשך (יומא ע"ד ע"ב) מבהיר')


def test_an_already_correct_citation_is_left_untouched():
    """The fingerprint (tractate + TWO consecutive integers) never matches a real citation — the
    amud there is always a letter ('ע"ב') or a bare colon, never a second integer — so this must
    never touch text that was already written correctly."""
    text = 'יומא עד ע"ב זה תקין ולא אמור להשתנות'
    assert fix_raw_talmud_segment_refs(text) == text


def test_unrelated_text_is_untouched():
    text = "תשובה רגילה בלי שום מספר או מסכת"
    assert fix_raw_talmud_segment_refs(text) == text


def test_a_nonsensical_daf_number_is_dropped_rather_than_shown():
    """If the arithmetic produces something no tractate has (way past Bava Batra's 176), the
    confusing digits are dropped rather than presenting a fake-looking daf number."""
    out = fix_raw_talmud_segment_refs("ביומא 9000:1 נאמר")
    assert "9000" not in out and "1" not in out.split("ביומא")[-1][:5]
    assert "ביומא" in out


def test_empty_and_none_input_is_safe():
    assert fix_raw_talmud_segment_refs("") == ""
    assert fix_raw_talmud_segment_refs(None) == ""
