"""Landmark / indirect-reference resolution (Phase 2, spec 002-query-understanding).

Maps well-known *indirect* phrases to concrete corpus refs so questions that never
name a verse explicitly still anchor:

    "מה המחלוקת בין רש\"י לרמב\"ן בפסוק הראשון בתורה?"  →  named_refs = ["Genesis.1.1"]

Two layers: a curated absolute map (famous passages) and relative patterns
("הפסוק הראשון ב<ספר>", "הדף הראשון ב<מסכת>"). Pure, offline, data-extendable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from chavruta.intents.hebrew_refs import HE_BOOKS, HE_TRACTATES, _book_alt, gematria

# Talmud perek → opening ref in the CORPUS format (built from Sefaria by
# scripts/build_talmud_perek_index.py). {English tractate: {"he":…, "perakim":[ref per perek]}}.
try:
    _PEREK_INDEX = json.loads(
        (Path(__file__).parent / "data" / "talmud_perek_daf.json").read_text(encoding="utf-8"))
except Exception:
    _PEREK_INDEX = {}

# Hebrew ordinal words → number (perek names). Higher perakim are addressed by gematria/digits.
_HE_ORDINALS = {
    "ראשון": 1, "שני": 2, "שלישי": 3, "רביעי": 4, "חמישי": 5, "שישי": 6, "ששי": 6,
    "שביעי": 7, "שמיני": 8, "תשיעי": 9, "עשירי": 10,
}
_ORD_ALT = "|".join(sorted(_HE_ORDINALS, key=len, reverse=True))


def _perek_num(token: str) -> int | None:
    token = token.strip()
    if token in _HE_ORDINALS:
        return _HE_ORDINALS[token]
    core = token.rstrip("'׳\"״")
    if core.isdigit():
        return int(core)
    # A Hebrew numeral counts only if it's a SINGLE letter ('ג') or carries a geresh/gershayim
    # ('ג׳', 'י״א'); a bare multi-letter token is rejected — otherwise demonstratives like 'זה'/'הוא'
    # ('פרק זה' = "this chapter") gematria-sum to a bogus perek number and anchor the wrong daf.
    marked = any(c in token for c in "'׳\"״")
    if core and all("א" <= c <= "ת" for c in core) and (len(core) == 1 or marked):
        return gematria(core) or None
    return None

# ── Absolute landmarks: famous passages with a fixed ref ─────────────────────────
ABSOLUTE_LANDMARKS: dict[str, str] = {
    # Opening of Torah & Creation
    "הפסוק הראשון בתורה": "Genesis.1.1",
    "הפסוק הראשון של התורה": "Genesis.1.1",
    "פסוק ראשון בתורה": "Genesis.1.1",
    "תחילת התורה": "Genesis.1.1",
    "ריש התורה": "Genesis.1.1",
    "בראשית ברא": "Genesis.1.1",
    "בריאת העולם": "Genesis.1.1",
    "מעשה בראשית": "Genesis.1",
    "גן עדן": "Genesis.2",
    "עץ הדעת": "Genesis.2.17",
    "קין והבל": "Genesis.4",
    "תיבת נח": "Genesis.6",
    "המבול": "Genesis.6",
    "דור המבול": "Genesis.6",
    "מגדל בבל": "Genesis.11",
    "דור הפלגה": "Genesis.11",
    "לך לך": "Genesis.12",
    "ברית בין הבתרים": "Genesis.15",
    "ברית מילה": "Genesis.17.10",
    "המול לכם כל זכר": "Genesis.17.10",
    "הכנסת אורחים": "Genesis.18.2",
    "ביקור חולים": "Genesis.18.1",
    "מהפכת סדום": "Genesis.19",
    "סדום ועמורה": "Genesis.19",
    "פרשת העקדה": "Genesis.22",
    "פרשת העקידה": "Genesis.22",
    "עקדת יצחק": "Genesis.22",
    "עקידת יצחק": "Genesis.22",
    "העקדה": "Genesis.22",
    "העקידה": "Genesis.22",
    "סולם יעקב": "Genesis.28.12",
    "חלום יעקב": "Genesis.28.12",
    "מאבק יעקב והמלאך": "Genesis.32.25",
    "גיד הנשה": "Genesis.32.33",
    "מפגש יעקב ועשו": "Genesis.33",
    "מכירת יוסף": "Genesis.37",
    "חלומות יוסף": "Genesis.37",
    "חלומות פרעה": "Genesis.41",
    "ברכת יעקב לבניו": "Genesis.49",

    # Exodus / Shemot
    "הסנה הבוער": "Exodus.3",
    "מעשה הסנה": "Exodus.3",
    "עשרת המכות": "Exodus.7",
    "עשר המכות": "Exodus.7",
    "מכות מצרים": "Exodus.7",
    "קרבן פסח": "Exodus.12",
    "מצוות קידוש החודש": "Exodus.12.2",
    "החודש הזה לכם": "Exodus.12.2",
    "ביעור חמץ": "Exodus.12.15",
    "תשביתו שאר מבתיכם": "Exodus.12.15",
    "אכילת מצה": "Exodus.12.18",
    "סיפור יציאת מצרים": "Exodus.13.8",
    "והגדת לבנך": "Exodus.13.8",
    "קריעת ים סוף": "Exodus.14",
    "שירת הים": "Exodus.15",
    "מתן מן": "Exodus.16",
    "מלחמת עמלק": "Exodus.17.8",
    "מעמד הר סיני": "Exodus.19",
    "מתן תורה": "Exodus.19",
    "עשרת הדיברות": "Exodus.20",
    "עשרת הדברות": "Exodus.20",
    "זכור את יום השבת": "Exodus.20.8",
    "שביתת שבת": "Exodus.20.8",
    "שמירת שבת": "Exodus.20.8",
    "כיבוד אב ואם": "Exodus.20.12",
    "כבד את אביך ואת אמך": "Exodus.20.12",
    "לא תרצח": "Exodus.20.13",
    "לא תנאף": "Exodus.20.13",
    "לא תגנוב": "Exodus.20.13",
    "לא תענה ברעך": "Exodus.20.13",
    "לא תחמוד": "Exodus.20.14",
    "לא תשא שמע שווא": "Exodus.23.1",
    "לא תשא שמע שוא": "Exodus.23.1",
    "שמע שווא": "Exodus.23.1",
    "אחרי רבים להטות": "Exodus.23.2",
    "לא תבשל גדי בחלב אמו": "Exodus.23.19",
    "בשר בחלב": "Exodus.23.19",
    "חטא העגל": "Exodus.32",
    "מעשה העגל": "Exodus.32",
    "שלוש עשרה מידות": "Exodus.34.6",
    "י\"ג מידות הרחמים": "Exodus.34.6",
    "יג מידות": "Exodus.34.6",

    # Leviticus / Vayikra
    "נדב ואביהוא": "Leviticus.10",
    "סימני כשרות בבהמה": "Leviticus.11.3",
    "סימני כשרות בדגים": "Leviticus.11.9",
    "סימני כשרות בעופות": "Leviticus.11.13",
    "שרצים": "Leviticus.11.41",
    "יום הכיפורים": "Leviticus.16.29",
    "יום כיפור": "Leviticus.16.29",
    "ועיניתם את נפשותיכם": "Leviticus.16.29",
    "איסור אכילה ביום כיפור": "Leviticus.16.29",
    "שעיר לעזאזל": "Leviticus.16.8",
    "איסור אכילת דם": "Leviticus.17.10",
    "וחי בהם": "Leviticus.18.5",
    "פיקוח נפש": "Leviticus.18.5",
    "איסור עריות": "Leviticus.18",
    "קדושים תהיו": "Leviticus.19.2",
    "איש אמו ואביו תיראו": "Leviticus.19.3",
    "מתנות עניים": "Leviticus.19.9",
    "לקט שכחה ופאה": "Leviticus.19.9",
    "פאה": "Leviticus.19.9",
    "לקט": "Leviticus.19.9",
    "לא תגנובו": "Leviticus.19.11",
    "לא תכחשו": "Leviticus.19.11",
    "לא תשקרו איש בעמיתו": "Leviticus.19.11",
    "לא תשבעו בשמי לשקר": "Leviticus.19.12",
    "לא תעשוק": "Leviticus.19.13",
    "לא תגזול": "Leviticus.19.13",
    "איסור גזל": "Leviticus.19.13",
    "הלנת שכר": "Leviticus.19.13",
    "לא תלין פעולת שכיר": "Leviticus.19.13",
    "לפני עיוור לא תיתן מכשול": "Leviticus.19.14",
    "לפני עיוור לא תתן מכשול": "Leviticus.19.14",
    "לפני עיוור": "Leviticus.19.14",
    "לפני עור": "Leviticus.19.14",
    "בצדק תשפוט עמיתך": "Leviticus.19.15",
    "לדון לכף זכות": "Leviticus.19.15",
    # Lashon Hara & Rechilut
    "איסור לשון הרע": "Leviticus.19.16",
    "לשון הרע": "Leviticus.19.16",
    "איסור רכילות": "Leviticus.19.16",
    "רכילות": "Leviticus.19.16",
    "לא תלך רכיל": "Leviticus.19.16",
    "לא תלך רכיל בעמיך": "Leviticus.19.16",
    "רכיל בעמיך": "Leviticus.19.16",
    "לא תעמוד על דם רעך": "Leviticus.19.16",
    "לא תעמוד על דם": "Leviticus.19.16",
    "הצלת נפשות": "Leviticus.19.16",
    "לא תשנא את אחיך": "Leviticus.19.17",
    "לא תשנא את אחיך בלבבך": "Leviticus.19.17",
    "הוכח תוכיח": "Leviticus.19.17",
    "הוכח תוכיח את עמיתך": "Leviticus.19.17",
    "מצוות תוכחה": "Leviticus.19.17",
    "לא תקום ולא תטור": "Leviticus.19.18",
    "לא תקום": "Leviticus.19.18",
    "לא תטור": "Leviticus.19.18",
    "ואהבת לרעך כמוך": "Leviticus.19.18",
    "ואהבת לרעך": "Leviticus.19.18",
    "מצוות קידוש השם": "Leviticus.22.32",
    "ונקדשתי בתוך בני ישראל": "Leviticus.22.32",
    "חילול השם": "Leviticus.22.32",
    "מצוות סוכה": "Leviticus.23.42",
    "בסוכות תשבו": "Leviticus.23.42",
    "בסוכות תשבו שבעת ימים": "Leviticus.23.42",
    "ארבעת המינים": "Leviticus.23.40" ,
    "ולקחתם לכם ביום הראשון": "Leviticus.23.40",
    "ולקחתם לכם": "Leviticus.23.40",
    "ספירת העומר": "Leviticus.23.15",
    "וספרתם לכם": "Leviticus.23.15",
    "אונאת ממון": "Leviticus.25.14",
    "אל תונו איש את אחיו": "Leviticus.25.14",
    "אונאת דברים": "Leviticus.25.17",
    "לא תונו איש את עמיתו": "Leviticus.25.17",
    "ריבית": "Leviticus.25.36",
    "איסור ריבית": "Leviticus.25.36",
    "הלוואה בריבית": "Leviticus.25.36",
    "אל תקח מאתו נשך ותרבית": "Leviticus.25.36",
    "נשך ותרבית": "Leviticus.25.36",
    "מצוות שמיטה": "Leviticus.25.2",
    "שנת השמיטה": "Leviticus.25.2",
    "שמיטת קרקעות": "Leviticus.25.2",
    "מצוות יובל": "Leviticus.25.10",
    "שנת היובל": "Leviticus.25.10",

    # Numbers / Bamidbar
    "ברכת כהנים": "Numbers.6.24",
    "יברכך ה' וישמרך": "Numbers.6.24",
    "פסח שני": "Numbers.9",
    "חטא המתאוננים": "Numbers.11",
    "קברות התאווה": "Numbers.11",
    "מרים ואהרן במשה": "Numbers.12",
    "חטא המרגלים": "Numbers.13",
    "פרשת המרגלים": "Numbers.13",
    "מצוות ציצית": "Numbers.15.37",
    "פרשת ציצית": "Numbers.15.37",
    "וראיתם אותו וזכרתם": "Numbers.15.39",
    "מחלוקת קורח": "Numbers.16",
    "קורח ועדתו": "Numbers.16",
    "פרשת קורח": "Numbers.16",
    "פרשת פרה אדומה": "Numbers.19",
    "פרה אדומה": "Numbers.19",
    "מי מריבה": "Numbers.20",
    "חטא מי מריבה": "Numbers.20",
    "נחש הנחושת": "Numbers.21",
    "פרשת בלק": "Numbers.22",
    "בלעם ואתונו": "Numbers.22",
    "מה טובו אוהליך יעקב": "Numbers.24.5",
    "מעשה זמרי וכזבי": "Numbers.25",
    "קנאות פנחס": "Numbers.25.11",
    "בנות צלפחד": "Numbers.27",
    "נחלת בנות צלפחד": "Numbers.27",
    "פרשת נדרים": "Numbers.30",
    "הפרת נדרים": "Numbers.30",
    "ערי מקלט": "Numbers.35",

    # Deuteronomy / Devarim
    "ונשמרתם מאד לנפשותיכם": "Deuteronomy.4.15",
    "שמירת הנפש": "Deuteronomy.4.15",
    "שמור את יום השבת": "Deuteronomy.5.12",
    "קריאת שמע": "Deuteronomy.6.4",
    "שמע ישראל": "Deuteronomy.6.4",
    "ואהבת את ה' אלוהיך": "Deuteronomy.6.5",
    "מצוות תפילין": "Deuteronomy.6.8",
    "וקשרתם לאות על ידך": "Deuteronomy.6.8",
    "מצוות מזוזה": "Deuteronomy.6.9",
    "וכתבתם על מזוזות ביתך": "Deuteronomy.6.9",
    "שבעת המינים": "Deuteronomy.8.8",
    "שבעת המינים של ארץ ישראל": "Deuteronomy.8.8",
    "ארץ חיטה ושעורה": "Deuteronomy.8.8",
    "ברכת המזון": "Deuteronomy.8.10",
    "ואכלת ושבעת וברכת": "Deuteronomy.8.10",
    "פרשת והיה אם שמוע": "Deuteronomy.11.13",
    "מצוות צדקה": "Deuteronomy.15.8",
    "צדקה": "Deuteronomy.15.8",
    "פתוח תפתח את ידך": "Deuteronomy.15.8",
    "שמיטת כספים": "Deuteronomy.15.1",
    "עבד עברי": "Deuteronomy.15.12",
    "מצוות מינוי שופטים": "Deuteronomy.16.18",
    "שופטים ושוטרים תתן לך": "Deuteronomy.16.18",
    "צדק צדק תרדוף": "Deuteronomy.16.20",
    "לא תסור מן הדבר": "Deuteronomy.17.11",
    "מצוות מינוי מלך": "Deuteronomy.17.14",
    "מינוי מלך": "Deuteronomy.17.14",
    "שום תשים עליך מלך": "Deuteronomy.17.15",
    "איסור כישוף": "Deuteronomy.18.10",
    "תמים תהיה עם ה' אלוהיך": "Deuteronomy.18.13",
    "עדים זוממים": "Deuteronomy.19.19",
    "ועשיתם לו כאשר זמם": "Deuteronomy.19.19",
    "מלחמת רשות ומלחמת מצווה": "Deuteronomy.20",
    "איסור בל תשחית": "Deuteronomy.20.19",
    "בל תשחית": "Deuteronomy.20.19",
    "עגלה ערופה": "Deuteronomy.21",
    "אשת יפת תואר": "Deuteronomy.21.10",
    "בן סורר ומורה": "Deuteronomy.21.18",
    "קבורת המת": "Deuteronomy.21.23",
    "השבת אבידה": "Deuteronomy.22.1",
    "השבת אבדה": "Deuteronomy.22.1",
    "מצוות השבת אבידה": "Deuteronomy.22.1",
    "לא תוכל להתעלם": "Deuteronomy.22.3",
    "איסור לא ילבש": "Deuteronomy.22.5",
    "לא ילבש גבר": "Deuteronomy.22.5",
    "מצוות שילוח הקן": "Deuteronomy.22.6",
    "שילוח הקן": "Deuteronomy.22.6",
    "שלוח הקן": "Deuteronomy.22.6",
    "שלח תשלח את האם": "Deuteronomy.22.7",
    "מצוות מעקה": "Deuteronomy.22.8",
    "ועשית מעקה לגגך": "Deuteronomy.22.8",
    "איסור כלאיים": "Deuteronomy.22.9",
    "שעטנז": "Deuteronomy.22.11",
    "איסור ריבית לאחיך": "Deuteronomy.23.20",
    "לא תשיך לאחיך": "Deuteronomy.23.20",
    "מוצא שפתיך תשמור": "Deuteronomy.23.24",
    "מצוות גירושין": "Deuteronomy.24.1",
    "ספר כריתות": "Deuteronomy.24.1",
    "זכירת מעשה מרים": "Deuteronomy.24.9",
    "מעשה מרים": "Deuteronomy.24.9",
    "זכור את אשר עשה ה' למרים": "Deuteronomy.24.9",
    "ייבום וחליצה": "Deuteronomy.25.5",
    "מצוות ייבום": "Deuteronomy.25.5",
    "מצוות חליצה": "Deuteronomy.25.7",
    "איפה ואיפה": "Deuteronomy.25.13",
    "מידות ומשקלות": "Deuteronomy.25.13",
    "זכירת מעשה עמלק": "Deuteronomy.25.17",
    "זכור את אשר עשה לך עמלק": "Deuteronomy.25.17",
    "מחיית עמלק": "Deuteronomy.25.19",
    "פרשת ביכורים": "Deuteronomy.26",
    "מקרא ביכורים": "Deuteronomy.26.5",
    "ארמי אובד אבי": "Deuteronomy.26.5",
    "פרשת התוכחה": "Deuteronomy.28",
    "הנסתרות לה' אלוהינו": "Deuteronomy.29.28",
    "מצוות תשובה": "Deuteronomy.30.2",
    "לא בשמים היא": "Deuteronomy.30.12",
    "ובחרת בחיים": "Deuteronomy.30.19",
    "מצוות הקהל": "Deuteronomy.31.12",
    "מצוות כתיבת ספר תורה": "Deuteronomy.31.19",
    "כתבו לכם את השירה הזאת": "Deuteronomy.31.19",
    "שירת האזינו": "Deuteronomy.32",
    "האזינו השמים": "Deuteronomy.32.1",
    "ברכת משה": "Deuteronomy.33",
    "וזאת הברכה": "Deuteronomy.33.1",

    # Famous Tanakh Narratives & Passages
    "שירת דבורה": "Judges.5",
    "גדעון והמדיינים": "Judges.7",
    "שמשון ודלילה": "Judges.16",
    "תפילת חנה": "I Samuel.2",
    "דוד וגוליית": "I Samuel.17",
    "משפט שלמה": "I Kings.3.16",
    "אליהו בהר הכרמל": "I Kings.18",
    "כרם נבות היזרעאלי": "I Kings.21",
    "כרם נבות": "I Kings.21",
    "מרכבת יחזקאל": "Ezekiel.1",
    "מעשה מרכבה": "Ezekiel.1",
    "חזון העצמות היבשות": "Ezekiel.37",
    "יונה במעי הדג": "Jonah.2",
    "נבואת זכריה": "Zechariah.1",
    "חזון אחרית הימים": "Isaiah.2",
    "קדוש קדוש קדוש": "Isaiah.6.3",
    "אשת חיל": "Proverbs.31.10",
    "הבל הבלים": "Ecclesiastes.1.2",
    "מגילת רות": "Ruth.1",
    "מגילת אסתר": "Esther.1",

    # Famous Talmudic Sugyot (Daf References)
    "שניים אוחזין": "Bava Metzia.2a",
    "שנים אוחזין": "Bava Metzia.2a",
    "שניים אוחזין בטלית": "Bava Metzia.2a",
    "המפקיד אצל חברו": "Bava Metzia.33b",
    "תנורו של עכנאי": "Bava Metzia.59b",
    "תנור של עכנאי": "Bava Metzia.59b",
    "השוכר את הפועלים": "Bava Metzia.75b",
    "פועלים שהטעו זה את זה": "Bava Metzia.75b",
    "כל המשנה ידו על התחתונה": "Bava Metzia.75b",
    "קניין חצר": "Bava Metzia.11a",
    "קניין ארבע אמות": "Bava Metzia.10a",
    "ארבעה אבות נזיקין": "Bava Kamma.2a",
    "הכונס צאן לדיר": "Bava Kamma.55b",
    "חזקת הבתים": "Bava Batra.28a",
    "חזקת קרקעות": "Bava Batra.28a",
    "מאי חנוכה": "Shabbat.21b",
    "נר חנוכה": "Shabbat.21b",
    "סוכה ישנה": "Sukkah.2a",
    "סוכה שגבוהה למעלה מעשרים אמה": "Sukkah.2a",
    "מאימתי קורין את שמע": "Berakhot.2a",
    "האיש מקדש": "Kiddushin.41a",
    "האומר לשלוחו": "Kiddushin.41b",
    "אין שליח לדבר עבירה": "Kiddushin.42b",
    "שלוחו של אדם כמותו": "Berakhot.34b",
    "יהרג ואל יעבור": "Sanhedrin.74a",
    "הבא להורגך השכם להורגו": "Sanhedrin.72a",
    "דיני ממונות בשלושה": "Sanhedrin.2a",
}

# English famous-passage map — English queries otherwise ride entirely on cross-lingual dense (which
# buries the terse Hebrew base verse). Matched case-insensitively as a substring. Extendable as data.
# Keys are matched at WORD BOUNDARIES (not raw substring) and are kept specific — a bare "shema"
# collides with the name "Shemaiah", "in the beginning" is a common discourse phrase, etc.
ENGLISH_LANDMARKS: dict[str, str] = {
    # Lashon Hara / Speech
    "lashon hara": "Leviticus.19.16", "evil speech": "Leviticus.19.16",
    "talebearer": "Leviticus.19.16", "gossip": "Leviticus.19.16",
    "slander": "Leviticus.19.16", "do not go as a talebearer": "Leviticus.19.16",
    "do not bear false witness": "Exodus.20.13", "false report": "Exodus.23.1",

    # Famous Passages & Prayers
    "shema yisrael": "Deuteronomy.6.4", "the shema": "Deuteronomy.6.4",
    "ten commandments": "Exodus.20", "decalogue": "Exodus.20",
    "binding of isaac": "Genesis.22", "akedah": "Genesis.22", "the akeda": "Genesis.22",
    "creation of the world": "Genesis.1.1", "first verse of the torah": "Genesis.1.1",
    "love your neighbor": "Leviticus.19.18", "love your fellow": "Leviticus.19.18",
    "love your neighbor as yourself": "Leviticus.19.18",
    "song of the sea": "Exodus.15", "priestly blessing": "Numbers.6.24",
    "garden of eden": "Genesis.2", "tree of knowledge": "Genesis.2.17",
    "cain and abel": "Genesis.4", "tower of babel": "Genesis.11",
    "the golden calf": "Exodus.32", "golden calf": "Exodus.32",
    "seven species": "Deuteronomy.8.8",
    "ten plagues": "Exodus.7", "plagues of egypt": "Exodus.7",
    "burning bush": "Exodus.3",
    "splitting of the sea": "Exodus.14", "parting of the red sea": "Exodus.14",
    "giving of the torah": "Exodus.19", "revelation at sinai": "Exodus.19",
    "jacob's ladder": "Genesis.28",
    "noah's ark": "Genesis.6", "the flood": "Genesis.6",
    "covenant between the pieces": "Genesis.15",
    "twelve spies": "Numbers.13", "sin of the spies": "Numbers.13",
    "red heifer": "Numbers.19", "korah": "Numbers.16",
    "balak and balaam": "Numbers.22",

    # Core Mitzvot
    "returning lost items": "Deuteronomy.22.1", "lost property": "Deuteronomy.22.1",
    "lost object": "Deuteronomy.22.1", "appointing a king": "Deuteronomy.17.14",
    "appoint a king": "Deuteronomy.17.14",
    "sending away the mother bird": "Deuteronomy.22.6", "shiluach haken": "Deuteronomy.22.6",
    "honoring parents": "Exodus.20.12", "honor your father and mother": "Exodus.20.12",
    "keeping shabbat": "Exodus.20.8", "remember the sabbath": "Exodus.20.8",
    "tzitzit": "Numbers.15.37", "fringes": "Numbers.15.37",
    "tefillin": "Deuteronomy.6.8", "phylacteries": "Deuteronomy.6.8",
    "mezuzah": "Deuteronomy.6.9", "grace after meals": "Deuteronomy.8.10",
    "birkat hamazon": "Deuteronomy.8.10",
    "four species": "Leviticus.23.40", "lulav and etrog": "Leviticus.23.40",
    "sukkah": "Leviticus.23.42", "dwell in booths": "Leviticus.23.42",
    "yom kippur": "Leviticus.16.29", "day of atonement": "Leviticus.16.29",
    "shmita": "Leviticus.25.2", "sabbatical year": "Leviticus.25.2",
    "jubilee": "Leviticus.25.10", "yovel": "Leviticus.25.10",
    "charity": "Deuteronomy.15.8", "tzedakah": "Deuteronomy.15.8",
    "interest": "Leviticus.25.36", "usury": "Leviticus.25.36",
    "do not steal": "Leviticus.19.11", "do not murder": "Exodus.20.13",
    "stumbling block": "Leviticus.19.14", "do not put a stumbling block": "Leviticus.19.14",
    "do not hate your brother": "Leviticus.19.17", "rebuke your neighbor": "Leviticus.19.17",
    "do not take revenge": "Leviticus.19.18", "do not bear a grudge": "Leviticus.19.18",
    "circumcision": "Genesis.17.10", "brit milah": "Genesis.17.10",
    "cities of refuge": "Numbers.35", "parsha of tzitzit": "Numbers.15.37",
    "do not destroy": "Deuteronomy.20.19", "bal tashchit": "Deuteronomy.20.19",
}
_EN_LANDMARK_RE = {p: re.compile(rf"\b{re.escape(p)}\b") for p in ENGLISH_LANDMARKS}

# ── Relative landmarks: pattern → resolver ───────────────────────────────────────
_HE_BOOK_ALT = _book_alt(HE_BOOKS)
_HE_TRACTATE_ALT = _book_alt(HE_TRACTATES)

# "the first verse of the Torah", tolerant of ה/ב prefixes: "בפסוק הראשון בתורה",
# "הפסוק הראשון של התורה", "תחילת התורה", "ריש התורה".
_TORAH_FIRST_RE = re.compile(
    r"(?:[הב]?פסוק\s+(?:ה)?ראשון\s+(?:ב|של\s+)?(?:ה)?(?:תורה|חומש)"
    r"|(?:ב?תחילת|ריש)\s+(?:ה)?(?:תורה|חומש))"
)

# The words that may sit between "the first verse of" and the book itself. Hebrew stacks them freely
# — "של ספר בראשית", "בספר שמות", "בבראשית" — and each layer is optional, so they are composed rather
# than enumerated. Enumerating them is what went wrong before: the list held "של " and "ספר " and
# "בספר " but not "של ספר ", so "הפסוק הראשון של ספר בראשית" resolved to nothing while
# "הפסוק הראשון בבראשית" resolved fine. A question that names its verse in the more formal register
# simply lost its anchor.
_OF_THE_BOOK = r"(?:של\s+)?(?:ה?ספר\s+|ב(?:ה?ספר\s+)?)?"
_OF_THE_TRACTATE = r"(?:של\s+)?(?:ה?מסכת\s+|ב(?:ה?מסכת\s+)?)?"

# "הפסוק הראשון בבראשית" / "הפסוק הראשון בספר שמות" / "תחילת ספר ויקרא"
# / "הפסוק הראשון של ספר בראשית"
_FIRST_VERSE_RE = re.compile(
    rf"(?:[הב]?פסוק\s+(?:ה)?ראשון|פסוק\s+ראשון|ב?תחילת|ריש)\s+"
    rf"{_OF_THE_BOOK}(?P<book>{_HE_BOOK_ALT})"
)

# "הדף הראשון בבבא מציעא" / "תחילת מסכת ברכות" / "תחילת בבא מציעא" → tractate opens at daf 2a.
# "מסכת" is optional: people say "תחילת בבא מציעא" far more often than they say the full form, and
# requiring the word meant "מה מפרש רש\"י על תחילת בבא מציעא" produced no ref at all — so anchoring
# never ran and retrieval answered with Rashi on some other daf entirely.
_FIRST_DAF_RE = re.compile(
    rf"(?:ה?דף\s+(?:ה)?ראשון|ב?תחילת|ריש)\s+"
    rf"{_OF_THE_TRACTATE}(?P<tractate>{_HE_TRACTATE_ALT})"
)

# "פרק שלישי בסנהדרין" / "פרק ג' בבבא מציעא" / "פרק 3 בגיטין" (prefix-tolerant: "הדף הראשון בפרק…").
_PEREK_RE = re.compile(
    rf"פרק\s+(?P<ord>{_ORD_ALT}|[א-ת]{{1,3}}['׳]?|\d+)\s+"
    rf"(?:ב|של\s+|ב?מסכת\s+|ד)?(?P<tractate>{_HE_TRACTATE_ALT})"
)


def resolve_landmarks(text: str) -> list[str]:
    """All landmark refs found in the question, de-duplicated, order-preserving."""
    refs: list[str] = []

    def add(ref: str) -> None:
        if ref not in refs:
            refs.append(ref)

    # "first verse of the Torah" (prefix-tolerant) → Genesis.1.1
    if _TORAH_FIRST_RE.search(text):
        add("Genesis.1.1")

    # Absolute phrases (longest first so "הפסוק הראשון בתורה" beats "תחילת התורה" overlap)
    for phrase in sorted(ABSOLUTE_LANDMARKS, key=len, reverse=True):
        if phrase in text:
            add(ABSOLUTE_LANDMARKS[phrase])

    # English famous passages — WORD-BOUNDARY match (case-insensitive), longest first for specificity.
    low = text.lower()
    for phrase in sorted(ENGLISH_LANDMARKS, key=len, reverse=True):
        if _EN_LANDMARK_RE[phrase].search(low):
            add(ENGLISH_LANDMARKS[phrase])

    for m in _FIRST_VERSE_RE.finditer(text):
        add(f"{HE_BOOKS[m.group('book')]}.1.1")

    # First daf of a tractate → its opening daf 2a (amud form; the anchoring path converts it to the
    # corpus amud-linear ref via with_ref_variants).
    for m in _FIRST_DAF_RE.finditer(text):
        add(f"{HE_TRACTATES[m.group('tractate')]}.2a")

    # "פרק <ordinal> ב<מסכת>" → the perek's opening ref from the Sefaria-built index.
    for m in _PEREK_RE.finditer(text):
        tractate = HE_TRACTATES.get(m.group("tractate"))
        n = _perek_num(m.group("ord"))
        perak = (_PEREK_INDEX.get(tractate) or {}).get("perakim") or []
        if tractate and n and 1 <= n <= len(perak) and perak[n - 1]:
            add(perak[n - 1])

    return refs
