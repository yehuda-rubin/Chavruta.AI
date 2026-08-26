"""mismatched_tanakh_citations + its two building blocks (src/chavruta/generation/grounded.py,
src/chavruta/intents/hebrew_refs.py) — the citation-cross-reference guard.

A real bug found live 2026-08-20: one QA answer quoted the SAME pasuk ("והאבדתי את הנפש ההיא...")
correctly as (ויקרא כג,ל) earlier in the response, then cited the identical phrase as (ויקרא יג,ל) —
Leviticus 13, tzaraat, wholly unrelated — a few lines later. `unverified_quotes` did not catch this:
the quoted WORDS genuinely are in the retrieved Gemara. What was wrong is a parenthetical
cross-reference back to the Torah pasuk itself, carrying no [S#] marker at all.

Every threshold here (_OWN_MAX, _ALT_MIN, the same-chapter exclusion) was calibrated against that
real production answer, not invented — see grounded.py::mismatched_tanakh_citations' docstring.
"""
from __future__ import annotations

from types import SimpleNamespace

from chavruta.generation.grounded import marker_numbers_in, mismatched_tanakh_citations
from chavruta.intents.hebrew_refs import detect_parenthetical_tanakh_citations


# ── marker_numbers_in ─────────────────────────────────────────────────────────────────────────
def test_standard_bracket_shapes():
    assert marker_numbers_in("ראה [S1] וגם [S2, S3]") == [1, 2, 3]


def test_a_non_standard_bracket_still_resolves():
    """Found live 2026-08-19: chavruta mode's own bespoke regex (`\\[\\s*S(\\d+)\\s*\\]`) missed
    "[source S1]" outright, silently dropping the citation instead of resolving it — this is the
    fix, reused instead of a second narrower regex."""
    assert marker_numbers_in("לפי [source S1] הדבר נכון") == [1]


def test_a_bracket_with_no_marker_is_ignored():
    assert marker_numbers_in("זה [כן] וגם [לא S]") == []


# ── detect_parenthetical_tanakh_citations ────────────────────────────────────────────────────
def test_plain_unmarked_gematria_is_parsed():
    """The shape a model actually writes — no geresh/gershayim on the multi-letter numeral. The
    general-purpose detect_tanakh_refs (query-understanding, hebrew_refs.py) REQUIRES a mark here
    specifically to avoid false positives in free user prose; a parenthetical citation is a
    different, safer context where that guard does not apply."""
    refs = [r for r, _, _ in detect_parenthetical_tanakh_citations("...עמה\" (ויקרא כג,ל)")]
    assert refs == ["Leviticus.23.30"]


def test_a_citation_with_a_space_after_the_comma_still_parses():
    refs = [r for r, _, _ in detect_parenthetical_tanakh_citations("(ויקרא יג, ל)")]
    assert refs == ["Leviticus.13.30"]


def test_spans_locate_the_citation_in_the_original_text():
    text = "מבוא (ויקרא כג, ל) סיום"
    ((ref, start, end),) = detect_parenthetical_tanakh_citations(text)
    assert ref == "Leviticus.23.30"
    assert text[start:end] == "(ויקרא כג, ל)"


# ── mismatched_tanakh_citations ───────────────────────────────────────────────────────────────
# Real corpus text (skeletons only matter; niqqud/cantillation intentionally kept, matching what
# the live corpus actually stores — see [[niqqud-recall-gap]]).
_LEVITICUS_23_30 = ("[ויקרא] Leviticus 23:30\nוְכָל־הַנֶּ֗פֶשׁ אֲשֶׁ֤ר תַּעֲשֶׂה֙ כָּל־מְלָאכָ֔ה "
                    "בְּעֶ֖צֶם הַיּ֣וֹם הַזֶּ֑ה וְהַֽאֲבַדְתִּ֛י אֶת־הַנֶּ֥פֶשׁ הַהִ֖וא מִקֶּ֥רֶב עַמָּֽהּ")
_LEVITICUS_13_30 = ("[ויקרא] Leviticus 13:30\nוְרָאָ֨ה הַכֹּהֵ֜ן אֶת־הַנֶּ֗גַע וְהִנֵּ֤ה מַרְאֵ֙הוּ֙ "
                    "עָמֹ֣ק מִן־הָע֔וֹר וּבוֹ֙ שֵׂעָ֣ר צָהֹ֔ב דָּ֑ק וְטִמֵּ֨א אֹת֜וֹ הַכֹּהֵ֗ן")
_LEVITICUS_23_31 = "[ויקרא] Leviticus 23:31\nכָּל־מְלָאכָ֖ה לֹ֣א תַעֲשׂ֑וּ חֻקַּ֤ת עוֹלָם֙ לְדֹרֹ֣תֵיכֶ֔ם בְּכֹ֖ל מֹשְׁבֹֽתֵיכֶֽם"


def _store(mapping: dict[str, str]):
    def fetch_refs(refs):
        return [SimpleNamespace(ref=r, text=mapping[r]) for r in refs if r in mapping]
    return fetch_refs


def test_the_real_2026_08_20_case_is_caught():
    """The model's own quote is not verbatim (word order shifted from the real pasuk) even in the
    CORRECT citation — this must still work despite that, which is why the guard uses n-gram
    overlap rather than an exact substring match."""
    text = (
        'הפסוק "וְהַנֶּפֶשׁ הַהִיא אֶהֱמִירֹתִי מִקֶּרֶב עַמָּהּ" (ויקרא כג,ל) מלמד יסוד חשוב. '
        'ואם נפשך לומר הרי הוא אומר (ויקרא יג, ל) והאבדתי את הנפש ההיא ענוי שהוא אבידת נפש '
        'ואיזה זה אכילה ושתיה, וזה עיקר הלימוד כולו.'
    )
    fetch_refs = _store({"Leviticus.23.30": _LEVITICUS_23_30, "Leviticus.13.30": _LEVITICUS_13_30})

    findings = mismatched_tanakh_citations(text, fetch_refs)

    assert len(findings) == 1
    assert findings[0].correct_ref == "Leviticus.23.30"
    assert findings[0].wrong_ref == "Leviticus.13.30"


def test_adjacent_verses_in_a_multi_verse_quotation_are_not_flagged():
    """Reproduced live: citing several consecutive verses as one continuous block makes a
    neighboring verse's content bleed into the window around any one citation. Same-chapter
    alternatives are excluded from 'better ref' for exactly this reason — this must stay silent."""
    text = (
        'שנאמר "וְכָל־הַנֶּפֶשׁ אֲשֶׁר תַּעֲשֶׂה" (ויקרא כג,ל) '
        'וממשיך "כָּל־מְלָאכָה לֹא תַעֲשׂוּ חֻקַּת עוֹלָם" (ויקרא כג,לא).'
    )
    fetch_refs = _store({"Leviticus.23.30": _LEVITICUS_23_30, "Leviticus.23.31": _LEVITICUS_23_31})

    assert mismatched_tanakh_citations(text, fetch_refs) == []


def test_a_single_citation_has_nothing_to_contradict_it():
    text = 'הפסוק "וְכָל־הַנֶּפֶשׁ" (ויקרא כג,ל) מלמד יסוד.'
    fetch_refs = _store({"Leviticus.23.30": _LEVITICUS_23_30})

    assert mismatched_tanakh_citations(text, fetch_refs) == []


def test_no_citations_at_all_returns_empty():
    assert mismatched_tanakh_citations("תשובה רגילה בלי שום ציטוט של פסוק.", _store({})) == []


def test_a_broken_fetch_never_raises():
    def boom(refs):
        raise RuntimeError("qdrant down")

    text = '(ויקרא כג,ל) ... (ויקרא יג, ל)'
    assert mismatched_tanakh_citations(text, boom) == []
