"""unverified_quotes (citation-faithfulness guard, src/chavruta/generation/grounded.py).

A real bug found live: a user asked about a Shulchan Arukh passage, and the model quoted it
verbatim — but the source text itself contains Hebrew abbreviation gershayim (בר"ה, ואע"ג — very
common in halachic sources). The old regex used gershayim/" as BOTH the quote-boundary delimiter
and ordinary text, so a faithfully-quoted source got split at its own internal abbreviation marks
into two truncated fragments, each of which then (correctly, but for the wrong reason) failed the
corpus-containment check — a real, accurate quote got flagged as fabricated.
"""

from __future__ import annotations

from chavruta.generation.grounded import unverified_quotes
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
