"""One-language citation labels for the UI: a Hebrew reader sees Hebrew only, an English reader English only.

The corpus names a passage by its position inside a work — `Chatam_Sofer_on_Torah,_Chayei_Sara.36`,
`Berakhot.3.1`, `Rashi_on_Genesis.1.1.1`. Three things in that string mean nothing to a person:
the amud-linear daf number, the trailing line / comment index, and English section names inside a
Hebrew label. A learner needs the work, the chapter and the section — "ברכות ב ע"א", "רש"י על בראשית א', א'" —
so that is all this produces. Hebrew section names that have no translation are left out, not shown in
English: a Hebrew label with a Latin fragment is worse than a slightly shorter one.

`cite_labels(ref)` takes either spelling of a ref (corpus 'Berakhot.3.1' or the reader's 'Berakhot 3:1').
"""
from __future__ import annotations

import re

from chavruta.corpus.refs import _is_bavli, _load_hebrew_titles, hebrew_numeral

_REF = re.compile(r"^(?P<title>.+?)[ .](?P<nums>\d+(?:[.:]\d+)*)$")
_ROMAN = re.compile(r"^(?=[IVXLCDM]+$)M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _fold(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _roman(s: str) -> int | None:
    if not _ROMAN.match(s or ""):
        return None
    total = 0
    for a, b in zip(s, s[1:] + " "):
        total += -_ROMAN_VAL[a] if _ROMAN_VAL.get(b, 0) > _ROMAN_VAL[a] else _ROMAN_VAL[a]
    return total


# Section names that follow a work's title after a comma. Parashot are spelled many ways across works, so they
# are matched folded (letters only).
_SEGMENTS_HE = {
    "bereshit": "בראשית", "bereishit": "בראשית", "genesis": "בראשית", "noach": "נח", "noah": "נח",
    "lechlecha": "לך לך", "vayera": "וירא", "chayeisarah": "חיי שרה", "chayeisara": "חיי שרה", "toldot": "תולדות", "toldos": "תולדות", "vayetzei": "ויצא", "vayetze": "ויצא",
    "vayishlach": "וישלח", "vayeshev": "וישב", "miketz": "מקץ", "mikeitz": "מקץ", "vayigash": "ויגש",
    "vayechi": "ויחי", "shemot": "שמות", "shemos": "שמות", "exodus": "שמות", "vaera": "וארא", "bo": "בא",
    "beshalach": "בשלח", "yitro": "יתרו", "mishpatim": "משפטים", "terumah": "תרומה", "tetzaveh": "תצוה",
    "kitisa": "כי תשא", "kitissa": "כי תשא", "vayakhel": "ויקהל", "pekudei": "פקודי", "vayikra": "ויקרא",
    "leviticus": "ויקרא", "tzav": "צו", "shemini": "שמיני", "shmini": "שמיני", "tazria": "תזריע",
    "metzora": "מצורע", "achreimot": "אחרי מות", "acharemot": "אחרי מות", "achareimot": "אחרי מות",
    "acheremot": "אחרי מות", "acharei": "אחרי מות", "kedoshim": "קדושים", "emor": "אמור", "behar": "בהר",
    "bechukotai": "בחוקותי", "bechukosai": "בחוקותי", "bamidbar": "במדבר", "numbers": "במדבר", "nasso": "נשא",
    "naso": "נשא", "behaalotcha": "בהעלותך", "shlach": "שלח", "shelach": "שלח", "korach": "קרח",
    "chukat": "חקת", "chukkat": "חקת", "balak": "בלק", "pinchas": "פינחס", "matot": "מטות", "masei": "מסעי",
    "devarim": "דברים", "deuteronomy": "דברים", "vaetchanan": "ואתחנן", "eikev": "עקב", "ekev": "עקב",
    "reeh": "ראה", "shoftim": "שופטים", "kiteitzei": "כי תצא", "kitetzei": "כי תצא", "kitavo": "כי תבוא", "nitzavim": "נצבים", "vayeilech": "וילך", "vayelech": "וילך", "haazinu": "האזינו",
    "vezotshaberakhah": "וזאת הברכה", "vezotthaberakhah": "וזאת הברכה",
    # Shulchan Arukh and Tur parts
    "orachchayim": "אורח חיים", "orachchaim": "אורח חיים", "yorehdeah": "יורה דעה", "evenhaezer": "אבן העזר",
    "choshenmishpat": "חושן משפט",
    # structure
    "introduction": "הקדמה", "intro": "הקדמה", "authorsintroduction": "הקדמת המחבר", "preface": "פתח דבר",
    "authorspreface": "הקדמת המחבר", "foreword": "מבוא", "appendix": "נספח", "addenda": "תוספות",
    "additions": "תוספות", "approbations": "הסכמות", "index": "מפתח", "bibliography": "רשימת מקורות",
    "epilogue": "אחרית דבר", "conclusion": "סיכום", "petichta": "פתיחתא", "partone": "חלק א", "parttwo": "חלק ב",
    "partthree": "חלק ג", "parti": "חלק א", "partii": "חלק ב", "partiii": "חלק ג", "volumei": "כרך א",
    "volumeii": "כרך ב", "firsttreatise": "מאמר ראשון", "secondtreatise": "מאמר שני", "thirdtreatise": "מאמר שלישי",
    "fifthgate": "שער חמישי", "firstgate": "שער ראשון", "positivecommandments": "מצוות עשה",
    "negativecommandments": "מצוות לא תעשה", "shabbatandfestivals": "שבת ומועדים",
    "legalstatutes": "חוקים", "hilchotshabbat": "הלכות שבת",
}


def segment_he(seg: str) -> str | None:
    return _SEGMENTS_HE.get(_fold(seg))


def _title_entry(title: str) -> dict | None:
    return _load_hebrew_titles().get(title)


def _he_title(title: str, nums: list[int]) -> tuple[str | None, list[int]]:
    """Hebrew title of a work (comma sections translated or dropped). Roman-numeral sections become the leading
    numbers: 'Or HaTzafun, Vayikra, V' + [11] -> ('אור הצפון, ויקרא', [5, 11])."""
    entry = _title_entry(title)
    if entry and entry.get("he"):
        return entry["he"], nums
    if "," not in title:
        return None, nums
    head, *rest = [p.strip() for p in title.split(",")]
    h = _title_entry(head)
    if not (h and h.get("he")):
        return None, nums
    parts, lead = [h["he"]], []
    for seg in rest:
        if (r := _roman(seg)) is not None:
            lead.append(r)
            continue
        if (e := _title_entry(seg)) and e.get("he"):
            parts.append(e["he"])
        elif he := segment_he(seg):
            parts.append(he)
        # no Hebrew for it: leave it out
    return ", ".join(parts), lead + nums


def _en_title(title: str, nums: list[int]) -> tuple[str, list[int]]:
    if "," not in title:
        return title, nums
    head, *rest = [p.strip() for p in title.split(",")]
    lead, keep = [], [head]
    for seg in rest:
        if (r := _roman(seg)) is not None:
            lead.append(r)
        else:
            keep.append(seg)
    return ", ".join(keep), lead + nums


def _bavli(title: str) -> bool:
    entry = _title_entry(title)
    if entry and entry.get("cat"):
        return _is_bavli(entry)
    base = title.split(" on ", 1)[1] if " on " in title else ""
    return bool(base) and _is_bavli(_title_entry(base))


def _split(ref: str) -> tuple[str, list[int]] | None:
    m = _REF.match((ref or "").strip())
    if not m:
        return None
    return m.group("title").replace("_", " ").strip(), [int(n) for n in re.split(r"[.:]", m.group("nums"))]


def _position(title: str, nums: list[int], he: bool, full: bool = False) -> str:
    """The part of the position a reader can use: chapter and section (or daf and amud); never the line or comment
    index inside it. `full` keeps the segment of a base text (the verse, the line of a daf) for the reader page,
    where every segment is shown on its own; a commentary's own index is never shown."""
    commentary = " on " in title
    if _bavli(title) and nums:
        daf, amud = (nums[0] + 1) // 2, "a" if nums[0] % 2 else "b"
        pos = f"{hebrew_numeral(daf)} {'ע״א' if amud == 'a' else 'ע״ב'}" if he else f"{daf}{amud}"
        return pos          # the line inside a daf is an internal index: never shown, even on the reader page
    kept = nums if (full and not commentary) else nums[:2]
    return ", ".join(hebrew_numeral(n) for n in kept) if he else ":".join(str(n) for n in kept)


def section_he(ref: str) -> str | None:
    """'דף כ"א ע"ב' for a Bavli ref (the reader's header), None for any other work."""
    sp = _split(ref)
    if sp is None or not _bavli(sp[0]) or " on " in sp[0]:
        return None
    return "דף " + _position(sp[0], sp[1], True)


def cite_labels(ref: str, *, title_he: str = "", full: bool = False) -> dict[str, str]:
    """{'he': 'רש"י על בראשית א', א'', 'en': 'Rashi on Genesis 1:1', 'who_he': 'רש"י', 'who_en': 'Rashi'}.
    Empty strings where nothing can be said in that language."""
    sp = _split(ref)
    if sp is None:
        return {"he": "", "en": "", "who_he": "", "who_en": ""}
    title, nums = sp
    he_title, he_nums = _he_title(title, nums)
    if not he_title and title_he:       # a work the title tables do not know: the caller's own Hebrew name for it
        he_title = title_he
    en_title, en_nums = _en_title(title, nums)
    who_en = re.split(r" on |,", en_title)[0].strip()
    who_he = re.split(r" על |,", he_title)[0].strip() if he_title else ""
    return {
        "he": f"{he_title} {_position(title, he_nums, True, full)}".strip() if he_title else "",
        "en": f"{en_title} {_position(title, en_nums, False, full)}".strip(),
        "who_he": who_he,
        "who_en": who_en,
    }
