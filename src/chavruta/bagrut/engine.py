"""Core Bagrut Mode (מצב בגרויות) engine — Spec 010 (specs/010-bagrut-mode/plan.md).

Provides:
- Subject, track, unit-level, and action detection and multi-turn resolution
- Clean-room curriculum & Aramaic/Rubric scaffold loading (`data/bagrut_curriculum.yaml`)
- Guard against unattached past exam queries (`is_unattached_past_exam_query`, Principle I)
- Core Bagrut commentator boosting (`boost_bagrut_hits`)
- Grounded prompt builders for downloadable Bagrut files (`build_bagrut_file_job_md`) and
  interactive practice / rubric-based answer checking (`build_bagrut_chat_messages`)
- Output splitting (`split_bagrut_files`) for `===BAGRUT_SUMMARY===`, `===BAGRUT_EXAM===`,
  `===BAGRUT_RUBRIC===`, and `===ORDER===`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

try:
    from chavruta.corpus import audience as audience_ctx
except ImportError:
    audience_ctx = None  # type: ignore[assignment]
from chavruta.corpus.refs import (
    hebrew_display_ref,
    talmud_english_display_ref,
    talmud_hebrew_display_ref,
)
from chavruta.generation.grounded import QUOTE_REF_RULE, QUOTE_REF_RULE_HE, source_body
from chavruta.intents.hebrew_refs import HE_BOOKS, HE_TRACTATES
try:
    from chavruta.llm.base import append_minor_safety
except ImportError:
    def append_minor_safety(system: str, lang: str = "he") -> str:  # type: ignore[misc]
        return system

BAGRUT_SUBJECTS: tuple[str, ...] = ("tanakh", "gemara", "toshba", "machshava")
BAGRUT_TRACKS: tuple[str, ...] = ("mmd", "mamlachti")
BAGRUT_UNITS: tuple[str, ...] = ("2", "3", "5")
BAGRUT_ACTIONS: tuple[str, ...] = ("practice", "check", "summary", "exam")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CURRICULUM_PATH = _REPO_ROOT / "data" / "bagrut_curriculum.yaml"

_DEFAULT_CURRICULUM: dict[str, Any] = {
    "version": 1,
    "subjects": {
        "tanakh": {
            "id": "tanakh",
            "title_he": 'תנ"ך',
            "title_en": "Tanakh (Hebrew Bible)",
            "tracks": ["mmd", "mamlachti"],
            "units": [2, 3, 5],
            "core_commentators": [
                "rashi",
                "ramban",
                "ibn_ezra",
                "rashbam",
                "sforno",
                "radak",
                "malbim",
                "metzudat_david",
                "metzudat_tzion",
                "metzudat_zion",
            ],
            "track_details": {
                "mmd": {
                    "title_he": 'תנ"ך חמ"ד (ממלכתי-דתי)',
                    "title_en": "Tanakh — State-Religious Track (MMD)",
                    "exam_codes": ["2551", "2575", "2585"],
                    "units_supported": [3, 5],
                    "focus_he": (
                        'לימוד תנ"ך בעיון ובבקיאות לאור פרשנות הראשונים והאחרונים: זיהוי הקושי בפסוק, '
                        "הבחנה בין פשט לדרש, השוואת שיטות מפרשים (רש\"י, רמב\"ן, אבן עזרא, רשב\"ם, ספורנו, רד\"ק, מלבי\"ם, מצודות), "
                        "וניתוח קטע שלא נלמד (Unseen)."
                    ),
                    "focus_en": (
                        "In-depth (Iyun) and broad-knowledge (Bekiut) Bible study through classical commentators: "
                        "identifying textual difficulties, distinguishing pshat from drash, comparing commentators, "
                        "and analyzing an unseen passage."
                    ),
                },
                "mamlachti": {
                    "title_he": 'תנ"ך ממלכתי (כללי)',
                    "title_en": "Tanakh — General State Track (Mamlachti)",
                    "exam_codes": ["1281", "0581"],
                    "units_supported": [2, 5],
                    "focus_he": (
                        "קריאה צמודה של הטקסט המקראי, אמצעים אומנותיים ורטוריים (מילה מנחה, תקבולת, כינוי, "
                        "אירוניה, אנלוגיה, מבנה כיאסטי), השוואה פנים-מקראית, חוק וחברה במקרא, ומנהיגות ונבואה."
                    ),
                    "focus_en": (
                        "Close reading of the biblical text, literary and rhetorical devices (leitwort, parallelism, "
                        "chiasmus, analogy, irony), intra-biblical comparison, biblical law and society."
                    ),
                },
            },
        },
        "gemara": {
            "id": "gemara",
            "title_he": "גמרא (תלמוד בבלי)",
            "title_en": "Gemara (Babylonian Talmud)",
            "tracks": ["mmd", "mamlachti"],
            "units": [2, 3, 5],
            "core_commentators": [
                "rashi",
                "tosafot",
                "rambam",
                "shulchan_aruch",
                "bartenura",
                "mishnah_berurah",
            ],
            "track_details": {
                "mmd": {
                    "title_he": 'גמרא חמ"ד — לקט מצוות, סוגיות ועיון',
                    "title_en": "Gemara MMD — Talmudic Sugyot & In-Depth Iyun",
                    "exam_codes": ["5391", "5291", "6281"],
                    "units_supported": [3, 5],
                    "focus_he": (
                        "ניתוח מבנה הסוגיה (שקלא וטריא), זיהוי מונחי יסוד בארמית ותפקידם הלוגי, הבחנה בין "
                        "דברי תנאים לדברי אמוראים, הבהרת הסברות שבבסיס המחלוקות, ובעיון (5 יח\"ל) — לימוד "
                        "מעמיק של רש\"י ותוספות על הדף (קושיא, תירוץ, אוקימתא ונפקא מינה)."
                    ),
                    "focus_en": (
                        "Analyzing the structure of the Talmudic sugya (shakla vetarya), identifying Aramaic structural "
                        "terms and their logical roles, distinguishing Tannaitic from Amoraic statements, and studying Rashi and Tosafot."
                    ),
                },
                "mamlachti": {
                    "title_he": "תורה שבעל פה ותרבות ישראל — סוגיות תלמודיות",
                    "title_en": "Oral Law & Talmudic Culture (General Track)",
                    "exam_codes": ["5291"],
                    "units_supported": [2, 5],
                    "focus_he": (
                        'קריאה מונחית במקורות חז"ל (משנה, אגדה וסוגיות תלמודיות נבחרות), הבנת הדילמה הערכית '
                        "והמשפטית, וביאור מונחי יסוד בשפת התלמוד."
                    ),
                    "focus_en": (
                        "Guided reading in rabbinic texts (Mishnah, Aggadah, and selected Talmudic sugyot), "
                        "understanding ethical and legal dilemmas, and explaining core Talmudic terms."
                    ),
                },
            },
        },
        "toshba": {
            "id": "toshba",
            "title_he": 'תושב"ע (משנה והלכה)',
            "title_en": "Toshba (Mishnah & Halacha)",
            "tracks": ["mmd", "mamlachti"],
            "units": [2, 3, 5],
            "core_commentators": [
                "bartenura",
                "rambam",
                "shulchan_aruch",
                "mishnah_berurah",
                "rashi",
            ],
            "track_details": {
                "mmd": {
                    "title_he": 'תושב"ע חמ"ד — משנה, הלכה ואירועונים לימודיים',
                    "title_en": "Toshba MMD — Mishnah, Halachic Progression & Exam Case Studies",
                    "exam_codes": ["5391", "5381"],
                    "units_supported": [3, 5],
                    "focus_he": (
                        'פירוק מבני של המשנה (כותרת/נושא, מקרה, דין, טעם ומחלוקת), פירוש ר"ע מברטנורא והרמב"ם, '
                        "השתלשלות ההלכה מן המשנה והגמרא אל השולחן ערוך והמשנה ברורה, וניתוח \"אירועון הלכתי\" "
                        "לימודי לבחינה (בכפוף לעקרון VIII: לימוד עיוני לבגרות בלבד, אינו פסק הלכה למעשה)."
                    ),
                    "focus_en": (
                        "Structural breakdown of the Mishnah (case, ruling, rationale, dispute), Bartenura and Rambam "
                        "commentaries, halachic progression to Shulchan Arukh and Mishnah Berurah, and educational "
                        "halachic case studies for exam preparation (subject to Principle VIII: academic study only, never a practical psak)."
                    ),
                },
                "mamlachti": {
                    "title_he": "משנה ויצירה תלמודית — מסלול ממלכתי",
                    "title_en": "Mishnah & Rabbinic Literature — General Track",
                    "exam_codes": ["5291"],
                    "units_supported": [2, 5],
                    "focus_he": (
                        "הכרת עולם המשנה וההלכה, הבנת מבנה המשנה (מקרה, דין וטעם), וניתוח דילמות מוסריות וחברתיות בדברי חז\"ל."
                    ),
                    "focus_en": (
                        "Introduction to the world of the Mishnah and Halacha, understanding Mishnah structure (case, ruling, reason), "
                        "and analyzing moral and social dilemmas in rabbinic literature."
                    ),
                },
            },
        },
    },
    "tracks": {
        "mmd": {
            "id": "mmd",
            "title_he": 'ממלכתי-דתי (חמ"ד)',
            "title_en": "State-Religious (MMD / Hemed)",
        },
        "mamlachti": {
            "id": "mamlachti",
            "title_he": "ממלכתי (כללי)",
            "title_en": "General State (Mamlachti)",
        },
    },
    "units": {
        2: {"level": 2, "title_he": '2 יח"ל (חובה / בסיס)', "title_en": "2 Units (Core / Mandatory)"},
        3: {"level": 3, "title_he": '3 יח"ל (מורחב בסיסי)', "title_en": "3 Units (Intermediate Extended)"},
        5: {"level": 5, "title_he": '5 יח"ל (מוגבר / עיון)', "title_en": "5 Units (Advanced / Iyun)"},
    },
    "core_commentators": [
        "rashi",
        "ramban",
        "ibn_ezra",
        "rashbam",
        "sforno",
        "radak",
        "malbim",
        "metzudat_david",
        "metzudat_tzion",
        "metzudat_zion",
        "tosafot",
        "rambam",
        "shulchan_aruch",
        "bartenura",
        "mishnah_berurah",
    ],
    "aramaic_scaffold": [
        {
            "term": "מנא הני מילי (מנלן)",
            "role_he": "שאלת מקור",
            "meaning_he": "מניין לנו הדברים האלה? בקשת מקור מן התורה שבכתב לדין שנאמר במשנה או במימרא.",
            "meaning_en": "From where are these words derived? Seeking a biblical source for a Mishnaic or Amoraic ruling.",
        },
        {
            "term": "מאי שנא",
            "role_he": "שאלת הבחנה / קושיא",
            "meaning_he": "מה שונה? מדוע קיים הבדל בדין בין שני מקרים שנראים דומים (למשל בין הרישא לסיפא)?",
            "meaning_en": "What is the difference? Why does the ruling differ between two seemingly similar cases?",
        },
        {
            "term": "איבעיא להו",
            "role_he": "בעיה / ספק הלכתי",
            "meaning_he": "נשאלה להם (לבני הישיבה): הצגת שאלה או ספק הלכתי שטרם הוכרע.",
            "meaning_en": "It was asked by them: Introducing an unresolved legal inquiry or dilemma in the study hall.",
        },
        {
            "term": 'תא שמע (ת"ש)',
            "role_he": "הבאת ראיה / פשיטת ספק",
            "meaning_he": "בוא ושמע: הבאת מקור (משנה, ברייתא או מימרא) כדי להוכיח צד מסוים או לפשוט ספק.",
            "meaning_en": "Come and hear: Introducing a proof-text to resolve an inquiry or support a position.",
        },
        {
            "term": "מיתיבי",
            "role_he": "קושיא ממקור תנאי",
            "meaning_he": "משיבים (מקשים) על דברי אמורא ממקור בעל סמכות גבוהה יותר (משנה או ברייתא).",
            "meaning_en": "They objected: Challenging an Amoraic statement from a higher-authority Tannaitic source.",
        },
        {
            "term": "ורמינהו",
            "role_he": "סתירה בין שני מקורות שווי-מעמד",
            "meaning_he": "והשלך אותם זה בזה: הצגת סתירה בין שני מקורות תנאיים (משנה מול משנה, או ברייתא מול ברייתא).",
            "meaning_en": "Contrast them: Pointing out a contradiction between two sources of equal Tannaitic authority.",
        },
        {
            "term": "הכא במאי עסקינן (אוקימתא)",
            "role_he": "תירוץ על ידי העמדת המקרה",
            "meaning_he": "כאן במה אנו עוסקים? יישוב קושיא או סתירה על ידי צמצום המקור למקרה או לתנאים מסוימים.",
            "meaning_en": "With what case are we dealing here? (Okimta): Resolving a contradiction by limiting a source to specific circumstances.",
        },
        {
            "term": "תיובתא",
            "role_he": "דחייה מוחלטת",
            "meaning_he": "קושיא מכרעת שאין לה תירוץ, הדוחה את שיטת האמורא שלהלכה.",
            "meaning_en": "Definitive refutation: A decisive objection from an authoritative source that refutes an Amora's position.",
        },
        {
            "term": 'קא משמע לן (קמ"ל)',
            "role_he": "הצגת החידוש",
            "meaning_he": "משמיע לנו: הסבר מדוע המקור אינו מיותר — איזה חידוש הלכתי הוא בא ללמד.",
            "meaning_en": "It teaches us: Explaining the novel point of the source and what mistaken assumption it rules out.",
        },
        {
            "term": 'נפקא מינה (נפ"מ)',
            "role_he": "הבדל מעשי בין שיטות",
            "meaning_he": "יוצא מזה: מהו המקרה המעשי שבו יתבטא ההבדל בין שני פירושים או שתי שיטות?",
            "meaning_en": "Practical difference: What concrete case results in a different ruling depending on the two views?",
        },
        {
            "term": "הלכתא",
            "role_he": "הכרעת ההלכה בסוגיה",
            "meaning_he": "הלכה כדברי פלוני: הכרעת הגמרא בסוף הדיון.",
            "meaning_en": "The law is: The Talmud's final halachic conclusion on the dispute.",
        },
    ],
    "rubric_principles_he": {
        "core_formula": "טענה מפורשת + ביסוס/ציטוט מדויק מן המקור [S#] + הסבר במילים שלך המקשר בין הציטוט לטענה.",
        "principles": [
            {
                "id": "claim_cite_explain",
                "title": "מבנה תשובה מלאה (טענה – ביסוס – הסבר)",
                "rule": (
                    "תשובה מלאה בבחינת הבגרות חייבת לכלול שלושה רכיבים: (1) מענה ישיר לשאלה (הטענה/הדין/הקושי); "
                    "(2) ביסוס מן הכתוב או מן המפרש באמצעות ציטוט ממוקד או הפניה מפורשת [S#]; "
                    "(3) הסבר במילים של התלמיד המראה כיצד הציטוט מוכיח את הטענה."
                ),
            },
            {
                "id": "halachic_humility_principle_viii",
                "title": "ענווה הלכתית בלימוד אירועונים (Principle VIII)",
                "rule": (
                    "שאלות יישום ו\"אירועון הלכתי\" במצב בגרויות נועדו לבחון הבנה לימודית-עיונית של המקורות לקראת בחינת הבגרות בלבד. "
                    "המחוון והמשוב מציגים את השיטות והנימוקים מתוך המקורות שאוחזרו, ומציינים במפורש כי אין לראות בכך פסק הלכה למעשה."
                ),
            },
        ],
    },
    "rubric_principles_en": {
        "core_formula": "Explicit Claim + Accurate Textual Citation [S#] + Own-Words Explanation linking the citation to the claim.",
        "principles": [
            {
                "id": "claim_cite_explain",
                "title": "Complete Answer Structure (Claim – Citation – Explanation)",
                "rule": (
                    "A full-credit Bagrut response requires three components: (1) a direct answer to the prompt; "
                    "(2) textual grounding via a focused quote or explicit reference [S#]; and "
                    "(3) an explanation in the student's own words demonstrating how the quote proves the claim."
                ),
            },
            {
                "id": "halachic_humility_principle_viii",
                "title": "Halachic Humility in Case Studies (Principle VIII)",
                "rule": (
                    "Halachic case-study questions (Eru'on Halachti) in Bagrut Mode strictly assess academic comprehension of the retrieved sources "
                    "for exam preparation. Rubrics and feedback present the retrieved positions and rationales for study purposes only, never as a practical halachic ruling (psak)."
                ),
            },
        ],
    },
}

_curriculum_cache: dict[str, Any] | None = None


def load_bagrut_curriculum(path: str | Path | None = None) -> dict[str, Any]:
    """Load `data/bagrut_curriculum.yaml` with a safe fallback dictionary."""
    global _curriculum_cache
    if path is None and _curriculum_cache is not None:
        return _curriculum_cache
    target = Path(path) if path is not None else _CURRICULUM_PATH
    try:
        if target.is_file():
            loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and "subjects" in loaded:
                if path is None:
                    _curriculum_cache = loaded
                return loaded
    except Exception:
        pass
    return dict(_DEFAULT_CURRICULUM)


# ── Subject Detection ────────────────────────────────────────────────────────────────────────

_MACHSHAVA_KEYWORDS: tuple[str, ...] = (
    "מחשבת ישראל",
    "מחשבת",
    "הכוזרי",
    "כוזרי",
    "ריהל",
    'ריה"ל',
    "ריה״ל",
    "ספר הכוזרי",
    "שמונה פרקים",
    "מורה נבוכים",
    "אורות התשובה",
    "איש האמונה",
    "קול דודי דופק",
    "הרב קוק",
    'הראי"ה',
    "הראי״ה",
    "סולובייצ'יק",
    "סולוביצ'יק",
    "עיקרי האמונה",
    "שאלון 281",
    "שאלון 282",
    "שאלון 5281",
    "machshevet yisrael",
    "jewish thought",
)

_TOSHBA_KEYWORDS: tuple[str, ...] = (
    'תושב"ע',
    "תושב״ע",
    "תושבע",
    "תורה שבעל פה",
    "תורה שבעל-פה",
    "שולחן ערוך",
    'שו"ע',
    "שו״ע",
    "משנה ברורה",
    'מ"ב',
    "אירועון",
    "אירועונים",
    "אירועון הלכתי",
    "הלכות ",
    "בהלכות ",
    "הלכה לבגרות",
    "בגרות בהלכה",
    "בגרות במשנה",
    "ברטנורא",
    'ר"ע מברטנורא',
    'רע"ב',
    "תפארת ישראל",
    "יכין ובועז",
    "אישות ומשפחה",
    "מצוות התלויות בארץ",
    "כשרות",
    "5381",
    "toshba",
    "oral law",
    "shulchan aruch",
    "shulchan arukh",
    "mishnah berurah",
    "mishna berura",
    "bartenura",
    "case study",
    "halachic case",
)

_GEMARA_STRONG_KEYWORDS: tuple[str, ...] = (
    "גמרא",
    "בגמרא",
    "לגמרא",
    "תלמוד",
    "בתלמוד",
    "בבלי",
    "סוגיה",
    "סוגיא",
    "סוגיית",
    "סוגיות",
    "שקלא וטריא",
    'שקו"ט',
    "אביי",
    "אביי ורבא",
    "אמר רבא",
    "לרבא",
    "דרבא",
    "רב אשי",
    "רבינא",
    "אמורא",
    "אמוראים",
    "תוספות",
    'רש"י ותוספות',
    "תיובתא",
    "אוקימתא",
    "איבעיא להו",
    "מיתיבי",
    "ורמינהו",
    "מנא הני מילי",
    "מנלן",
    "מאי שנא",
    "תא שמע",
    "קא משמע לן",
    'קמ"ל',
    "נפקא מינה",
    'נפ"מ',
    "מאי בינייהו",
    "עמוד א",
    "עמוד ב",
    'ע"א',
    "ע״א",
    'ע"ב',
    "ע״ב",
    "6281",
    "gemara",
    "talmud",
    "sugya",
    "sugyot",
    "shakla",
    "tosafot",
    "amora",
    "amoraim",
    "abaye",
    "rava",
)

_TANAKH_KEYWORDS: tuple[str, ...] = (
    'תנ"ך',
    "תנ״ך",
    "תנך",
    "מקרא",
    "מקראי",
    "מקראית",
    "פסוק",
    "פסוקים",
    "בפסוק",
    "פרק ",
    "פרקים",
    "נביא",
    "נביאים",
    "כתובים",
    "חומש",
    "פרשת ",
    'רמב"ן',
    "רמב״ן",
    "אבן עזרא",
    'ראב"ע',
    'רד"ק',
    "רד״ק",
    'רשב"ם',
    "רשב״ם",
    "ספורנו",
    'מלבי"ם',
    "מלבי״ם",
    "מצודת דוד",
    "מצודת ציון",
    "מצודות",
    "אברבנאל",
    "בעל הטורים",
    "הקבלה פנים-מקראית",
    "פנים מקראית",
    "אמצעים אומנותיים",
    "אמצעים ספרותיים",
    "מילה מנחה",
    "תקבולת",
    "כיאזם",
    "כיאסטי",
    "1281",
    "0581",
    "2575",
    "2585",
    "2551",
    "tanakh",
    "tanach",
    "bible",
    "biblical",
    "verse",
    "verses",
    "pshat",
    "peshat",
    "ramban",
    "ibn ezra",
    "radak",
    "rashbam",
    "sforno",
    "malbim",
)

_MISHNAH_WORD_RE = re.compile(
    r"(?:^|[\s,.:;()\[\]\"'״׳\-])(?:ב?משנה|משניות|mishnah|mishna)(?=$|[\s,.:;()\[\]\"'״׳\-])",
    re.IGNORECASE,
)
_DAF_REF_RE = re.compile(
    r"(?:\bדף\s+[א-ת\d]{1,4}\b|\bdaf\s+\d+[ab]?\b)",
    re.IGNORECASE,
)


def _detect_bagrut_subject_raw(text: str) -> str:
    """Return 'tanakh', 'gemara', 'toshba', or 'machshava' if explicitly signaled in `text`, else ''."""
    clean = " ".join((text or "").split())
    if not clean:
        return ""
    low = clean.lower()

    if any(kw in low for kw in _MACHSHAVA_KEYWORDS):
        return "machshava"

    has_toshba_kw = any(kw in low for kw in _TOSHBA_KEYWORDS)
    has_mishnah_word = bool(_MISHNAH_WORD_RE.search(clean))
    has_rava_word = bool(re.search(r"(?:^|[\s,.:;()\[\]\"'״׳\-])רבא(?=$|[\s,.:;()\[\]\"'״׳\-])", clean))
    has_gemara_strong = (
        any(kw in low for kw in _GEMARA_STRONG_KEYWORDS)
        or has_rava_word
        or bool(_DAF_REF_RE.search(clean))
    )

    # Check explicit Toshba signals first (when not overridden by strong Gemara sugya terms)
    if has_toshba_kw and not has_gemara_strong:
        return "toshba"
    if has_mishnah_word and not has_gemara_strong:
        return "toshba"
    if has_toshba_kw and any(
        kw in low for kw in ('תושב"ע', "תושב״ע", "תושבע", "תורה שבעל פה", "אירועון", "שולחן ערוך", 'שו"ע', "משנה ברורה", "toshba", "case study")
    ):
        return "toshba"

    if has_gemara_strong:
        return "gemara"

    # Check Tanakh book names BEFORE tractates for shared/distinct names, or check tractates
    for he_tr, en_tr in HE_TRACTATES.items():
        # Note: "שבת" can be either Tractate Shabbat or Laws of Shabbat / Tanakh Shabbat context
        if he_tr == "שבת":
            if re.search(r"(?:מסכת\s+שבת|שבת\s+דף|\bshabbat\s+\d+[ab]\b)", low):
                return "gemara"
            continue
        if re.search(rf"(?:^|[\s,.:;()\[\]\"'״׳\-])(?:ב?מסכת\s+)?{re.escape(he_tr)}(?=$|[\s,.:;()\[\]\"'״׳\-])", clean):
            return "gemara"
        if re.search(rf"\b{re.escape(en_tr.lower())}\b", low):
            return "gemara"

    if any(kw in low for kw in _TANAKH_KEYWORDS):
        return "tanakh"

    for he_bk, en_bk in HE_BOOKS.items():
        if re.search(rf"(?:^|[\s,.:;()\[\]\"'״׳\-])(?:ב?ספר\s+)?{re.escape(he_bk)}(?=$|[\s,.:;()\[\]\"'״׳\-])", clean):
            return "tanakh"
        if re.search(rf"\b{re.escape(en_bk.lower())}\b", low):
            return "tanakh"

    # Common abbreviated/base biblical book names ("מלכים", "שמואל", "דברי הימים")
    if re.search(r"(?:^|[\s,.:;()\[\]\"'״׳\-])(?:מלכים|שמואל|דברי\s+הימים)(?=$|[\s,.:;()\[\]\"'״׳\-])", clean):
        return "tanakh"
    if re.search(r"\b(?:kings|samuel|chronicles)\b", low):
        return "tanakh"

    # Questionnaire code 5391 defaults to gemara/toshba -> gemara if unspecified
    if "5391" in low or "5291" in low:
        return "gemara"

    # "הלכות שבת" / "דיני שבת" -> toshba
    if re.search(r"(?:הלכות|דיני|הלכה)\b", clean):
        return "toshba"

    return ""


def detect_bagrut_subject(text: str) -> str:
    """Detect 'tanakh', 'gemara', or 'toshba' from Hebrew/English text (defaults to 'tanakh')."""
    return _detect_bagrut_subject_raw(text) or "tanakh"


# ── Track Detection ──────────────────────────────────────────────────────────────────────────

_MMD_EXPLICIT_RE = re.compile(
    r"(?:"
    r"חמ[\"״']?ד"
    r"|ממלכתי[\s\-־]*דתי"
    r"|חינוך\s+ממלכתי\s+דתי"
    r"|(?:מסלול|תיכון|בגרות|בית\s+ספר)\s+דתי(?:ת)?"
    r"|ישיבה\s+תיכונית"
    r"|אולפנ[הת]"
    r"|\b(?:2575|2585|2551|5391|5381|6281)\b"
    r"|\b(?:mmd|hemed|state[\s\-]*religious|religious\s+track)\b"
    r"|(?:^|[\s,.:;()\[\]])דתי(?=$|[\s,.:;()\[\]])"
    r")",
    re.IGNORECASE,
)

_MAMLACHTI_EXPLICIT_RE = re.compile(
    r"(?:"
    r"ממלכתי[\s\-־]*כללי"
    r"|תנ[\"״']?ך\s+(?:כללי|ממלכתי)(?!\s*[-\u05be]?\s*דתי)"
    r"|(?:מסלול|תיכון|בגרות|בית\s+ספר)\s+כללי(?:ת)?"
    r"|ממלכתי(?!\s*[-\u05be]?\s*דתי)"
    r"|\b(?:1281|0581|581)\b"
    r"|\b(?:mamlachti|general\s+state|general\s+track|secular\s+track)\b"
    r")",
    re.IGNORECASE,
)

_RELIGIOUS_COMMENTATORS_RE = re.compile(
    r"(?:רש[\"״']?י|רמב[\"״']?ן|אבן\s+עזרא|ראב[\"״']?ע|רשב[\"״']?ם|ספורנו|רד[\"״']?ק|מלבי[\"״']?ם|מצודת\s+דוד|מצודת\s+ציון|מצודות"
    r"|\brashi\b|\bramban\b|\bibn\s+ezra\b|\brashbam\b|\bsforno\b|\bradak\b|\bmalbim\b)",
    re.IGNORECASE,
)


def _detect_bagrut_track_raw(text: str, subject: str = "") -> str:
    """Return 'mmd' or 'mamlachti' if explicitly signaled in `text`, else ''."""
    clean = " ".join((text or "").split())
    if not clean:
        return ""
    if _MMD_EXPLICIT_RE.search(clean):
        return "mmd"
    if _MAMLACHTI_EXPLICIT_RE.search(clean):
        return "mamlachti"
    if _RELIGIOUS_COMMENTATORS_RE.search(clean):
        return "mmd"
    return ""


def detect_bagrut_track(text: str, subject: str = "") -> str:
    """Detect 'mamlachti' vs 'mmd' from text and subject.

    For `gemara` and `toshba`, default track is `'mmd'`; for `tanakh`, defaults to `'mmd'`
    if religious commentators are named or if unspecified, unless `'mamlachti'` is indicated.
    """
    raw = _detect_bagrut_track_raw(text, subject)
    if raw:
        return raw
    return "mmd"


# ── Units Detection ──────────────────────────────────────────────────────────────────────────

_UNITS_DIGIT_RE = re.compile(
    r"(?:^|[^\d])([235])\s*(?:יח[\"״']?ל|יחידות(?:\s*לימוד)?|יח['׳״]?|units?\b)",
    re.IGNORECASE,
)

_UNITS_WORD_2_RE = re.compile(
    r"(?:שתי\s+(?:יחידות|יח[\"״']?ל)|two\s+units)",
    re.IGNORECASE,
)
_UNITS_WORD_3_RE = re.compile(
    r"(?:שלוש\s+(?:יחידות|יח[\"״']?ל)|three\s+units)",
    re.IGNORECASE,
)
_UNITS_WORD_5_RE = re.compile(
    r"(?:חמש\s+(?:יחידות|יח[\"״']?ל)|five\s+units)",
    re.IGNORECASE,
)

_CODE_TO_UNITS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:1281|0581|581|5291)\b"), "2"),
    (re.compile(r"\b(?:5391|5381|2551)\b"), "3"),
    (re.compile(r"\b(?:6281|2575|2585)\b"), "5"),
)


def _detect_bagrut_units_raw(text: str) -> str:
    """Return '2', '3', or '5' if explicitly signaled in `text`, else ''."""
    clean = " ".join((text or "").split())
    if not clean:
        return ""
    m = _UNITS_DIGIT_RE.search(clean)
    if m:
        return m.group(1)
    if _UNITS_WORD_2_RE.search(clean):
        return "2"
    if _UNITS_WORD_3_RE.search(clean):
        return "3"
    if _UNITS_WORD_5_RE.search(clean):
        return "5"
    for pat, u in _CODE_TO_UNITS:
        if pat.search(clean):
            return u
    return ""


def detect_bagrut_units(text: str) -> str:
    """Detect '2', '3', or '5' units from text or questionnaire code, defaulting to '5'."""
    return _detect_bagrut_units_raw(text) or "5"


# ── Action Detection ─────────────────────────────────────────────────────────────────────────

_ACTION_CHECK_RE = re.compile(
    r"(?:"
    r"(?:תבדוק|בדוק|תבדקי|בדקי|לבדוק)\s+(?:לי\s+)?(?:את\s+)?(?:התשובה|תשובתי)"
    r"|(?:תבדוק|בדוק|תבדקי|בדקי)\s+לי\b"
    r"|התשובה\s+שלי\s*[:\-–—]?"
    r"|תשובתי\s*[:\-–—]"
    r"|עניתי\s+(?:כך|ככה)\b"
    r"|כמה\s+נקודות\s+(?:הייתי\s+מקבל|מגיע\s+לי|אקבל)"
    r"|איך\s+התשובה\s+שלי"
    r"|האם\s+התשובה\s+שלי\s+נכונה"
    r"|תן\s+ציון\s+לתשובה"
    r"|\b(?:check|grade|score|evaluate)\s+my\s+(?:answer|response)\b"
    r"|\bmy\s+answer\s*:"
    r"|\bhow\s+many\s+points\s+would\s+i\s+get\b"
    r")",
    re.IGNORECASE,
)

_ACTION_SUMMARY_RE = re.compile(
    r"(?:"
    r"סיכום(?:\s+לבגרות|\s+מלא|\s+על|\s+לפרק|\s+לסוגיה|\s+חדש)?"
    r"|תסכם|לסכם|סכם\s+לי"
    r"|דף\s+חזרה"
    r"|מיקודית"
    r"|חוברת(?:\s+סיכום|\s+הכנה|\s+לימוד|\s+לבגרות)?"
    r"|\b(?:study\s+guide|summary\s+sheet|review\s+sheet|bagrut\s+summary|summarize\s+for\s+bagrut)\b"
    r"|\b(?:build|create|write|make|prepare)\s+(?:a\s+)?summary\b"
    r")",
    re.IGNORECASE,
)

_ACTION_EXAM_RE = re.compile(
    r"(?:"
    r"מתכונת"
    r"|מבחן(?:\s+בגרות|\s+מתכונת|\s+מלא|\s+חדש|\s+על|\s+ב)?"
    r"|בחינת\s+(?:מתכונת|בגרות)"
    r"|שאלון\s+בגרות"
    r"|שאלון\s*\+\s*מחוון"
    r"|(?:תבנה|בנה|תכין|הכן|צור|תיצור|חולל)\s+(?:לי\s+)?(?:מתכונת|מבחן|בחינה|שאלון)"
    r"|\b(?:mock\s+exam|practice\s+exam|bagrut\s+exam)\b"
    r"|\b(?:build|create|generate|make|prepare)\s+(?:an?\s+|a\s+full\s+)?(?:mock\s+)?exam\b"
    r")",
    re.IGNORECASE,
)

_ACTION_SOLUTION_RE = re.compile(
    r"(?:"
    r"(?:תפתור|פתור|תפתרי|פתרי|לפתור)\s+(?:לי\s+)?(?:את\s+)?(?:כל\s+)?(?:הבגרות|שאלון|המבחן|הבחינה)"
    r"|(?:תפתור|פתור|תפתרי|פתרי|לפתור|תשובות|פתרון|מענה)(?:.*?)כקובץ"
    r"|(?:קובץ\s+פתרון|קובץ\s+תשובות)"
    r"|פתרון\s+(?:מלא\s+)?(?:לבגרות|לשאלון|למבחן|של\s+הבגרות|לבחינה)"
    r"|תשובות\s+(?:מלאות\s+)?(?:לבגרות|לשאלון|למבחן)"
    r"|מענה\s+מלא\s+(?:לבגרות|לשאלון)"
    r"|\b(?:solve|solution\s+to|complete\s+solution)\s+(?:the\s+)?(?:bagrut|exam)\b"
    r"|\b(?:solve|solution)\s+(?:.*?\s+)?as\s+(?:a\s+)?file\b"
    r")",
    re.IGNORECASE,
)


def _detect_bagrut_action_raw(text: str) -> str:
    """Return 'check', 'summary', 'exam', or 'solution' if explicitly signaled in `text`, else ''."""
    clean = " ".join((text or "").split())
    if not clean:
        return ""
    # Check grading/answer-verification first so "תבדוק את התשובה שלי במבחן" routes to 'check'
    if _ACTION_CHECK_RE.search(clean):
        return "check"
    # Check solving a full exam/questionnaire into a solution file
    if _ACTION_SOLUTION_RE.search(clean):
        return "solution"
    # If the user asks to solve a single question from a past exam ("פתור לי את שאלה 3 ממבחן בגרות"),
    # that is interactive practice/solving, not generating a full mock exam file.
    if re.search(r"(?:פתור|תפתור|נסה\s+לפתור|תרגל\s+איתי)\s+(?:לי\s+)?(?:את\s+)?שאלה\b", clean):
        return "practice"
    if _ACTION_EXAM_RE.search(clean):
        return "exam"
    if _ACTION_SUMMARY_RE.search(clean):
        return "summary"
    return ""


def detect_bagrut_action(text: str) -> str:
    """Detect 'exam', 'summary', 'solution', 'check', or 'practice' (default) from user text."""
    return _detect_bagrut_action_raw(text) or "practice"


# ── Follow-up Rebuild Detection & Parameter Resolution ───────────────────────────────────────

_BAGRUT_REBUILD_VERB = (
    r"(?:בנה|תבנה|לבנות|צור|תיצור|ליצור|ערוך|תערוך|לערוך|הפק|תפיק|להפיק|"
    r"הכן|תכין|להכין|כתוב|תכתוב|לכתוב|חולל|תחולל|לחולל|סכם|תסכם|לסכם|חדש|תחדש|לחדש)"
)
_BAGRUT_NOUN = r"(?:מתכונת|מבחן|בחינה|בחינת\s*מתכונת|שאלון|סיכום|דף\s*חזרה|מיקודית|חוברת|מחוון)"
_BAGRUT_REBUILD_HE_RE = re.compile(
    rf"(?:{_BAGRUT_REBUILD_VERB}\s+(?:[^\n.?!]{{0,30}}?){_BAGRUT_NOUN}"
    rf"|{_BAGRUT_NOUN}\s+(?:חדש|חדשה|נוסף|נוספת|אחר|אחרת|מעודכן|מעודכנת))",
    re.IGNORECASE,
)
_BAGRUT_REBUILD_EN_RE = re.compile(
    r"(?:"
    r"\b(?:build|create|generate|make|prepare|write|regenerate)\s+(?:[^\n.?!]{0,25}?)"
    r"\b(?:exam|mock\s+exam|test|summary|study\s+guide|review\s+sheet|rubric)\b"
    r"|\b(?:new|another|updated|fresh)\s+(?:mock\s+)?(?:exam|summary|study\s+guide|review\s+sheet|rubric)\b"
    r")",
    re.IGNORECASE,
)


def is_bagrut_file_rebuild_request(text: str) -> bool:
    """Return True only when `text` explicitly asks to build/regenerate a Bagrut summary or exam file.

    Used on follow-up turns in a session that already produced Bagrut files (`Turn.bagrut=True`) so
    ordinary follow-up questions ('תסביר את שאלה 2', 'למה רש\"י אומר ככה') route to interactive chat
    instead of regenerating downloadable files.
    """
    clean = " ".join((text or "").split())
    if not clean:
        return False
    return bool(_BAGRUT_REBUILD_HE_RE.search(clean) or _BAGRUT_REBUILD_EN_RE.search(clean))


# Alias for callers referencing the double-prefixed name in task specs
is_is_bagrut_file_rebuild_request = is_bagrut_file_rebuild_request


_NARROW_TOPIC_RE = re.compile(
    r"(?:"
    r"רק\s+(?:על|ב|בנושא|בפרק|במסכת|בהלכות|בספר)"
    r"|בלבד(?=$|[\s,.:;()\[\]])"
    r"|ממוקד(?:ת)?(?:\s+ב|\s+על)"
    r"|ספציפי(?:ת)?(?:\s+ל|\s+על)"
    r"|\b(?:only\s+on|focus(?:ed)?\s+on\s+only|narrowly\s+on)\b"
    r")",
    re.IGNORECASE,
)


def is_bagrut_narrow_topic_request(text: str) -> bool:
    """Return True if the user explicitly asks for an exam/summary on a single narrow topic only."""
    clean = " ".join((text or "").split())
    if not clean:
        return False
    return bool(_NARROW_TOPIC_RE.search(clean))


def _turn_role(turn: Any) -> str:
    if isinstance(turn, dict):
        return str(turn.get("role") or "user")
    return str(getattr(turn, "role", "user") or "user")


def _turn_text(turn: Any) -> str:
    if isinstance(turn, dict):
        return str(turn.get("text") or "")
    return str(getattr(turn, "text", "") or "")


def _turn_is_bagrut_files(turn: Any) -> bool:
    if isinstance(turn, dict):
        return bool(turn.get("bagrut"))
    return bool(getattr(turn, "bagrut", False))


def resolve_bagrut_params(
    question: str,
    history: list | None = None,
    subject: str = "",
    track: str = "",
    units: str = "",
    action: str = "",
) -> dict[str, str]:
    """Combine explicit UI parameters with auto-detection across the current question and user history."""
    subj = subject.strip().lower() if subject and subject.strip().lower() in BAGRUT_SUBJECTS else ""
    trk = track.strip().lower() if track and track.strip().lower() in BAGRUT_TRACKS else ""
    unt = str(units).strip() if units and str(units).strip() in BAGRUT_UNITS else ""
    act = action.strip().lower() if action and action.strip().lower() in BAGRUT_ACTIONS else ""

    user_turns = [
        _turn_text(h).strip()
        for h in (history or [])
        if _turn_role(h) == "user" and _turn_text(h).strip()
    ]
    has_prior_bagrut_files = any(_turn_is_bagrut_files(h) for h in (history or []))

    # 1. Subject: explicit -> current question -> reverse history -> default 'tanakh'
    if not subj:
        subj = _detect_bagrut_subject_raw(question)
    if not subj:
        for ut in reversed(user_turns):
            subj = _detect_bagrut_subject_raw(ut)
            if subj:
                break
    if not subj:
        subj = "tanakh"

    # 2. Track: explicit -> current question -> reverse history -> default 'mmd'
    if not trk:
        trk = _detect_bagrut_track_raw(question, subj)
    if not trk:
        for ut in reversed(user_turns):
            trk = _detect_bagrut_track_raw(ut, subj)
            if trk:
                break
    if not trk:
        trk = detect_bagrut_track(question, subj)

    # 3. Units: explicit -> current question -> reverse history -> default '5'
    if not unt:
        unt = _detect_bagrut_units_raw(question)
    if not unt:
        for ut in reversed(user_turns):
            unt = _detect_bagrut_units_raw(ut)
            if unt:
                break
    if not unt:
        unt = "5"

    # 4. Action:
    # If the session ALREADY generated Bagrut files (`Turn.bagrut=True`) and this turn is a follow-up
    # question that does NOT ask to rebuild files, route to 'check' (if checking answer) or 'practice'
    # even if the UI's sticky dropdown still sent 'summary' or 'exam'.
    q_act = _detect_bagrut_action_raw(question)
    if has_prior_bagrut_files and not is_bagrut_file_rebuild_request(question):
        if q_act == "check" or act == "check":
            act = "check"
        elif q_act in ("solution", "exam", "summary"):
            act = q_act
        else:
            act = "practice"
    elif q_act in ("exam", "summary", "check", "solution"):
        # Explicit intent in the user prompt (e.g. asking for a solution or exam file)
        # overrides any sticky default ("practice") from the UI dropdown.
        act = q_act
    elif not act:
        # If no completed bagrut files yet, check if an earlier user turn requested exam/summary/solution
        for ut in reversed(user_turns):
            prev_act = _detect_bagrut_action_raw(ut)
            if prev_act:
                act = prev_act
                break
        if not act:
            act = "practice"

    return {
        "subject": subj,
        "track": trk,
        "units": unt,
        "action": act,
    }


# ── Principle I Guard: Unattached Past Exam Query Detection ──────────────────────────────────

_INTRA_WORD_GERSHAYIM_RE = re.compile(r"(?<=[\u0590-\u05ff\w])[\"״׳'](?=[\u0590-\u05ff\w])")
_QUOTED_SPAN_RE = re.compile(r"(?:\"[^\"]{20,}\"|“[^”]{20,}”|«[^»]{20,}»|'[^']{25,}')")

_PAST_EXAM_REF_RE = re.compile(
    r"(?:"
    r"בגרות"
    r"|שאלון\s*\d{3,4}"
    r"|\bbagrut\b"
    r"|\bquestionnaire\s*\d{3,4}\b"
    r")",
    re.IGNORECASE,
)

_PAST_EXAM_TIME_OR_Q_RE = re.compile(
    r"(?:"
    # Hebrew year like תשפ"ג, תשפ״ד, תש"פ, תשע"ח, תשפג
    r"\bתש(?:[א-ת][\"״׳']?[א-ת]|[\"״׳'][א-ת])\b"
    # Gregorian year 1990-2029
    r"|\b(?:199\d|20[0-2]\d)\b"
    # Season / Moed
    r"|(?:קיץ|חורף|אביב|מועד\s*[אב])\b"
    r"|\b(?:summer|winter|spring|moed\s*[ab12])\b"
    # Asking "what was question N in questionnaire XXXX"
    r"|(?:מה\s+הייתה\s+שאלה\s+\d+)"
    r"|(?:what\s+was\s+question\s+\d+)"
    r")",
    re.IGNORECASE,
)

_SPECIFIC_QUESTION_NUM_RE = re.compile(
    r"(?:שאלה\s*(?:\d+|[א-ת](?=$|[\s,.:;]))|\bquestion\s*\d+\b)",
    re.IGNORECASE,
)

_BUILD_NEW_EXAM_RE = re.compile(
    r"(?:תבנה|בנה|תכין|הכן|צור|תיצור|חולל|מתכונת\s+חדשה|\b(?:build|create|generate|make)\b)",
    re.IGNORECASE,
)


def is_unattached_past_exam_query(question: str, has_attachments: bool = False) -> bool:
    """Detect when a user asks for a specific past Ministry of Education Bagrut exam question
    by year/season/questionnaire/number WITHOUT providing the question text or an attachment.

    Prevents hallucinating copyrighted past exams from parametric memory (Constitution Principle I).
    """
    if has_attachments:
        return False
    clean = " ".join((question or "").split()).strip()
    if not clean or len(clean) >= 140:
        return False
    # Strip intra-word Hebrew gershayim (e.g. תנ"ך, תשפ"ג) before checking for actual quoted passages
    de_gershayim = _INTRA_WORD_GERSHAYIM_RE.sub("", clean)
    if _QUOTED_SPAN_RE.search(de_gershayim):
        return False
    # If the user is asking us to BUILD a new mock exam on a topic, do not block
    if _BUILD_NEW_EXAM_RE.search(clean) and not _SPECIFIC_QUESTION_NUM_RE.search(clean):
        return False

    has_exam_ref = bool(_PAST_EXAM_REF_RE.search(clean))
    has_time_or_past = bool(_PAST_EXAM_TIME_OR_Q_RE.search(clean))
    has_q_num = bool(_SPECIFIC_QUESTION_NUM_RE.search(clean))

    if has_exam_ref and has_time_or_past:
        return True
    if has_q_num and has_time_or_past:
        return True
    return False


# ── Core Commentator Retrieval Boosting ──────────────────────────────────────────────────────

_COMMENTATOR_ALIASES_MAP: dict[str, str] = {
    "metzudat_zion": "metzudat_tzion",
    "metzudat_tzion": "metzudat_tzion",
    "shulchan_arukh": "shulchan_aruch",
    "shulchan_aruch": "shulchan_aruch",
    "mishna_berura": "mishnah_berurah",
    "mishnah_berurah": "mishnah_berurah",
    'רש"י': "rashi",
    'רמב"ן': "ramban",
    "אבן עזרא": "ibn_ezra",
    'רשב"ם': "rashbam",
    "ספורנו": "sforno",
    'רד"ק': "radak",
    'מלבי"ם': "malbim",
    "מצודת דוד": "metzudat_david",
    "מצודת ציון": "metzudat_tzion",
    "תוספות": "tosafot",
    'רמב"ם': "rambam",
    "שולחן ערוך": "shulchan_aruch",
    "ברטנורא": "bartenura",
    "משנה ברורה": "mishnah_berurah",
}


def _norm_commentator_id(cid: str | None) -> str:
    if not cid:
        return ""
    raw = cid.strip().lower().replace(" ", "_")
    return _COMMENTATOR_ALIASES_MAP.get(raw, _COMMENTATOR_ALIASES_MAP.get(cid.strip(), raw))


def boost_bagrut_hits(hits: list, subject: str, track: str = "mmd") -> list:
    """Reorder commentary hits so core Bagrut commentators for `(subject, track)` appear before
    esoteric/unrelated commentators, while keeping base sources (`commentator_id is None`) at the very front.
    """
    if not hits:
        return []
    curriculum = load_bagrut_curriculum()
    subj_key = (subject or "tanakh").strip().lower()
    subj_cfg = (curriculum.get("subjects") or {}).get(subj_key) or {}
    subj_core_raw = subj_cfg.get("core_commentators") or []
    global_core_raw = curriculum.get("core_commentators") or []

    subj_core = {_norm_commentator_id(c): idx for idx, c in enumerate(subj_core_raw)}
    global_core = {_norm_commentator_id(c): idx for idx, c in enumerate(global_core_raw)}

    base_hits: list = []
    subj_core_hits: list[tuple[int, int, Any]] = []
    global_core_hits: list[tuple[int, int, Any]] = []
    other_commentary_hits: list = []

    for orig_idx, h in enumerate(hits):
        cid = h.get("commentator_id") if isinstance(h, dict) else getattr(h, "commentator_id", None)
        if not cid:
            base_hits.append(h)
            continue
        norm_cid = _norm_commentator_id(str(cid))
        if norm_cid in subj_core:
            subj_core_hits.append((subj_core[norm_cid], orig_idx, h))
        elif norm_cid in global_core:
            global_core_hits.append((global_core[norm_cid], orig_idx, h))
        else:
            other_commentary_hits.append(h)

    subj_core_hits.sort(key=lambda item: (item[0], item[1]))
    global_core_hits.sort(key=lambda item: (item[0], item[1]))

    return (
        base_hits
        + [item[2] for item in subj_core_hits]
        + [item[2] for item in global_core_hits]
        + other_commentary_hits
    )


# ── Output Splitting ─────────────────────────────────────────────────────────────────────────

BAGRUT_SPLIT_RE = re.compile(
    r"^[ \t>*‏‎]*===\s*(BAGRUT_SUMMARY|BAGRUT_EXAM|BAGRUT_RUBRIC|BAGRUT_SOLUTION|ORDER)\s*===[ \t*]*$",
    re.MULTILINE,
)

_SPLIT_KEY_ALIASES: dict[str, str] = {
    "summary": "BAGRUT_SUMMARY",
    "bagrut_summary": "BAGRUT_SUMMARY",
    "exam": "BAGRUT_EXAM",
    "bagrut_exam": "BAGRUT_EXAM",
    "rubric": "BAGRUT_RUBRIC",
    "bagrut_rubric": "BAGRUT_RUBRIC",
    "solution": "BAGRUT_SOLUTION",
    "bagrut_solution": "BAGRUT_SOLUTION",
    "order": "ORDER",
}


class _BagrutSplitDict(dict):
    """Dict with canonical keys (`BAGRUT_SUMMARY`, `BAGRUT_EXAM`, `BAGRUT_RUBRIC`, `BAGRUT_SOLUTION`, `ORDER`)
    that also resolves shorthand aliases (`summary`, `exam`, `rubric`, `solution`, `order`).
    """

    def __getitem__(self, key: str) -> str:
        canon = _SPLIT_KEY_ALIASES.get(key, key)
        return super().__getitem__(canon)

    def get(self, key: str, default: Any = "") -> Any:
        canon = _SPLIT_KEY_ALIASES.get(key, key)
        return super().get(canon, default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            canon = _SPLIT_KEY_ALIASES.get(key, key)
            return super().__contains__(canon)
        return super().__contains__(key)


def split_bagrut_files(text: str) -> dict[str, str]:
    """Split a Bagrut file generation response into its constituent sections."""
    parts = _BagrutSplitDict(
        {
            "BAGRUT_SUMMARY": "",
            "BAGRUT_EXAM": "",
            "BAGRUT_RUBRIC": "",
            "BAGRUT_SOLUTION": "",
            "ORDER": "",
        }
    )
    if not text:
        return parts
    matches = list(BAGRUT_SPLIT_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts[m.group(1)] = text[m.end() : end].strip()
    return parts


# ── Helper Formatting for Sources, Templates & Scaffolds ─────────────────────────────────────

def _format_sources_for_prompt(hits: list, lang: str) -> list[str]:
    lines: list[str] = []
    he = (lang or "he") != "en"
    for i, h in enumerate(hits, 1):
        cid = h.get("commentator_id") if isinstance(h, dict) else getattr(h, "commentator_id", None)
        ref_str = (h.get("ref") if isinstance(h, dict) else getattr(h, "ref", "")) or ""
        raw_text = (h.get("text") if isinstance(h, dict) else getattr(h, "text", "")) or ""
        who = f" ({cid})" if cid else ""
        if he:
            try:
                title = talmud_hebrew_display_ref(ref_str) or hebrew_display_ref(ref_str) or ref_str
            except Exception:
                title = ref_str
            header = f"### [S{i}] {title} (מזהה מקור: {ref_str}){who}"
        else:
            try:
                title = talmud_english_display_ref(ref_str) or ref_str
            except Exception:
                title = ref_str
            header = f"### [S{i}] {title} (source ID: {ref_str}){who}"
        clean_text = source_body(raw_text).strip()
        lines += [header, clean_text, ""]
    return lines


def _load_tpl_skeleton(tpl: dict | None, role: str, lang: str) -> str:
    """Return the markdown body for `role` ('summary', 'exam', 'rubric') from `tpl`."""
    if not tpl:
        return ""
    he = (lang or "he") != "en"
    if not he and tpl.get(f"_{role}_en"):
        return str(tpl[f"_{role}_en"])
    if tpl.get(f"_{role}"):
        return str(tpl[f"_{role}"])
    # Fallback: load from disk if `dir` or `id` is in `tpl`
    dir_str = tpl.get("dir") or (f"lessons/templates/{tpl.get('id')}" if tpl.get("id") else "")
    if not dir_str:
        return ""
    d = _REPO_ROOT / dir_str
    files_map = (tpl.get("files_en") if not he else None) or tpl.get("files") or {}
    fn = files_map.get(role)
    if not fn:
        cand = f"TEMPLATE_{role}_en.md" if not he else f"TEMPLATE_{role}.md"
        if (d / cand).is_file():
            fn = cand
        elif (d / f"TEMPLATE_{role}.md").is_file():
            fn = f"TEMPLATE_{role}.md"
    if fn:
        try:
            p = (d / fn).resolve()
            p.relative_to(_REPO_ROOT)
            if p.is_file():
                return p.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def _build_aramaic_scaffold_lines(curriculum: dict[str, Any], lang: str) -> list[str]:
    scaffold = curriculum.get("aramaic_scaffold") or []
    if not scaffold:
        return []
    he = (lang or "he") != "en"
    lines = [
        "## פיגומי שפה ארמית ומבנה הסוגיה (Aramaic & Sugya Structure Scaffold)"
        if he
        else "## ARAMAIC & SUGYA STRUCTURE SCAFFOLD"
    ]
    if he:
        lines.append(
            "חובה לבאר מונחים ארמיים המופיעים במקורות ולהדגיש את תפקידו המבני של כל שלב בשקלא וטריא "
            "(משנה, גמרא, קושיא, תירוץ, אוקימתא, תיובתא, איבעיא להו, תא שמע, מיתיבי, ורמינהו, נפקא מינה):"
        )
        for item in scaffold[:12]:
            lines.append(f"- **{item.get('term', '')}** ({item.get('role_he', '')}): {item.get('meaning_he', '')}")
    else:
        lines.append(
            "You MUST translate and explain Aramaic terms appearing in the sources and highlight the logical role "
            "of each step in the shakla vetarya (Mishnah, Gemara, kushya, terutz, okimta, tyuvta, ibaya lehu, ta shma, nafka mina):"
        )
        for item in scaffold[:12]:
            lines.append(f"- **{item.get('term', '')}** ({item.get('role_he', '')}): {item.get('meaning_en', '')}")
    lines.append("")
    return lines


def _build_halachic_humility_lines(lang: str) -> list[str]:
    he = (lang or "he") != "en"
    if he:
        return [
            "## עקרון VIII — ענווה הלכתית בלימוד תושב\"ע ואירועונים (Principle VIII: Halachic Humility)",
            "חשוב מאוד: כל ניתוח הלכתי או פתרון שניתן לשאלת 'אירועון הלכתי' במצב בגרויות נועד אך ורק לצורך "
            "**לימוד עיוני והכנה לבחינת הבגרות**, ולעולם אינו מהווה פסק הלכה למעשה! "
            "הצג את המקורות, השיטות והנימוקים (מקרה, דין וטעם) כפי שהם עולים מן המקורות [S#], וציין במפורש כי "
            "מדובר בניתוח לימודי לבחינת הבגרות ולא בפסיקת הלכה למעשה.",
            "",
        ]
    return [
        "## PRINCIPLE VIII — HALACHIC HUMILITY IN TOSHBA & CASE STUDIES",
        "CRITICAL: Every halachic analysis or case-study (Eru'on Halachti) solution in Bagrut Mode is strictly for "
        "**academic study and Bagrut exam preparation**, and is NEVER a practical halachic ruling (psak halacha)! "
        "Present the cases, rulings, and rationales (Case – Ruling – Rationale) strictly from the retrieved sources [S#], "
        "and explicitly state that this is for exam study only and not a ruling for practice.",
        "",
    ]


def _build_rubric_principles_lines(curriculum: dict[str, Any], lang: str) -> list[str]:
    he = (lang or "he") != "en"
    rubric = curriculum.get("rubric_principles_he" if he else "rubric_principles_en") or {}
    formula = rubric.get("core_formula") or ""
    principles = rubric.get("principles") or []
    lines = [
        "## עקרונות מחוון הבגרות (Bagrut Grading Rubric Principles)"
        if he
        else "## BAGRUT GRADING RUBRIC PRINCIPLES"
    ]
    if formula:
        lines.append(f"**נוסחת הליבה לתשובה מלאה:** {formula}" if he else f"**Core Full-Credit Formula:** {formula}")
    for p in principles:
        lines.append(f"- **{p.get('title', '')}**: {p.get('rule', '').strip()}")
    lines.append("")
    return lines


# ── Prompt Builders ──────────────────────────────────────────────────────────────────────────


def get_active_bagrut_curriculum(
    subject: str = "gemara",
    track: str = "mmd",
    units: str | int = 5,
    exam_code: str | None = None,
) -> dict[str, Any]:
    """Retrieve active Bagrut curriculum from DB cache if available, falling back to static YAML."""
    subj = subject.strip().lower()
    trk = track.strip().lower()
    unt = int(units) if str(units).isdigit() else 5
    if not exam_code:
        default_codes = {"gemara": "5391", "toshba": "5381", "tanakh": "2575", "machshava": "281"}
        exam_code = default_codes.get(subj)

    # 1. Check dynamic DB cache first (Zero deployment needed)
    try:
        from app.db import get_active_bagrut_curriculum_from_db
        db_curr = get_active_bagrut_curriculum_from_db(subj, trk, unt, exam_code=exam_code)
        if db_curr:
            return db_curr
    except Exception:
        pass

    # 2. Fallback to active_curriculum in data/bagrut_curriculum.yaml
    curr = load_bagrut_curriculum()
    active_root = curr.get("active_curriculum") or {}
    subj_active = active_root.get(subj) or {}
    if exam_code and exam_code in subj_active:
        return dict(subj_active[exam_code])
    if subj_active:
        first_key = next(iter(subj_active))
        return dict(subj_active[first_key])

    return {}


def format_active_curriculum_prompt_block(
    subject: str,
    track: str,
    units: str | int,
    lang: str = "he",
) -> list[str]:
    """Build prompt lines instructing the LLM to follow the active Ministry curriculum strictly."""
    curr_spec = get_active_bagrut_curriculum(subject, track, units)
    if not curr_spec:
        return []

    lines = []
    tractate = curr_spec.get("tractate") or curr_spec.get("tractate_book") or ""
    chapter = curr_spec.get("chapter") or curr_spec.get("chapter_he") or ""
    daf_range = curr_spec.get("daf_range") or curr_spec.get("daf_verses_he") or ""
    topics = curr_spec.get("key_topics") or []

    lines += [
        "## MANDATORY ACTIVE MINISTRY OF EDUCATION CURRICULUM (מיקוד משרד החינוך המחייב לשנת הלימודים)",
        f"- Target Subject: {subject.upper()} ({track}, {units} units)",
    ]
    if tractate:
        lines.append(f"- Active Tractate / Book (מסכת/ספר במיקוד): {tractate}")
    if chapter:
        lines.append(f"- Chapter (פרק במיקוד): {chapter}")
    if daf_range:
        lines.append(f"- Exact Pages / Verses (טווח דפים מחייב): {daf_range}")
    if topics:
        lines.append("- Core Sugyot / Topics (סוגיות ליבה מחייבות):")
        for tp in topics:
            lines.append(f"  * {tp}")
    lines += [
        "CRITICAL CURRICULUM CONSTRAINT (הנחיית מיקוד מחייבת):",
        "You MUST formulate all exam questions, sugya analyses, and rubric answers strictly within this specified "
        "active curriculum and from the retrieved SOURCES. Do NOT invent questions from arbitrary, unrelated pages!",
        "",
    ]
    return lines


def build_bagrut_file_job_md(
    question: str,
    hits: list,
    lang: str = "he",
    *,
    params: dict | None = None,
    tpl: dict | None = None,
    history: list | None = None,
) -> str:
    """Build the grounded bridge/agentic job markdown for `action in ("summary", "exam")`."""
    he = (lang or "he") != "en"
    curriculum = load_bagrut_curriculum()
    resolved = params or resolve_bagrut_params(question, history)
    subject = resolved.get("subject", "tanakh")
    track = resolved.get("track", "mmd")
    units = str(resolved.get("units", "5"))
    action = resolved.get("action", "summary")

    subj_cfg = (curriculum.get("subjects") or {}).get(subject) or {}
    track_cfg = (subj_cfg.get("track_details") or {}).get(track) or {}
    subj_title = subj_cfg.get("title_he" if he else "title_en") or subject
    track_title = track_cfg.get("title_he" if he else "title_en") or track
    track_focus = (track_cfg.get("focus_he" if he else "focus_en") or "").strip()

    lines: list[str] = [f"lang: {lang}", ""]

    # Inject minor safety block at the top when serving a minor (Spec 009)
    if audience_ctx is not None and getattr(audience_ctx.current(), "minor", False):
        safety_block = append_minor_safety("", lang).strip()
        if safety_block:
            lines += ["## MINOR AUDIENCE SAFETY RULES (MANDATORY)", safety_block, ""]

    prior = [h for h in (history or []) if _turn_text(h).strip()]
    if prior:
        lines.append("## CONVERSATION SO FAR")
        for h in prior[-6:]:
            lines.append(f"- {_turn_role(h)}: {_turn_text(h).strip()}")
        lines.append("")

    lines += [
        "## BAGRUT PARAMETERS",
        f"- Subject (מקצוע): {subj_title} ({subject})",
        f"- Track (מסלול): {track_title} ({track})",
        f"- Level (יחידות לימוד): {units} יח\"ל ({units} units)",
        f"- Requested Output (פעולה): {'חוברת סיכום ומיקודית לבגרות (summary)' if action == 'summary' else 'בחינת מתכונת + מחוון תשובות וניקוד למורה (exam + rubric)'}",
    ]
    if track_focus:
        lines.append(f"- Pedagogical Focus (דגשים פדגוגיים): {track_focus}")
    lines.append("")

    curr_lines = format_active_curriculum_prompt_block(subject, track, units, lang)
    if curr_lines:
        lines += curr_lines

    if subject == "gemara":
        lines += _build_aramaic_scaffold_lines(curriculum, lang)
    if subject == "toshba":
        lines += _build_halachic_humility_lines(lang)

    lines += _build_rubric_principles_lines(curriculum, lang)

    if tpl:
        tpl_title = (tpl.get("title_en") if not he else None) or tpl.get("title", "")
        tpl_struct = (tpl.get("structure_en") if not he else None) or tpl.get("structure", "")
        lines += [
            "## SELECTED BAGRUT TEMPLATE — follow THIS clean-room structure and pedagogy",
            f"{tpl_title} — {'Structure' if not he else 'מבנה'}: {tpl_struct}",
        ]
        if action == "summary":
            skel_sum = _load_tpl_skeleton(tpl, "summary", lang)
            if skel_sum:
                skel_sum = re.sub(r"<!--.*?-->", "", skel_sum, flags=re.S).strip()
                lines += [
                    "",
                    "SUMMARY TEMPLATE SKELETON — replace every [ ] placeholder with real grounded content from SOURCES:",
                    skel_sum,
                ]
        elif action == "solution":
            skel_sol = _load_tpl_skeleton(tpl, "solution", lang)
            if skel_sol:
                skel_sol = re.sub(r"<!--.*?-->", "", skel_sol, flags=re.S).strip()
                lines += [
                    "",
                    "SOLUTION TEMPLATE SKELETON — replace every [ ] placeholder with complete model answers grounded in SOURCES:",
                    skel_sol,
                ]
        else:
            skel_exam = _load_tpl_skeleton(tpl, "exam", lang)
            skel_rubric = _load_tpl_skeleton(tpl, "rubric", lang)
            if skel_exam:
                skel_exam = re.sub(r"<!--.*?-->", "", skel_exam, flags=re.S).strip()
                lines += [
                    "",
                    "EXAM TEMPLATE SKELETON — replace every [ ] placeholder with real grounded questions built ONLY from SOURCES:",
                    skel_exam,
                ]
            if skel_rubric:
                skel_rubric = re.sub(r"<!--.*?-->", "", skel_rubric, flags=re.S).strip()
                lines += [
                    "",
                    "RUBRIC TEMPLATE SKELETON — replace every [ ] placeholder with full model answers and point breakdowns grounded in SOURCES:",
                    skel_rubric,
                ]
        lines.append("")

    lines += ["## TOPIC / REQUEST", question.strip(), "", "## SOURCES"]
    if hits:
        lines += _format_sources_for_prompt(hits, lang)
    else:
        lines += ["(no sources retrieved yet)", ""]

    lines += [
        "## INSTRUCTIONS FOR CLAUDE",
        "STEP 0 — If the SOURCES above are empty or off-topic for the requested Bagrut topic, do NOT invent sources or questions from memory! "
        "First reply with ONLY a block starting with the EXACT line '===NEED_SOURCES===' followed by 1–4 focused search queries "
        "(exact biblical chapter/verses, Talmudic tractate & daf, or Mishnah chapter), and STOP.",
        "",
        "STEP 1 — CONSTITUTION PRINCIPLE I (GROUNDED, NEVER INVENTED):",
        "- Every question, quote, commentator opinion, Aramaic translation, and rubric model answer MUST be 100% grounded in the retrieved SOURCES [S#] above.",
        "- NEVER invent or reproduce a past Ministry of Education Bagrut exam question from parametric memory. Build original Bagrut-structured questions strictly from the retrieved sources [S#].",
        "- Cite every claim and source reference with its marker [S1], [S2], etc.",
        "- Quote verbatim source spans using quote references: {{S1: first words … last words}}.",
    ]
    if subject == "toshba":
        lines.append(
            "- CONSTITUTION PRINCIPLE VIII (HALACHIC HUMILITY): Include a clear study disclaimer that all halachic case studies (אירועונים) "
            "and rulings are presented strictly for academic Bagrut exam preparation and are NOT a practical halachic ruling (פסק הלכה למעשה)."
        )

    if action == "summary":
        lines += [
            "",
            "STEP 2 — Write ONE response containing these EXACT delimiter lines:",
            "===BAGRUT_SUMMARY===",
            "===ORDER===",
            "",
            "Under ===BAGRUT_SUMMARY===, write a comprehensive, structured Bagrut study guide (דף סיכום ומיקודית לבגרות) for the topic, including:",
            "1. פתיחה, הקשר ונושא מרכזי (Overview & Context) grounded in [S#].",
            "2. ביאור מילים קשות / מילון מונחים בארמית ומושגי יסוד (Key Terms & Vocabulary / Aramaic Glossary) from [S#].",
            "3. ניתוח מפורט של הפסוקים / שלבי הסוגיה (שקלא וטריא) / פירוק המשנה וההלכה (מקרה, דין, טעם) לפי המקורות [S#].",
            "4. השוואת מפרשים / מחלוקות תנאים, אמוראים וראשונים (Commentator & Sage Comparisons) grounded in [S#].",
            "5. שאלות חזרה ותרגול במבנה בגרות (סעיפים מדורגים א'–ב' עם ניקוד) + פתרונות מלאים לפי נוסחת המחוון (טענה + ביסוס [S#] + הסבר).",
            "",
            "Under ===ORDER===, write a single line listing the [S#] markers in the order used (e.g. 'S1, S2, S4').",
        ]
    elif action == "solution":
        lines += [
            "",
            "STEP 2 — Write ONE response containing these EXACT delimiter lines:",
            "===BAGRUT_SOLUTION===",
            "===ORDER===",
            "",
            "Under ===BAGRUT_SOLUTION===, write the Complete Student-Facing Bagrut Exam Solution (פתרון מלא ומנומק לשאלון בגרות) tailored to "
            f"{subj_title} ({track_title}, {units} יח\"ל):",
            "1. כותרת הפתרון, שאלון/פרק הנלמד וטבלת ריכוז שאלות ומבנה הניקוד המלא.",
            "2. לכל שאלה וסעיף בשאלון (בין אם נמסר בשאלת המשתמש/קובץ ובין אם נבנה מתוך המקורות):",
            "   - הצגת השאלה ומשקלה בנקודות.",
            "   - תשובת מופת מלאה ומנוסחת ברמת 100% המעוגנת ישירות במקורות [S#].",
            "   - פירוק התשובה לפי מחוון משרד החינוך: טענה מרכזית מפורשת (40%) + ביסוס מדויק (ציטוט מן המקור [S#], 30%) + הסבר מקשר ומבאר במילות התלמיד (30%).",
            "   - טיפ מעשי לבחינה / דגש למניעת שגיאות נפוצות של תלמידים בסעיף זה.",
            "",
            "Under ===ORDER===, write a single line listing the [S#] markers in the order used (e.g. 'S1, S2, S4').",
        ]
    else:
        lines += [
            "",
            "STEP 2 — Write ONE response containing these EXACT delimiter lines:",
            "===BAGRUT_EXAM===",
            "===BAGRUT_RUBRIC===",
            "===ORDER===",
            "",
            "Under ===BAGRUT_EXAM===, write a complete, student-facing Bagrut Mock Exam (בחינת מתכונת לבגרות) tailored to "
            f"{subj_title} ({track_title}, {units} יח\"ל):",
            "1. כותרת הבחינה, הנחיות לנבחן וחלוקת הניקוד (סה\"כ 100 נקודות או משקל ברור לכל שאלה וסעיף).",
            "2. קטעי המקור המלאים מתוך [S#] המוצגים לנבחן (כולל ניקוד/פיסוק וציון המקור).",
            "3. שאלות בגרות מדורגות (סעיפים א', ב', ג' עם ציון נקודות לכל סעיף, כגון '(10 נק')') הבוחנות הבנה, זיהוי קושי/מבנה, השוואת מפרשים/שיטות ויישום.",
            "4. אל תכלול את התשובות בתוך קובץ השאלון לתלמיד (===BAGRUT_EXAM===)!",
            (
                "5. חובת פיזור נושאי ומגוון מקורות (Mandatory Curriculum Diversity): "
                "אלא אם המשתמש הגדיר נושא יחיד ספציפי, עליך להבטיח שהבחינה משקפת מתכונת בגרות מלאה ומאוזנת: "
                "חלק את הבחינה לפרקים נפרדים המכסים נושאים מובחנים ושונים מתוך תוכנית הלימודים "
                "(למשל: פרק ראשון על משנה/בקיאות, פרק שני על השתלשלות ההלכה בתחום אחד, ופרק שלישי על תחום הלכתי נוסף או אירועון יישומי). "
                "חל איסור מוחלט לרכז את כל השאלות סביב מקור בודד או נושא יחיד — הבחינה חייבת לפזר את השאלות על פני מספר מקורות [S#] שונים ומגוונים."
                if not is_bagrut_narrow_topic_request(question)
                else "5. התמקדות בנושא המבוקש: בנה את השאלות והסעיפים במעמיק סביב הנושא והמקורות [S#] שהוגדרו בבקשה."
            ),
            "",
            "Under ===BAGRUT_RUBRIC===, write the complete Teacher Grading Rubric & Answer Key (מחוון תשובות וניקוד למורה):",
            "1. לכל שאלה וסעיף בשאלון: תשובת מופת מלאה ומפורטת המעוגנת במקורות [S#].",
            "2. פירוט רכיבי הציון לכל סעיף לפי נוסחת המחוון: טענה מפורשת (% מהניקוד) + ביסוס/ציטוט מן המקור [S#] (% מהניקוד) + הסבר במילים המקשר בין הציטוט לטענה (% מהניקוד).",
            "3. דגשים לבודק ושגיאות נפוצות של תלמידים שיש לשים לב אליהן.",
            "",
            "Under ===ORDER===, write a single line listing the [S#] markers in the order used (e.g. 'S1, S2, S4').",
        ]

    lines += [
        "",
        "LANGUAGE RULE: Write ONLY in the requested language (Hebrew for lang=he, English for lang=en) with zero foreign word bleed. "
        "Never copy internal corpus IDs (like 'Bava_Metzia.3.1') into prose — always use traditional Hebrew/English titles.",
    ]
    return "\n".join(lines)


def build_bagrut_chat_messages(
    question: str,
    hits: list,
    lang: str = "he",
    *,
    params: dict | None = None,
    tpl: dict | None = None,
    history: list | None = None,
    weak: bool = False,
) -> tuple[str, str]:
    """Build `(system_prompt, user_prompt)` for interactive Bagrut `practice` and `check` modes.

    Automatically applies `append_minor_safety(system_prompt, lang)` from `chavruta.llm.base`
    when running under a minor's `AudienceScope` (Spec 009).
    """
    he = (lang or "he") != "en"
    curriculum = load_bagrut_curriculum()
    resolved = params or resolve_bagrut_params(question, history)
    subject = resolved.get("subject", "tanakh")
    track = resolved.get("track", "mmd")
    units = str(resolved.get("units", "5"))
    action = resolved.get("action", "practice")

    subj_cfg = (curriculum.get("subjects") or {}).get(subject) or {}
    track_cfg = (subj_cfg.get("track_details") or {}).get(track) or {}
    subj_title = subj_cfg.get("title_he" if he else "title_en") or subject
    track_title = track_cfg.get("title_he" if he else "title_en") or track
    track_focus = (track_cfg.get("focus_he" if he else "focus_en") or "").strip()
    rubric_cfg = curriculum.get("rubric_principles_he" if he else "rubric_principles_en") or {}
    core_formula = rubric_cfg.get("core_formula") or ""

    if he:
        sys_parts = [
            f"אתה מורה ומאמן אישי מומחה להכנה לבחינות הבגרות ב**{subj_title}** (מסלול **{track_title}**, רמת **{units} יח\"ל**).",
            "חוק יסוד (עקרון I — Grounded, Never Invented): כל שאלה, רמז, פירוש מילה, בדיקת תשובה או הסבר חייבים להישען אך ורק על המקורות שסופקו לך [S#]. "
            "אסור בתכלית האיסור להמציא מקורות, ציטוטים, דעות מפרשים או שאלות בגרות משנים קודמות מתוך הזיכרון הפרמטרי!",
        ]
        if track_focus:
            sys_parts.append(f"דגשי המסלול ({track_title}): {track_focus}")

        if action == "check":
            sys_parts.append(
                "מצב פעולה: **בדיקת תשובה לפי מחוון בגרות (`check`)**.\n"
                f"נוסחת המחוון לבדיקה: **{core_formula}**\n"
                "עליך לבדוק את תשובת התלמיד ביחס למקורות [S#] ולמחוון הבגרות בשלושה חלקים ברורים:\n"
                "1. **✅ מה מדויק בתשובתך:** ציין אילו רכיבים בתשובת התלמיד נכונים ומדויקים (והערך את הניקוד היחסי).\n"
                "2. **⚠️ מה חסר או דורש דיוק לפי המחוון:** הצבע במדויק על רכיבים חסרים (למשל: חסר ציטוט/ביסוס מהכתוב, חסר הסבר במילים שלך המקשר בין הציטוט לטענה, לא הוצג הקושי בפסוק לפני דברי המפרש, או עירוב בין מקרה לדין).\n"
                "3. **📝 תשובת מופת מלאה (100% ניקוד):** נסח תשובת בגרות מלאה ומדויקת לפי נוסחת המחוון (טענה + ביסוס מן המקור [S#] + הסבר), מעוגנת אך ורק במקורות שסופקו."
            )
        else:
            sys_parts.append(
                "מצב פעולה: **תרגול בגרות אינטראקטיבי ולימוד מונחה (`practice`)**.\n"
                "פעל כמאמן בגרות סוקרטי וממוקד:\n"
                "- הצג לתלמיד את קטע המקור הרלוונטי מתוך [S#] (או התייחס לשאלת ההמשך שלו על הסיכום/המבחן).\n"
                "- נסח שאלת בגרות תקנית ומדורגת (סעיפים א'–ב' עם ניקוד לצד כל סעיף, למשל: **סעיף א' (8 נק')**, **סעיף ב' (7 נק')**) המבוססת ישירות על המקור [S#].\n"
                "- אם התלמיד מבקש הסבר או רמז: תן רמז מדורג ומכוון אל המילים המדויקות במקור [S#] בלי לחשוף מיד את הפתרון המלא.\n"
                "- אם התלמיד ענה על שאלת תרגול קודמת: הענק לו משוב קצר לפי נוסחת המחוון (**טענה + ביסוס [S#] + הסבר**) והמשך לסעיף או לשאלה הבאה."
            )

        if subject == "gemara":
            sys_parts.append(
                "דגשים לגמרא: הקפד לבאר מונחים בארמית המופיעים בסוגיה (כגון: מנא הני מילי, מאי שנא, איבעיא להו, תא שמע, מיתיבי, ורמינהו, הכא במאי עסקינן / אוקימתא, תיובתא, קמ\"ל, נפקא מינה) "
                "ולהבחין בבירור בין התפקיד המבני של כל שלב בשקלא וטריא לבין תוכנו ההלכתי."
            )
        elif subject == "toshba":
            sys_parts.append(
                "דגשים לתושב\"ע והלכה (עקרון VIII — ענווה הלכתית): הקפד על פירוק מבני של המשנה וההלכה ל**מקרה, דין וטעם**. "
                "בשאלות יישום ו'אירועון הלכתי', הבהר תמיד כי הניתוח של השיטות והפוסקים הוא לצורך לימודי-עיוני לקראת בחינת הבגרות בלבד, ואינו פסק הלכה למעשה."
            )

        sys_parts.append(
            "כתוב בעברית תקנית ובהירה בלבד, ללא מילים בשפה זרה וללא מזהים פנימיים באנגלית. סמן כל טענה במקור שלה [S#]."
            + QUOTE_REF_RULE_HE
        )
        system_prompt = "\n\n".join(sys_parts)
    else:
        sys_parts = [
            f"You are an expert Bagrut Exam Coach and Examiner for **{subj_title}** (**{track_title}**, **{units} units**).",
            "CONSTITUTION PRINCIPLE I (GROUNDED, NEVER INVENTED): Every question, hint, term definition, rubric evaluation, and explanation MUST rely strictly on the provided sources [S#]. "
            "NEVER invent sources, quotes, commentator views, or past Ministry of Education Bagrut questions from parametric memory!",
        ]
        if track_focus:
            sys_parts.append(f"Track Focus ({track_title}): {track_focus}")

        if action == "check":
            sys_parts.append(
                "MODE: **Bagrut Rubric Answer Grader (`check`)**.\n"
                f"Core Rubric Formula: **{core_formula}**\n"
                "Grade the student's response against the provided sources [S#] and the official Bagrut rubric in three structured parts:\n"
                "1. **✅ What is accurate in your answer:** Highlight accurate points and estimate partial/full credit.\n"
                "2. **⚠️ What is missing or needs refinement per the rubric:** Pinpoint missing rubric components (e.g. missing textual citation, missing own-words explanation linking the quote to the claim, not stating the textual difficulty before the commentary, or conflating case and ruling).\n"
                "3. **📝 Full Model Answer (100% credit):** Provide a complete model Bagrut answer following the Claim + Citation [S#] + Explanation formula, grounded strictly in [S#]."
            )
        else:
            sys_parts.append(
                "MODE: **Interactive Socratic Bagrut Practice (`practice`)**.\n"
                "Act as a focused Bagrut coach:\n"
                "- Present the relevant verified source text from [S#] (or address the student's follow-up question).\n"
                "- Pose a structured multi-part Bagrut question (sub-questions a–b with point values, e.g., **Part a (8 pts)**, **Part b (7 pts)**) grounded directly in [S#].\n"
                "- Offer graduated hints pointing to the text rather than giving away the full solution immediately; if the student answered a question, evaluate it per the rubric (**Claim + Citation [S#] + Explanation**) and advance."
            )

        if subject == "gemara":
            sys_parts.append(
                "Gemara Scaffolding: Explain Aramaic structural terms in context (e.g., mena hani milei, mai shna, ibaya lehu, ta shma, meitivei, u'reminehu, okimta, tyuvta, ka mashma lan, nafka mina) "
                "and distinguish between the structural role of each step in the shakla vetarya and its legal content."
            )
        elif subject == "toshba":
            sys_parts.append(
                "Toshba & Halacha Scaffolding (Principle VIII — Halachic Humility): Break down Mishnah and Halacha into **Case, Ruling, and Rationale**. "
                "For halachic case studies (Eru'on Halachti), explicitly note that the analysis is strictly for academic Bagrut exam preparation and is never a practical halachic ruling (psak)."
            )

        sys_parts.append(
            "Write clearly in English (you may quote Hebrew/Aramaic source text) and cite every claim by its marker [S#]."
            + QUOTE_REF_RULE
        )
        system_prompt = "\n\n".join(sys_parts)

    # Apply minor safety rules via chavruta.llm.base.append_minor_safety (Spec 009)
    system_prompt = append_minor_safety(system_prompt, lang)

    # Build user prompt
    user_lines: list[str] = []
    prior = [h for h in (history or []) if _turn_text(h).strip()]
    if prior:
        user_lines.append("## השיחה עד כה" if he else "## CONVERSATION SO FAR")
        for h in prior[-6:]:
            user_lines.append(f"- {_turn_role(h)}: {_turn_text(h).strip()}")
        user_lines.append("")

    if tpl:
        tpl_title = (tpl.get("title_en") if not he else None) or tpl.get("title", "")
        tpl_struct = (tpl.get("structure_en") if not he else None) or tpl.get("structure", "")
        if tpl_title or tpl_struct:
            user_lines.append(
                f"## תבנית בגרות נבחרת: {tpl_title} ({tpl_struct})"
                if he
                else f"## SELECTED BAGRUT TEMPLATE: {tpl_title} ({tpl_struct})"
            )
            user_lines.append("")

    if not hits or weak:
        if he:
            user_lines += [
                "## ⚠️ התראת אחזור מקורות",
                "לא נמצאו מקורות ממוקדים מספיק לשאלה זו (או שרמת הביטחון באחזור נמוכה). "
                "אם ביכולתך לשלוף את המקור המדויק, השב תחילה אך ורק בבלוק המתחיל בשורה המדויקת '===NEED_SOURCES===' ואחריה 1–3 שאילתות חיפוש ממוקדות (כגון שם ספר ופרק או מסכת ודף), ועצור. "
                "אם אין מקור מתאים, בקש מהתלמיד לציין את הפרק, הפסוק או הסוגיה המדויקת או להדביק את לשון השאלה — לעולם אל תמציא מקור או שאלת בגרות מהזיכרון!",
                "",
            ]
        else:
            user_lines += [
                "## ⚠️ RETRIEVAL NOTICE",
                "No strongly matching sources were retrieved yet. If you can identify the canonical source, reply first ONLY with "
                "'===NEED_SOURCES===' followed by 1–3 focused search queries, and STOP. Otherwise ask the student to specify the exact "
                "chapter, verse, or sugya — NEVER invent sources or exam questions from memory!",
                "",
            ]

    user_lines.append("## המקורות (הידע היחיד המותר לך):" if he else "## SOURCES (the only knowledge you may use):")
    if hits:
        user_lines += _format_sources_for_prompt(hits, lang)
    else:
        user_lines += ["(no sources retrieved)", ""]

    if he:
        user_lines += [
            f"## פניית התלמיד/ה ({'בדיקת תשובה לפי מחוון' if action == 'check' else 'תרגול ולימוד לבגרות'}):",
            question.strip(),
        ]
    else:
        user_lines += [
            f"## STUDENT INPUT ({'Answer Check per Rubric' if action == 'check' else 'Bagrut Practice'}):",
            question.strip(),
        ]

    return system_prompt, "\n".join(user_lines)


# Alias matching plan.md reference
build_bagrut_chat_prompt = build_bagrut_chat_messages
