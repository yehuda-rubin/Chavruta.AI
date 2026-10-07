"""Hebrew / English citation labels shown beside each reader segment."""
from app.search_service import ref_labels


def test_tanakh_label():
    assert ref_labels("Genesis 1:1") == ("בראשית א׳, א׳", "Genesis 1:1")


def test_bavli_amudim_are_unfolded():
    assert ref_labels("Berakhot 3:1") == ("ברכות ב׳ ע״א, א׳", "Berakhot 2a:1")
    assert ref_labels("Berakhot 4:2")[1] == "Berakhot 2b:2"


def test_tosefta_and_mishnah_are_not_treated_as_bavli():
    assert ref_labels("Tosefta Shabbat 10:14") == ("תוספתא שבת י׳, י״ד", "Tosefta Shabbat 10:14")
    assert ref_labels("Mishnah Berakhot 1:1")[1] == "Mishnah Berakhot 1:1"


def test_commentary_on_bavli_uses_the_daf():
    assert ref_labels("Tosafot on Berakhot 3:1:1")[1] == "Tosafot on Berakhot 2a:1:1"


def test_unknown_title_never_empty():
    he, en = ref_labels("No Such Book 3:4")
    assert he and en == "No Such Book 3:4"
