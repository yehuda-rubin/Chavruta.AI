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
