"""Parallel live evaluation of the 3 beta modes: 10 tests for EACH mode (30 tests total).

Modes evaluated:
1. `sourcesheet` — Source Sheet Companion (10 diverse tests)
2. `parsha` — Parshat HaShavua (10 diverse tests)
3. `dafyomi` — Daf Yomi (10 diverse tests)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from typing import Any

# Ensure path
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

# ── 1. Source Sheet Companion Tests (10 tests) ───────────────────────────────

SOURCESHEET_TESTS = [
    {
        "id": "SS01_gemara_tosafot_relative",
        "mode": "sourcesheet",
        "title": "ייאוש שלא מדעת (ב\"מ כ\"א ע\"א) + רש\"י ותוספות",
        "question": (
            "1. בבא מציעא דף כ\"א ע\"א:\n"
            "אמר רבא: ייאוש שלא מדעת לא הוי ייאוש. אביי אמר: הוי ייאוש.\n\n"
            "2. רש\"י שם ד\"ה ייאוש שלא מדעת:\n"
            "כגון שנפלה ממנו אבידה ועדיין לא ידע שנפלה ממנו.\n\n"
            "3. תוספות ד\"ה שמע מינה:\n"
            "ואם תאמר, והא אמרינן לקמן בפירקין... (וצ\"ע ברמב\"ם)"
        ),
    },
    {
        "id": "SS02_halacha_shulchan_aruch_magen_avraham",
        "mode": "sourcesheet",
        "title": "זמן קריאת שמע של שחרית (שו\"ע או\"ח ומג\"א)",
        "question": (
            "1. שולחן ערוך אורח חיים סימן נ\"ח סעיף א':\n"
            "זמן קריאת שמע של שחרית משיראה את חברו הרגיל עמו קצת ברחוק ד' אמות ויכירנו.\n\n"
            "2. מגן אברהם שם ס\"ק א':\n"
            "פירוש שאינו רגיל עמו כל כך, דאי רגיל טובא מכיר אפילו ברחוק יותר."
        ),
    },
    {
        "id": "SS03_rambam_raavad_editor_note",
        "mode": "sourcesheet",
        "title": "הגדרת המינים (רמב\"ם הלכות תשובה והשגת הראב\"ד)",
        "question": (
            "1. רמב\"ם הלכות תשובה פרק ג' הלכה ז':\n"
            "חמשה הן הנקראים מינים: האומר שאין שם אלוה ואין לעולם מנהיג... והאומר שיש שם רבון אחד אבל שהוא גוף ובעל תמונה.\n\n"
            "2. השגת הראב\"ד שם:\n"
            "ולמה קרא לזה מין? וכמה גדולים וטובים ממנו הלכו בזו המחשבה לפי מה שראו במקראות... (וצ\"ע בכסף משנה שיישב דעת רבינו)"
        ),
    },
    {
        "id": "SS04_tanakh_rashbam_external_ref",
        "mode": "sourcesheet",
        "title": "קידוש החודש (שמות י\"ב) + רשב\"ם ומקור חיצוני",
        "question": (
            "1. שמות פרק י\"ב פסוק ב':\n"
            "הַחֹדֶשׁ הַזֶּה לָכֶם רֹאשׁ חֳדָשִׁים רִאשׁוֹן הוּא לָכֶם לְחָדְשֵׁי הַשָּׁנָה.\n\n"
            "2. רשב\"ם שם:\n"
            "ניסן יהיה ראש לחדשים למניין יציאת מצרים.\n\n"
            "3. ספר המאמרים לרבי עקיבא יוסף שלזינגר ח\"ב עמוד ק\"כ (מקור חיצוני)"
        ),
    },
    {
        "id": "SS05_choshen_mishpat_ketzot_netivot",
        "mode": "sourcesheet",
        "title": "קניינים וממונות (שו\"ע חו\"מ שמ\"ח, קצות החושן ונתיבות המשפט)",
        "question": (
            "1. שולחן ערוך חושן משפט סימן שמ\"ח סעיף א':\n"
            "אסור לגזול או לגנוב אפילו כל שהוא בין מישראל בין מעובד כוכבים.\n\n"
            "2. קצות החושן שם ס\"ק א':\n"
            "בדין איסור גזל פחות משווה פרוטה אם הוי איסור דאורייתא או מדרבנן.\n\n"
            "3. נתיבות המשפט שם:\n"
            "וביאר דהחיוב להחזיר תלוי בשווה פרוטה אבל האיסור איכא בכל שהוא."
        ),
    },
    {
        "id": "SS06_pesachim_ran_tosafot_shem",
        "mode": "sourcesheet",
        "title": "חמץ לפני זמנו (פסחים כ\"א ע\"א, רש\"י, תוספות ור\"ן)",
        "question": (
            "1. פסחים דף כ\"א ע\"א:\n"
            "כל שעה שמותר לאכול מאכיל לבהמה לחיה ולעופות.\n\n"
            "2. רש\"י שם:\n"
            "כל זמן שחמץ מותר בהנאה.\n\n"
            "3. תוספות ד\"ה כל שעה:\n"
            "לאיתויי שעה חמישית דאסור באכילה ומותר בהנאה.\n\n"
            "4. ר\"ן שם:\n"
            "וכן פסק הרי\"ף ז\"ל."
        ),
    },
    {
        "id": "SS07_mishnah_berurah_and_tur",
        "mode": "sourcesheet",
        "title": "ברכות השחר וקריאת שמע (ברכות ב' ע\"א, שו\"ע רל\"ה ומשנ\"ב)",
        "question": (
            "1. ברכות דף ב' ע\"א:\n"
            "מאימתי קורין את שמע בערבית משעה שהכהנים נכנסים לאכול בתרומתן.\n\n"
            "2. שולחן ערוך אורח חיים סימן רל\"ה סעיף א':\n"
            "זמן קריאת שמע של ערבית משעת צאת הכוכבים.\n\n"
            "3. משנה ברורה שם ס\"ק ג':\n"
            "ואם קרא קודם צאת הכוכבים צריך לקרותה שנית בלי ברכות."
        ),
    },
    {
        "id": "SS08_unindexed_responsa_principle_one",
        "mode": "sourcesheet",
        "title": "הפניות שו\"ת חיצוניות (מבחן עיקרון א' — ללא המצאת מקורות)",
        "question": (
            "1. שבת דף קי\"ח ע\"ב:\n"
            "כל המקיים שלוש סעודות בשבת ניצול משלוש פורענויות.\n\n"
            "2. שו\"ת חתם סופר אבן העזר ח\"ב סימן קל\"ז (מראה מקום ללא טקסט)\n\n"
            "3. שו\"ת אגרות משה יורה דעה ח\"ד סימן כ\"ב (מראה מקום ללא טקסט)"
        ),
    },
    {
        "id": "SS09_mishnah_bartenura_tosafot_yom_tov",
        "mode": "sourcesheet",
        "title": "מסכת אבות ומשנה (משנה אבות א' א' + ברטנורא ותוספות יום טוב)",
        "question": (
            "1. משנה אבות פרק א' משנה א':\n"
            "משה קיבל תורה מסיני ומסרה ליהושע ויהושע לזקנים.\n\n"
            "2. רבינו עובדיה מברטנורא שם:\n"
            "לפי שמסכת זו אינה מיוסדת על פי מצוה כשאר מסכתות, הקדים שגם מוסרים אלו מסיני.\n\n"
            "3. תוספות יום טוב שם:\n"
            "דייק מדוע נקט לשון קבלה ומסירה."
        ),
    },
    {
        "id": "SS10_machshava_aggadah_maharal",
        "mode": "sourcesheet",
        "title": "אגדה ומחשבת ישראל (שבת פ\"ח ע\"א, כפה עליהם הר כגיגית ומהר\"ל)",
        "question": (
            "1. שבת דף פ\"ח ע\"א:\n"
            "ויתייצבו בתחתית ההר - מלמד שכפה הקדוש ברוך הוא עליהם את ההר כגיגית.\n\n"
            "2. רש\"י שם ד\"ה כפה עליהם:\n"
            "שאם לא יקבלו את התורה שם תהא קבורתם.\n\n"
            "3. מהר\"ל מפראג גבורות ה' פרק ס\"ו:\n"
            "כי קבלת התורה היתה מחוייבת מצד עצם המציאות ולא נמסרה לבחירה בלבד."
        ),
    },
]


# ── 2. Parshat HaShavua Tests (10 tests) ─────────────────────────────────────

PARSHA_TESTS = [
    {
        "id": "PA01_central_theme_flow",
        "mode": "parsha",
        "title": "ציר הרעיון המרכזי של פרשת השבוע",
        "question": "מהו המסר הרעיוני המרכזי והקשר הפנימי בין נושאי פרשת השבוע?",
    },
    {
        "id": "PA02_rashi_vs_ramban_dispute",
        "mode": "parsha",
        "title": "מחלוקת רש\"י ורמב\"ן בפרשת השבוע",
        "question": "הצג מחלוקת עקרונית ומעמיקה בין רש\"י לרמב\"ן על אחד מפסוקי הפרשה ובאר את שורש המחלוקת ביניהם.",
    },
    {
        "id": "PA03_halachic_derivation_mitzvah",
        "mode": "parsha",
        "title": "מצווה והלכה היוצאת מפרשת השבוע",
        "question": "בחר אחת המצוות המופיעות בפרשת השבוע ובאר כיצד היא נפסקה להלכה ברמב\"ם ובשולחן ערוך.",
    },
    {
        "id": "PA04_ibn_ezra_vs_sforno",
        "mode": "parsha",
        "title": "השוואת פשט: אבן עזרא וספורנו",
        "question": "השווה בין פירוש האבן עזרא לפירוש הספורנו על פסוק מרכזי בפרשה, ומה ההבדל בגישתם לפשט?",
    },
    {
        "id": "PA05_midrash_rabba_illuminating_peshat",
        "mode": "parsha",
        "title": "מדרש חז\"ל על הפרשה וביאורו",
        "question": "הבא מדרש חז\"ל מרכזי (מדרש רבה / תנחומא) על פרשת השבוע ובאר כיצד הוא מאיר את עומק הפסוקים.",
    },
    {
        "id": "PA06_mussar_and_chassidut_message",
        "mode": "parsha",
        "title": "מסר בעבודת הנפש וחסידות",
        "question": "איזה מסר מוסרי או רעיון עמוק בעבודת הנפש עולה מפרשת השבוע לפי ספרי המוסר והחסידות?",
    },
    {
        "id": "PA07_haftarah_and_parsha_connection",
        "mode": "parsha",
        "title": "הקשר בין הפרשה להפטרה",
        "question": "מהו הקשר המהותי והרעיוני בין פרשת השבוע לבין ההפטרה הנקראת עמה?",
    },
    {
        "id": "PA08_textual_kushya_and_resolutions",
        "mode": "parsha",
        "title": "קושיה חזקה בלשון הפסוקים ותירוצה",
        "question": "הצג קושיה או דיוק לשוני בולט באחד מפסוקי הפרשה וכיצד יישבו אותה מפרשי הפשט (רש\"י, רשב\"ם, חזקוני)?",
    },
    {
        "id": "PA09_or_hachayim_kli_yakar_pearl",
        "mode": "parsha",
        "title": "פנינת 'אור החיים' או 'כלי יקר'",
        "question": "הבא פירוש עמוק או חידוש למדני של בעל ה'אור החיים' הקדוש או ה'כלי יקר' על פסוקי הפרשה.",
    },
    {
        "id": "PA10_contemporary_ethical_reflection",
        "mode": "parsha",
        "title": "השתקפות מעשית ואקטואלית לחיינו",
        "question": "כיצד העקרונות והערכים הנלמדים מפרשת השבוע מדריכים אותנו באתגרים האתיים והחינוכיים של ימינו?",
    },
]


# ── 3. Daf Yomi Tests (10 tests) ─────────────────────────────────────────────

DAFYOMI_TESTS = [
    {
        "id": "DY01_sugya_overview_and_structure",
        "mode": "dafyomi",
        "title": "מהלך הסוגיה המרכזית בדף היומי",
        "question": "באר את מהלך הסוגיה המרכזית בדף היומי של היום, משאלת הפתיחה ועד למסקנת הגמרא.",
    },
    {
        "id": "DY02_core_inquiry_chakira",
        "mode": "dafyomi",
        "title": "חקירת עומק למדנית בסברת הדף",
        "question": "העמד חקירה למדנית (שני צדדים בהבנת הדין) ביסוד הסברא של הדף של היום, עם נפקא מינה מעשית.",
    },
    {
        "id": "DY03_rashi_vs_tosafot_dispute",
        "mode": "dafyomi",
        "title": "מחלוקת רש\"י ותוספות בדף היומי",
        "question": "הבא מחלוקת מרכזית בין רש\"י לתוספות בדף היומי של היום ובאר את יסוד המחלוקת ביניהם.",
    },
    {
        "id": "DY04_halachic_pesak_rambam_shulchan_aruch",
        "mode": "dafyomi",
        "title": "פסק ההלכה ברמב\"ם ובשולחן ערוך",
        "question": "כיצד נפסקה סוגיית הדף היומי של היום להלכה במשנה תורה לרמב\"ם ובשולחן ערוך?",
    },
    {
        "id": "DY05_gemara_diyuk_precision",
        "mode": "dafyomi",
        "title": "דיוק בלשון הגמרא בדף היומי",
        "question": "דייק בלשון הגמרא או המימרא המופיעה בדף היומי של היום — איזו הלכה או הבנה עולה מדיוק הלשון?",
    },
    {
        "id": "DY06_rishonim_ramban_rashba_ritva",
        "mode": "dafyomi",
        "title": "שיטות הראשונים (רמב\"ן / רשב\"א / ריטב\"א)",
        "question": "כיצד ביארו הרמב\"ן, הרשב\"א או הריטב\"א את הקושיא המרכזית המתעוררת בסוגיית הדף היומי?",
    },
    {
        "id": "DY07_maharsha_penei_yehoshua_depth",
        "mode": "dafyomi",
        "title": "חידוש המהרש\"א / פני יהושע על הדף",
        "question": "באר קושיה או הערה למדנית של המהרש\"א או הפני יהושע על מהלך הגמרא בדף של היום.",
    },
    {
        "id": "DY08_chavruta_guided_questions",
        "mode": "dafyomi",
        "title": "שאלות מנחות ללימוד בחברותא",
        "question": "נסח 3 שאלות מנחות ומדורגות (מרמת פשט ועד רמת סברא) ללימוד הסוגיה של היום בחברותא.",
    },
    {
        "id": "DY09_practical_halachic_application",
        "mode": "dafyomi",
        "title": "השלכה מעשית של דין הגמרא",
        "question": "מהי ההשלכה ההלכתית או המעשית של הסוגיה בדף של היום לחיי היום-יום?",
    },
    {
        "id": "DY10_sugya_synthesis_and_summary",
        "mode": "dafyomi",
        "title": "סיכום תמציתי ומסקנת הסוגיה",
        "question": "סכם בקצרה את עיקרי מסקנות הסוגיה של הדף היומי ואת הכלל היסודי שלמדנו ממנה.",
    },
]


def run_single_test(tc: dict[str, Any], admin_owner: str = "admin_eval_test") -> dict[str, Any]:
    """Execute one query against the API implementation and score results."""
    from app.api import _run_query_impl

    t0 = time.perf_counter()
    res = {
        "id": tc["id"],
        "mode": tc["mode"],
        "title": tc["title"],
        "status": "UNKNOWN",
        "elapsed_s": 0.0,
        "answer_preview": "",
        "citations_count": 0,
        "files_count": 0,
        "grounded": False,
        "error": None,
    }

    try:
        qr = _run_query_impl(
            question=tc["question"],
            lang="he",
            intent_str=tc["mode"],
            history=[],
            owner_id=admin_owner,
        )
        elapsed = time.perf_counter() - t0
        res["elapsed_s"] = round(elapsed, 2)
        res["answer_preview"] = (qr.answer or "")[:200].replace("\n", " ") + "..."
        res["citations_count"] = len(qr.citations or [])
        res["files_count"] = len(qr.files or [])
        res["grounded"] = qr.grounded

        # Validation rules
        if tc["mode"] == "sourcesheet":
            if res["files_count"] >= 1 and len(qr.answer) > 20:
                res["status"] = "PASSED"
            else:
                res["status"] = f"FAILED: Missing files ({res['files_count']}) or answer too short"
        else:  # parsha or dafyomi
            if len(qr.answer) > 40:
                res["status"] = "PASSED"
            else:
                res["status"] = "FAILED: Answer too short"

    except Exception as exc:
        res["status"] = "ERROR"
        res["error"] = str(exc)
        res["elapsed_s"] = round(time.perf_counter() - t0, 2)

    return res


def run_mode_suite(mode_name: str, test_cases: list[dict[str, Any]], max_workers: int = 5) -> list[dict[str, Any]]:
    print(f"\n=======================================================")
    print(f"🔹 Running 10 Parallel Tests for Mode: [{mode_name.upper()}] (Concurrency: {max_workers})")
    print(f"=======================================================")

    t0 = time.perf_counter()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(run_single_test, tc): tc for tc in test_cases}
        for future in concurrent.futures.as_completed(future_map):
            tc = future_map[future]
            try:
                res = future.result()
                results.append(res)
                print(f"  [{res['status']}] {res['id']} — {res['title']} ({res['elapsed_s']}s)")
                if res.get("files_count"):
                    print(f"      📁 Files generated: {res['files_count']} | Citations: {res['citations_count']}")
                elif res.get("citations_count"):
                    print(f"      📖 Citations: {res['citations_count']}")
            except Exception as exc:
                print(f"  [ERROR] {tc['id']}: {exc}")

    elapsed = round(time.perf_counter() - t0, 2)
    passed = sum(1 for r in results if r["status"] == "PASSED")
    print(f"--- Finished [{mode_name.upper()}]: {passed}/{len(test_cases)} Passed in {elapsed}s ---\n")
    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate beta modes in parallel.")
    parser.add_argument("--mode", choices=["all", "sourcesheet", "parsha", "dafyomi"], default="all")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    suites = []
    if args.mode in ("all", "sourcesheet"):
        suites.append(("sourcesheet", SOURCESHEET_TESTS))
    if args.mode in ("all", "parsha"):
        suites.append(("parsha", PARSHA_TESTS))
    if args.mode in ("all", "dafyomi"):
        suites.append(("dafyomi", DAFYOMI_TESTS))

    all_results = {}
    t_start = time.perf_counter()

    for mode_name, tests in suites:
        all_results[mode_name] = run_mode_suite(mode_name, tests, max_workers=args.workers)

    total_time = round(time.perf_counter() - t_start, 2)
    total_tests = sum(len(res) for res in all_results.values())
    total_passed = sum(sum(1 for r in res if r["status"] == "PASSED") for res in all_results.values())

    print("\n" + "=" * 60)
    print(f"🏁 GRAND TOTAL EVALUATION SUMMARY: {total_passed}/{total_tests} PASSED across all modes in {total_time}s")
    print("=" * 60)

    # Output detailed JSON results
    with open("eval_results_30_tests.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print("Detailed JSON saved to eval_results_30_tests.json")


if __name__ == "__main__":
    main()
