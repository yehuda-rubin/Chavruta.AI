"""One-language citation labels: work, chapter and section only (corpus/cite_labels.py)."""
import re

from app.search_service import ref_labels
from chavruta.corpus.cite_labels import cite_labels

LATIN = re.compile(r"[A-Za-z]")


def test_tanakh_label():
    assert ref_labels("Genesis 1:1") == ("בראשית א', א'", "Genesis 1:1")


def test_bavli_shows_daf_and_amud_not_the_internal_segment():
    assert cite_labels("Berakhot.3.1")["he"] == "ברכות ב' ע״א"
    assert cite_labels("Berakhot.4.2")["en"] == "Berakhot 2b"


def test_reader_page_keeps_a_verse_but_never_the_line_of_a_daf():
    assert ref_labels("Berakhot 3:2", full=True) == ("ברכות ב' ע״א", "Berakhot 2a")
    assert ref_labels("Genesis 1:3", full=True)[1] == "Genesis 1:3"


def test_reader_header_names_the_daf_not_a_chapter():
    from chavruta.corpus.cite_labels import section_he
    assert section_he("Shabbat 42:5") == 'דף כ"א ע״ב'
    assert section_he("Genesis 1:1") is None


def test_commentary_never_shows_its_own_index():
    assert cite_labels("Rashi_on_Genesis.1.1.1") == {
        "he": "רש\"י על בראשית א', א'", "en": "Rashi on Genesis 1:1", "who_he": "רש\"י", "who_en": "Rashi",
    }
    assert cite_labels("Tosafot_on_Berakhot.3.1.1")["he"] == "תוספות על ברכות ב' ע״א"
    assert cite_labels("Chizkuni,_Genesis.17.5.2")["en"] == "Chizkuni, Genesis 17:5"


def test_tosefta_and_mishnah_are_not_treated_as_bavli():
    assert ref_labels("Tosefta Shabbat 10:14")[1] == "Tosefta Shabbat 10:14"
    assert ref_labels("Mishnah Berakhot 1:1")[1] == "Mishnah Berakhot 1:1"


def test_parasha_and_roman_sections_are_translated():
    he = cite_labels("Chatam_Sofer_on_Torah,_Chayei_Sara.36")["he"]
    assert he == 'חתם סופר על התורה, חיי שרה ל"ו' and not LATIN.search(he)


def test_a_hebrew_label_never_carries_latin_letters():
    for ref in ("Yachin_on_Pirkei_Avot.5.9.1", "Shulchan_Arukh,_Orach_Chayim.310.1", "Birkat_Asher_on_Torah,_Numbers.16.17.5"):
        he = cite_labels(ref)["he"]
        assert he and not LATIN.search(he), (ref, he)


def test_unknown_work_uses_the_callers_hebrew_name_or_nothing():
    assert cite_labels("No_Such_Book.3.4")["he"] == ""
    assert cite_labels("Chayei_Adam,_Shabbat_and_Festivals.45.15", title_he="חיי אדם")["he"] == 'חיי אדם מ"ה, ט"ו'
