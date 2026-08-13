"""Calendar-claim verification (src/chavruta/generation/computed.py).

Fully offline and deterministic: the calendar is handed in as a CalendarFacts value, so nothing here
reaches Sefaria, the network, the database, or an LLM. The two tests that exercise the network path
at all assert that it is BOUNDED and that giving up reports unknown.

The centre of gravity is the false-positive line: a daf mentioned without a today-framing, a date
that merely looks like a daf ("היום שבת כ' באב"), and an ambiguous clause must all produce nothing.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from chavruta.calendar.sefaria_calendar import DafYomiInfo, ParshaInfo
from chavruta.generation import computed

_CHULLIN_104 = DafYomiInfo(tractate="Chullin", daf=104)
_SHOFTIM = ParshaInfo(name_en="Shoftim", name_he="שפטים", ref_range="Deuteronomy 16:18-21:9")
_FACTS = computed.CalendarFacts(daf=_CHULLIN_104, parsha=_SHOFTIM)
_NO_FACTS = computed.CalendarFacts()


# ── daf: the claim the production answer got wrong ──────────────────────────────

def test_correct_daf_claim_passes():
    check = computed.check_calendar_claims("היום לומדים חולין קד, ושם נאמר...", _FACTS)
    assert check.mismatches == []
    assert [c.stated for c in check.confirmed] == ["Chullin 104"]


def test_wrong_daf_claim_reports_both_values():
    check = computed.check_calendar_claims("היום לומדים חולין קה.", _FACTS)
    assert len(check.mismatches) == 1
    m = check.mismatches[0]
    assert (m.kind, m.stated, m.expected) == ("daf_yomi", "Chullin 105", "Chullin 104")
    assert "חולין" in m.span          # the caller can show the user what was flagged
    assert check.confirmed == []


def test_wrong_tractate_is_a_mismatch_even_with_the_right_number():
    check = computed.check_calendar_claims("הדף היומי הוא ברכות קד", _FACTS)
    assert [m.stated for m in check.mismatches] == ["Berakhot 104"]


@pytest.mark.parametrize("text, stated", [
    ('הדף היומי היום: בבא מציעא דף כ ע"ב', "Bava Metzia 20"),   # gershayim amud + explicit דף
    ("היום לומדים בבא מציעא דף כ", "Bava Metzia 20"),
    ('הדף היומי היום הוא חולין ק"ד', "Chullin 104"),            # gematria with gershayim
    ("היום לומדים חולין 104", "Chullin 104"),                    # digits
    ("היום מתחילים סנהדרין לה", "Sanhedrin 35"),                 # two-letter gematria, unmarked
])
def test_hebrew_numeral_and_amud_forms_parse(text, stated):
    claims = computed.extract_calendar_claims(text)
    assert [c.stated for c in claims] == [stated]


# ── the false-positive line ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    'הגמרא בחולין קד ע"ב דנה בזה.',                       # a plain citation
    "כפי שראינו במסכת ברכות דף ב, יש מחלוקת.",
    "היום לומדים על דיני בשר וחלב. הגמרא בחולין קד מביאה...",   # framing in a DIFFERENT clause
    "היום שבת כ' באב.",                                    # a date, not Shabbat 20 — no study cue
    "היום לומדים בשבת קודש.",                              # gematria 410, not a daf
])
def test_daf_without_today_framing_is_not_flagged(text):
    assert computed.extract_calendar_claims(text) == []
    assert computed.check_calendar_claims(text, _FACTS).mismatches == []


def test_two_dapim_in_one_clause_is_too_ambiguous_to_claim():
    text = "היום לומדים חולין קה בניגוד לברכות ה, שם הסוגיה אחרת"
    assert computed.extract_calendar_claims(text) == []


# ── parsha ──────────────────────────────────────────────────────────────────────

def test_correct_parsha_claim_passes_across_ktiv_spellings():
    # The answer writes male ("שופטים"); Sefaria's calendar answers haser ("שפטים").
    check = computed.check_calendar_claims("פרשת השבוע היא פרשת שופטים", _FACTS)
    assert check.mismatches == []
    assert [c.stated for c in check.confirmed] == ["שופטים"]


def test_wrong_parsha_claim_reports_both_values():
    check = computed.check_calendar_claims("השבוע קוראים את פרשת ראה.", _FACTS)
    assert len(check.mismatches) == 1
    m = check.mismatches[0]
    assert (m.kind, m.stated, m.expected) == ("parsha", "ראה", "שפטים")


def test_either_half_of_a_doubled_parsha_is_correct():
    facts = computed.CalendarFacts(parsha=ParshaInfo(
        name_en="Vayakhel-Pekudei", name_he="ויקהל-פקודי", ref_range="Exodus 35:1-40:38"))
    for stated in ("ויקהל", "פקודי", "ויקהל-פקודי"):
        check = computed.check_calendar_claims(f"פרשת השבוע היא פרשת {stated}", facts)
        assert check.mismatches == [], stated
        assert len(check.confirmed) == 1


@pytest.mark.parametrize("text", [
    "פרשת שופטים עוסקת במינוי שופטים.",          # no this-week framing at all
    "השבוע למדנו על שופטים ושוטרים.",            # 'שופטים' as a word, not hung off פרשת
    "השבוע נעסוק בספר שופטים.",                  # the BOOK of Judges
    "בפרשת השבוע יש דיון על עדים.",              # framing, but no parsha named
])
def test_parsha_mention_without_framing_is_not_flagged(text):
    assert [c for c in computed.extract_calendar_claims(text) if c.kind == "parsha"] == []
    assert computed.check_calendar_claims(text, _FACTS).mismatches == []


# ── unknown, never "mismatch" ───────────────────────────────────────────────────

def test_unavailable_calendar_yields_unknown_not_mismatch():
    check = computed.check_calendar_claims(
        "היום לומדים חולין קה, והשבוע קוראים את פרשת ראה.", _NO_FACTS)
    assert check.mismatches == []
    assert check.confirmed == []
    assert {c.kind for c in check.unknown} == {"daf_yomi", "parsha"}


def test_parsha_name_the_table_cannot_map_is_unknown_not_mismatch():
    facts = computed.CalendarFacts(parsha=ParshaInfo(
        name_en="???", name_he="פרשה שאיננה בטבלה", ref_range="Genesis 1:1-6:8"))
    check = computed.check_calendar_claims("פרשת השבוע היא פרשת ראה", facts)
    assert check.mismatches == []
    assert [c.stated for c in check.unknown] == ["ראה"]


# ── facts resolution: cache first, bounded network, Jerusalem "today" ───────────

def test_resolve_facts_reads_the_cache_and_never_touches_the_network(monkeypatch):
    import chavruta.calendar.sefaria_calendar as cal

    monkeypatch.setattr(cal, "_fetch_calendar_items",
                        lambda: pytest.fail("the checker must not call Sefaria"))
    rows = {
        ("daf_yomi", "2026-08-13"): '{"tractate": "Chullin", "daf": 104}',
        ("parsha", "2026-08-09"): ('{"name_en": "Shoftim", "name_he": "\\u05e9\\u05e4\\u05d8\\u05d9\\u05dd",'
                                   ' "ref_range": "Deuteronomy 16:18-21:9", "haftarah_ref": ""}'),
    }
    now = datetime(2026, 8, 13, 9, 0, tzinfo=ZoneInfo("Asia/Jerusalem"))
    facts = computed.resolve_facts(load_cached=lambda k, d: rows.get((k, d)), now=now)
    assert facts.daf == _CHULLIN_104
    assert facts.parsha.name_he == "שפטים"


def test_no_cache_reader_means_unknown_rather_than_a_lookup():
    facts = computed.resolve_facts(now=datetime(2026, 8, 13, 9, 0, tzinfo=ZoneInfo("Asia/Jerusalem")))
    assert facts == computed.CalendarFacts(daf=None, parsha=None)


def test_a_slow_calendar_is_abandoned_at_the_deadline(monkeypatch):
    """The whole point of the deadline: sefaria_calendar retries for up to ~56s, and this check runs
    on a request a user is already waiting on."""
    import time

    import chavruta.calendar.sefaria_calendar as cal

    def _hang():
        time.sleep(30)
        return _CHULLIN_104

    monkeypatch.setattr(cal, "resolve_daf_yomi", _hang)
    monkeypatch.setattr(cal, "resolve_parsha", _hang)
    started = time.monotonic()
    facts = computed.resolve_facts(network_deadline_s=0.05)
    assert facts == computed.CalendarFacts(daf=None, parsha=None)   # unknown, not a wrong answer
    assert time.monotonic() - started < 5


def test_today_is_computed_in_jerusalem_not_utc():
    # 22:30 UTC on the 12th is already the 13th in Israel; a UTC "today" would read yesterday's daf
    # as today's and call a correct answer wrong.
    late_utc = datetime(2026, 8, 12, 22, 30, tzinfo=ZoneInfo("UTC"))
    assert computed._today(late_utc) == date(2026, 8, 13)


def test_cache_keys_match_the_buckets_the_api_writes():
    # daf_yomi buckets by day; parsha by the week's Sunday (Thursday 2026-08-13 → 2026-08-09).
    assert computed.cache_key("daf_yomi", date(2026, 8, 13)) == "2026-08-13"
    assert computed.cache_key("parsha", date(2026, 8, 13)) == "2026-08-09"
    assert computed.cache_key("parsha", date(2026, 8, 9)) == "2026-08-09"
