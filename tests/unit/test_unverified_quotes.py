"""unverified_quotes (citation-faithfulness guard, src/chavruta/generation/grounded.py).

A real bug found live: a user asked about a Shulchan Arukh passage, and the model quoted it
verbatim — but the source text itself contains Hebrew abbreviation gershayim (בר"ה, ואע"ג — very
common in halachic sources). The old regex used gershayim/" as BOTH the quote-boundary delimiter
and ordinary text, so a faithfully-quoted source got split at its own internal abbreviation marks
into two truncated fragments, each of which then (correctly, but for the wrong reason) failed the
corpus-containment check — a real, accurate quote got flagged as fabricated.
"""

from __future__ import annotations

from chavruta.generation.grounded import (
    misattributed_quotes,
    misattribution_note,
    unverified_quotes,
)
from chavruta.retrieval.base import RankedHit


def _hit(text: str) -> RankedHit:
    return RankedHit(chunk_id="c1", ref="Shulchan Arukh, Orach Chayim.113.2", text=text, score=0.9)


def test_quote_containing_an_abbreviation_gershayim_is_not_flagged():
    source = ('הנוהגים לשחות בר"ה וי"ה כשאומרים זכרנו ומי כמוך צריכים לזקוף כשמגיעים לסוף הברכה: '
               'הגה ואע"ג דבאבות כורע בסוף הברכה מכל מקום צריך לזקוף מעט בסוף זכרנו')
    answer = f'נאמר: "{source}".'
    assert unverified_quotes(answer, [_hit(source)]) == []


def test_a_genuinely_fabricated_quote_is_still_flagged():
    """The fix must not make the guard toothless — an invented quote with no abbreviation marks at
    all must still be caught."""
    answer = 'נאמר: "זהו ציטוט מומצא לחלוטין שאינו נמצא בשום מקור שסופק כאן".'
    assert unverified_quotes(answer, [_hit("טקסט מקור אמיתי שאינו קשור לציטוט")]) != []


def test_no_sources_short_circuits_to_empty():
    assert unverified_quotes('נאמר: "כל טקסט שהוא כאן למעלה מהאורך המינימלי".', []) == []


def test_abbreviation_at_the_very_edge_of_the_quote_is_not_mistaken_for_a_boundary():
    """A closing quote that lands right after an abbreviation mark (…סק"א") must still close the
    quote at the REAL boundary (the second "), not swallow past it."""
    source = 'עיין בזה בשו"ע ובנושאי כליו לענין הדין הנדון כאן באריכות רבה ובפרטי הפרטים'
    answer = f'כתוב: "{source}" עיין שם.'
    assert unverified_quotes(answer, [_hit(source)]) == []


# ── Fix (2026-08-11): the abbreviation mask was too broad and cost the guard its teeth ──────────
# Hebrew attaches one-letter prefixes straight onto an opening quote — ש"אסור לטלטל…", ו"היה…".
# That opening mark also sits between two Hebrew letters, so the mask deleted it, the quotation
# became invisible to the checker, and a FABRICATED quote written that way passed unflagged. A
# false negative here is far worse than the false positive the mask was added for.

_PROSE = ('כתב השו"ע באו"ח סי\' ש"י ס"א, ובהג"ה של הרמ"א שם, וכן דעת המ"ב בשעה"צ, '
          'שהעיקר הוא ש"{quote}", וכ"כ בכה"ח ובא"ר, ועיין בשו"ת חת"ס או"ח סי\' ק"ה.')
_SOURCE = "אסור לטלטל מוקצה בשבת אלא לצורך גופו או מקומו"


def test_fabricated_quote_attached_to_a_hebrew_prefix_is_caught():
    """The regression: an invented quote opened with ש" inside dense abbreviation prose."""
    fake = "מותר לטלטל כל מוקצה בשבת ללא הגבלה כלל"
    flagged = unverified_quotes(_PROSE.format(quote=fake), [_hit(_SOURCE)])
    assert flagged, "a fabricated quote opened with a ש\" prefix must not slip through"
    assert fake[:20] in flagged[0]


def test_faithful_quote_attached_to_a_hebrew_prefix_is_not_flagged():
    """…and the same construction quoting the source correctly must stay silent."""
    assert unverified_quotes(_PROSE.format(quote=_SOURCE), [_hit(_SOURCE)]) == []


def test_dense_abbreviations_alone_still_produce_no_quote():
    """The original false positive must stay fixed: abbreviations are not quote delimiters."""
    text = 'רש"י ורמב"ם ושו"ע ובב"ק ותשפ"ה — אין כאן שום ציטוט, רק ראשי תיבות רבים.'
    assert unverified_quotes(text, [_hit(_SOURCE)]) == []


def test_two_letter_abbreviation_is_still_masked():
    """Abbreviations ending in two letters (מהדו"ק-style) must remain masked, not read as quotes."""
    text = 'עיין בשו"ע ובמהדו"ק ובאבה"ע לענין זה, ואין כאן ציטוט כלל ועיקר בכלל.'
    assert unverified_quotes(text, [_hit(_SOURCE)]) == []


# ── Fix (2026-08-12): the guard reported the model's OWN prose as fabricated quotes ─────────────
# Found in a 26-question run: the regex let any quote mark pair with any later one, so a single
# short quoted word threw the parity off and every following pair was wrong. Spans are now paired
# in order, and a span containing a [S#] marker is never a quote — markers are written around
# sources, never inside one.

def test_short_quoted_word_does_not_throw_off_the_pairing():
    """ה\"ייאוש\" (…) — one quoted word, then ordinary prose that must not be read as a quote."""
    text = 'ה"ייאוש" (ויתור על החפץ) כבר קיים באופן עקרוני, גם אם לא התבטא בפועל אצל הבעלים.'
    assert unverified_quotes(text, [_hit("טקסט מקור כלשהו שאין בו קשר")]) == []


def test_span_containing_a_citation_marker_is_not_a_quote():
    text = 'הכלל הוא "מתייחסת לכל ערי ארץ ישראל [S14], והתקנה הורחבה" לדעת רבים ועוד.'
    assert unverified_quotes(text, [_hit("טקסט מקור כלשהו שאין בו קשר")]) == []


def test_a_quote_spanning_a_line_break_is_not_treated_as_one():
    text = 'פתח "מילה אחת כאן בשורה\nושורה חדשה לגמרי ממשיכה" וסיים.'
    assert unverified_quotes(text, [_hit("טקסט מקור כלשהו שאין בו קשר")]) == []


def test_the_guard_still_catches_a_fabrication_after_a_short_quoted_word():
    """The parity fix must not become a way for a real fabrication to hide."""
    source = "אסור לטלטל מוקצה בשבת אלא לצורך גופו או מקומו"
    text = ('ה"ייאוש" הוא מושג נפרד, אבל כאן נאמר '
            '"מותר לטלטל כל מוקצה בשבת בלי שום הגבלה כלל ועיקר" וזה לא נמצא.')
    flagged = unverified_quotes(text, [_hit(source)])
    assert flagged and "מותר לטלטל כל מוקצה" in flagged[0]


# ── misattributed_quotes (2026-08-13): a real quote under the wrong name ────────────────────────
# The hole unverified_quotes cannot see: it asks whether a quoted span exists in SOME source, never
# whether it exists in THE source the prose credits. Reproduced against the real functions with two
# Sukkah 41a chunks — Tosafot's words introduced as רש"י passed every guard clean.
#
# The design is deliberately biased toward silence, so most of what follows pins the NON-findings:
# a guard that cries wolf on faithful answers gets switched off, and then it catches nothing.

_RASHI_REF = "Rashi_on_Sukkah.41.1.1"
_TOSAFOT_REF = "Tosafot_on_Sukkah.41.1.1"
_BASE_REF = "Sukkah.41.1"

_RASHI = "ואני אומר שבית המקדש העתיד להיבנות בנוי ומשוכלל הוא יגלה ויבוא משמים"
_TOSAFOT = "ולעולם יבנה בידי אדם ואין סתירה בין הדברים אלא שהמלאכה נגמרת מלמעלה"
_BASE = "בראשונה היה לולב ניטל במקדש שבעה ובמדינה יום אחד משחרב בית המקדש"


def _src(ref: str, text: str) -> RankedHit:
    return RankedHit(chunk_id=ref, ref=ref, text=text, score=0.9)


def _sugya() -> list[RankedHit]:
    return [_src(_RASHI_REF, _RASHI), _src(_TOSAFOT_REF, _TOSAFOT), _src(_BASE_REF, _BASE)]


def test_tosafot_words_attributed_to_rashi_are_flagged():
    """THE pinned scenario. Note what the assertions say together: unverified_quotes is right to stay
    silent (the quote is genuinely in the corpus), and the answer is still a fabrication."""
    answer = f'רש"י כותב במפורש [S1]: "{_TOSAFOT}"'
    assert unverified_quotes(answer, _sugya()) == []
    found = misattributed_quotes(answer, _sugya())
    assert len(found) == 1
    assert found[0].claimed == "rashi"
    assert found[0].found_in == ("tosafot",)
    assert "יוחס" in misattribution_note("he", found)


def test_correct_attribution_is_never_flagged():
    for ref_name, quote in (('רש"י', _RASHI), ("תוספות", _TOSAFOT)):
        answer = f'{ref_name} כותב כאן [S1]: "{quote}"'
        assert misattributed_quotes(answer, _sugya()) == [], ref_name


def test_a_quote_with_no_commentator_named_is_never_flagged():
    answer = f'נאמר בסוגיה [S2]: "{_TOSAFOT}"'
    assert misattributed_quotes(answer, _sugya()) == []


def test_a_base_text_quote_beside_a_commentator_name_is_never_flagged():
    """A commentator quoting the daf he comments on is the normal shape of Torah prose. The base text
    has no commentator to disagree with, so the mere adjacency of a name must not fire."""
    answer = f'רש"י מפרש את דברי הגמרא [S3]: "{_BASE}"'
    assert misattributed_quotes(answer, _sugya()) == []


def test_a_hebrew_prefix_on_the_name_does_not_hide_the_attribution():
    """ולרש"י / שרש"י — Hebrew glues prefixes onto the name; the guard must still read it as Rashi."""
    for named in ('ולרש"י', 'שרש"י', 'הרש"י'):
        answer = f'{named} כאן [S1] לשון מפורשת: "{_TOSAFOT}"'
        assert [f.claimed for f in misattributed_quotes(answer, _sugya())] == ["rashi"], named


def test_gershayim_spelling_of_the_name_resolves_the_same():
    answer = f'רש״י כותב במפורש [S1]: "{_TOSAFOT}"'
    assert [f.claimed for f in misattributed_quotes(answer, _sugya())] == ["rashi"]


def test_a_quote_full_of_abbreviations_is_still_attributed_correctly():
    """Interplay with _protect_abbreviations: the mask must neither hide the misattribution nor
    manufacture one out of a faithful quote."""
    tosafot = 'ואע"ג דבעלמא אמרינן הכי הכא שאני משום דגלי קרא בהדיא ולא ילפינן מיניה'
    sources = [_src(_RASHI_REF, _RASHI), _src(_TOSAFOT_REF, tosafot)]
    assert misattributed_quotes(f'תוספות כותבים [S2]: "{tosafot}"', sources) == []
    assert [f.claimed for f in misattributed_quotes(f'רש"י כותב [S1]: "{tosafot}"', sources)] \
        == ["rashi"]


def test_two_names_in_one_sentence_are_too_ambiguous_to_flag():
    """'רש"י ותוספות נחלקו… וכאן נאמר: "…"' genuinely does not say whose words follow. Guessing here
    is how a guard earns a reputation for crying wolf, so it stays silent."""
    answer = f'רש"י ותוספות נחלקו בזה, וכאן נאמר [S2]: "{_TOSAFOT}"'
    assert misattributed_quotes(answer, _sugya()) == []


def test_a_name_in_the_previous_sentence_does_not_introduce_this_quote():
    answer = f'רש"י עוסק בבניין העתיד. וכך נאמר כאן [S2]: "{_TOSAFOT}"'
    assert misattributed_quotes(answer, _sugya()) == []


def test_a_trailing_attribution_after_the_quote_wins():
    answer = f'רש"י דן בזה, וכן נאמר: "{_TOSAFOT}" (תוספות שם).'
    assert misattributed_quotes(answer, _sugya()) == []


def test_no_source_by_the_named_commentator_means_no_finding():
    """The strictest condition, and deliberate: without Rashi's own text among the sources we cannot
    tell a misquote from a nested attribution ('הרמב"ן בשם רש"י'), so we say nothing."""
    answer = f'רש"י כותב במפורש: "{_TOSAFOT}"'
    assert misattributed_quotes(answer, [_src(_TOSAFOT_REF, _TOSAFOT)]) == []


def test_a_fabricated_quote_is_left_to_unverified_quotes():
    """No double-reporting: a quote in no source at all is the other guard's finding."""
    answer = 'רש"י כותב במפורש [S1]: "מקור שלא נכתב מעולם ואינו נמצא בשום ספר שבעולם כלל ועיקר"'
    assert misattributed_quotes(answer, _sugya()) == []
    assert unverified_quotes(answer, _sugya()) != []


def test_a_short_quoted_phrase_is_too_generic_to_attribute():
    answer = 'רש"י כותב [S1]: "ואין סתירה"'
    assert misattributed_quotes(answer, _sugya()) == []


def test_an_english_name_resolves_too():
    answer = f'Rashi writes explicitly [S1]: "{_TOSAFOT}"'
    assert [f.claimed for f in misattributed_quotes(answer, _sugya())] == ["rashi"]
    assert "Rashi" in misattribution_note("en", misattributed_quotes(answer, _sugya()))


def test_no_sources_and_no_quotes_short_circuit():
    assert misattributed_quotes(f'רש"י כותב: "{_TOSAFOT}"', []) == []
    assert misattributed_quotes("", _sugya()) == []
    assert misattribution_note("he", []) == ""


def test_the_dense_abbreviation_prose_still_produces_no_finding():
    """The original false positive that _protect_abbreviations exists for, re-run through this guard:
    a wall of abbreviations contains no quote, so it can contain no misattribution either."""
    text = 'רש"י ורמב"ם ושו"ע ובב"ק ותשפ"ה — אין כאן שום ציטוט, רק ראשי תיבות רבים.'
    assert misattributed_quotes(text, _sugya()) == []
