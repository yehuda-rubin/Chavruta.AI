# -*- coding: utf-8 -*-
"""gen_school_templates.py — give EVERY lesson genre an age-differentiated (school) template ladder.

For each of the existing lesson genres (general, gemara-iyun, halacha, parasha, moadim, tefila,
machshava, mussar, chassidut, aggada) this writes 4 school variants — one per age band
(א–ג / ד–ו / ז–ט / י–יב) — under `lessons/templates/school-<genre>-<band>/`:
    manifest.yaml + TEMPLATE_source_sheet.md + TEMPLATE_lesson_flow.md + TEMPLATE_full_lesson.md

So every lesson template exists at five levels: the original beit-midrash/yeshiva template plus
four school age bands. The yeshiva templates are left untouched. Pedagogy is grounded in
evidence-based practice (explicit instruction I-Do/We-Do/You-Do, cognitive-load management,
retrieval practice, Bloom-appropriate questioning, formative assessment) and differentiated per
band. Content is STRUCTURE only; the model fills it from the shared source RAG. NO external LLM API.

    .venv/Scripts/python.exe scripts/gen_school_templates.py     # rewrite all school-* folders
    .venv/Scripts/python.exe scripts/index_templates.py          # then re-index the template RAG
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TDIR = REPO / "lessons" / "templates"

# ── Age bands — pedagogy blocks (evidence-based, differentiated) ──────────────────────────────
BANDS = [
    {
        "slug": "a-c", "grades": "א–ג", "age": "6–9", "label": "יסודי צעיר", "duration": "30 דק'",
        "dev": "חשיבה קונקרטית וקשב קצר; לומדים דרך סיפור, תמונה, תנועה ומשחק. רעיון אחד לשיעור.",
        "hook": "פתיחה חווייתית — סיפור קצר, תמונה גדולה, חפץ להמחשה או שאלה מסקרנת (\"מה הייתם עושים אילו…\").",
        "ido": "המורה מספר/מקריא את המקור בקול, מתרגם כל מילה ומצייר תמונה במילים; משפט־מפתח אחד חוזרים עליו יחד.",
        "wedo": "כולם יחד: הצגה קטנה, אצבע על המילה, השלמת מילה בקול — הרבה חזרה ותנועה.",
        "youdo": "כל ילד לבד: ציור של הרעיון, השלמת מילה, או \"ספר לחבר במילה אחת מה למדנו\".",
        "assess": "הערכה בעל־פה ובציור: \"הראו לי בהצגה\", \"איזה צבע מתאים לרעיון?\", שלוש שאלות כן/לא.",
        "questioning": "שאלות זכירה והבנה בסיסית (מה קרה? מי? היכן?) ושאלת חיבור אישית פשוטה.",
        "language": "עברית פשוטה מאוד; לתרגם ולהסביר כל מילה קשה; משפטים קצרים.",
        "sources": "מקור ראשי אחד (פסוק/משנה קצרה) + פירוש במסירה מפושטת (פרפרזה) + סיפור/תמונה.",
    },
    {
        "slug": "d-f", "grades": "ד–ו", "age": "9–12", "label": "יסודי בוגר", "duration": "45 דק'",
        "dev": "תחילת חשיבה מופשטת; יכולים להחזיק מקור + פירוש אחד ולהשוות שתי דעות בפשטות.",
        "hook": "פתיחה עם שאלה או חידה שמעמידה בעיה (\"איך ייתכן ש…?\") או קישור לחיים של הילד.",
        "ido": "המורה מדגים \"דוגמה מעובדת\": קורא את המקור, שואל שאלה, ומראה כיצד הפירוש עונה — צעד אחר צעד.",
        "wedo": "תרגול מודרך בזוגות (ראשית חברותא): מנתחים מקור שני יחד בעזרת מארגן גרפי (טבלה: מקור / שאלה / תשובה).",
        "youdo": "תרגול עצמאי: דף עבודה — התאמת פירוש למקור, השוואת שתי דעות בטבלה, ניסוח הרעיון במשפט.",
        "assess": "כרטיס יציאה (שאלה אחת לכתיבה) + תרגול־אחזור מהיר בפתיחת השיעור הבא.",
        "questioning": "שאלות הבנה ויישום (למה? מה ההבדל? מה היה קורה אילו…?) והשוואה בין שתי דעות.",
        "language": "עברית בהירה; להסביר מונחים חדשים; לעודד ניסוח עצמאי.",
        "sources": "מקור ראשי + שני פירושים/דעות פשוטים להשוואה + מקור יישום.",
    },
    {
        "slug": "g-i", "grades": "ז–ט", "age": "12–15", "label": "חטיבת ביניים", "duration": "45 דק'",
        "dev": "חשיבה מופשטת מתפתחת; חשובות הרלוונטיות והזהות; יכולים להחזיק מחלוקת ואת שורשה ולטעון טענה מנומקת.",
        "hook": "פתיחה עם דילמה/מחלוקת (\"שניים חלוקים — מי צודק?\") או שאלה ערכית הנוגעת לעולמם.",
        "ido": "המורה מעמיד את המחלוקת/החקירה בפשטות: שני צדדים ברורים (צד א׳ מול צד ב׳), ומדגים כיצד קוראים מקור וטוענים ממנו.",
        "wedo": "חברותא: כל זוג מקבל צד ומחפש במקורות תמיכה; ואז דיון כיתתי / דיבייט מובנה בין הצדדים.",
        "youdo": "כתיבת טיעון עצמאי: \"בחר צד ונמק משני מקורות\"; ניתוח מקור חדש לבד.",
        "assess": "טיעון כתוב או דיבייט; רובריקה: טענה + שני מקורות + מסקנה. תרגול־אחזור על השיעור הקודם.",
        "questioning": "שאלות ניתוח והערכה (מהו שורש המחלוקת? איזו ראיה חזקה יותר? מהי הנפקא מינה?).",
        "language": "עברית מלאה; מציגים מונחים למדניים בסיסיים (מחלוקת, סברא, נפקא מינה) ומסבירים אותם.",
        "sources": "מקור־בסיס (משנה/גמרא/פסוק) + שתי שיטות ראשונים/פרשנים + מקור המחדד את הנפקא מינה.",
    },
    {
        "slug": "j-l", "grades": "י–יב", "age": "15–18", "label": "תיכון", "duration": "45–60 דק'",
        "dev": "חשיבה כמעט־בוגרת; ניתוח מבוסס־מקור, טיעון מתמשך ומיומנות טקסט ראשוני; גשר אל עיון בית־מדרש — עדיין עם פיגומים ורלוונטיות.",
        "hook": "פתיחה עם שאלה עקרונית/חקירה או מקרה־מבחן חריף שמכריח להעמיק (\"מה הדין כאן — ולמה זה בכלל ספק?\").",
        "ido": "המורה מעמיד חקירה/מחלוקת עקרונית עם שני צדדים מנוסחים, ומדגים ניתוח מקור ראשוני וקישורו לצד.",
        "wedo": "חברותא מעמיקה: ניתוח ראשונים ומבוא לאחרונים, מיפוי כל מקור לצד, בהנחיית שאלות מכוונות.",
        "youdo": "עבודה עצמאית: ניתוח מקור חדש, כתיבת מסה/סיכום עיוני קצר, או הכנת קטע לדיון.",
        "assess": "מסה עיונית / סיכום סוגיה / מבחן מקורות; רובריקה: העמדת החקירה, מיפוי שיטות, נפקא מינה ומסקנה.",
        "questioning": "שאלות ניתוח, סינתזה והערכה ברמה גבוהה; חקירה עקרונית ושורשי מחלוקת.",
        "language": "עברית מלאה ומדויקת; מונחים למדניים; שאיפה לעצמאות בקריאת המקור.",
        "sources": "מקור־בסיס + שיטות ראשונים + אחרון/מבוא לחקירה + מקור נפקא מינה; לקראת עיון מבואי.",
    },
]

# ── The 10 lesson genres — each gets the full age ladder ──────────────────────────────────────
# `best_bands` = the bands where this genre is typically taught in school (used only to phrase
# when_to_use; every band is still generated so the ladder is complete).
GENRES = [
    {
        "slug": "general", "title": "סוגיה / גמרא כללי",
        "short": "לימוד סוגיה מובנה — מקור, הבנת הפשט, פירוש והלכה למעשה",
        "gates": ["המקור (משנה / גמרא)", "הבנת הפשט", "פירוש / מחלוקת", "הדין / המסקנה"],
        "keywords": ["גמרא", "סוגיה", "משנה", "שקלא וטריא", "רש\"י", "הלכה"],
        "ex_topics": ["שניים אוחזין בטלית", "אלו מציאות", "המפקיד", "ברכות השחר"],
        "ex_queries": ["שיעור גמרא על", "לימוד סוגיה", "הבנת המשנה"],
        "structure": "המקור → הבנת הפשט → פירוש/מחלוקת → הדין",
        "best_bands": ["d-f", "g-i", "j-l"],
    },
    {
        "slug": "gemara-iyun", "title": "עיון תלמודי (למדנות)",
        "short": "העמקה בסוגיה — שאלה/חקירה, שיטות והכרעה, בהתאמת גיל",
        "gates": ["העמדת הסוגיה", "השאלה / החקירה", "שיטות הראשונים", "ההכרעה והנפקא מינה"],
        "keywords": ["עיון", "למדנות", "חקירה", "שני צדדים", "תוספות", "נפקא מינה", "סברא"],
        "ex_topics": ["יאוש שלא מדעת", "מיגו", "ברי ושמא", "קים ליה בדרבה מיניה"],
        "ex_queries": ["שיעור עיון על", "חקירה בסוגיה", "למדנות"],
        "structure": "העמדת הסוגיה → החקירה → שיטות הראשונים → הכרעה ונפקא מינה",
        "best_bands": ["g-i", "j-l"],
    },
    {
        "slug": "halacha", "title": "הלכה ומצוות",
        "short": "הלכה מעשית — מהמצווה והמקור אל היישום בחיי היום־יום",
        "gates": ["המצווה / המקרה", "המקור", "הכלל", "היישום המעשי"],
        "keywords": ["הלכה", "מצוות", "שבת", "כשרות", "ברכות", "מה עושים", "יישום מעשי"],
        "ex_topics": ["ברכות הנהנין", "כיבוד הורים", "הלכות שבת", "נטילת ידיים", "צדקה"],
        "ex_queries": ["שיעור הלכה", "איך מברכים", "מה מותר בשבת", "מצווה למעשה"],
        "structure": "המצווה/המקרה → המקור → הכלל → היישום המעשי",
        "best_bands": ["a-c", "d-f", "g-i", "j-l"],
    },
    {
        "slug": "parasha", "title": "חומש ופרשת שבוע",
        "short": "פסוקי החומש והפרשה — מהפשט אל הרעיון והמסר",
        "gates": ["הפסוק / הסיפור", "פשט — רש\"י", "מדרש / מפרש נוסף", "הרעיון והמסר"],
        "keywords": ["חומש", "פרשת שבוע", "פסוק", "רש\"י", "פשט", "מדרש", "סיפורי התורה", "מסר"],
        "ex_topics": ["בריאת העולם", "נח והתיבה", "יציאת מצרים", "עשרת הדיברות", "יוסף ואחיו"],
        "ex_queries": ["שיעור על פרשת השבוע", "סיפור מהתורה", "מה רש\"י אומר על הפסוק"],
        "structure": "הפסוק/הסיפור → פשט (רש\"י) → מדרש/מפרש → הרעיון והמסר",
        "best_bands": ["a-c", "d-f", "g-i", "j-l"],
    },
    {
        "slug": "moadim", "title": "חגים ומועדים",
        "short": "חגי השנה — מקור החג, טעמו, מנהגיו, וחוויה והכנה מעשית",
        "gates": ["מקור החג", "הטעם", "מנהגים והלכות", "החוויה וההכנה"],
        "keywords": ["חגים", "מועדים", "חנוכה", "פסח", "פורים", "סוכות", "מנהגים", "חוויה"],
        "ex_topics": ["נס חנוכה", "סדר פסח", "מגילת אסתר", "ארבעת המינים", "מתן תורה"],
        "ex_queries": ["שיעור על חג", "למה חוגגים", "מנהגי החג", "הכנה לחג"],
        "structure": "מקור החג → הטעם → מנהגים והלכות → החוויה וההכנה",
        "best_bands": ["a-c", "d-f", "g-i", "j-l"],
    },
    {
        "slug": "tefila", "title": "תפילה וברכות",
        "short": "פירוש התפילה והברכות — נוסח, מקור, פירוש וכוונה",
        "gates": ["נוסח התפילה / הברכה", "המקור", "הפירוש", "הכוונה"],
        "keywords": ["תפילה", "ברכה", "סידור", "נוסח", "פירוש התפילה", "כוונה", "שמונה עשרה"],
        "ex_topics": ["מודה אני", "שמע ישראל", "ברכות השחר", "אשרי", "ברכת המזון"],
        "ex_queries": ["פירוש התפילה", "מה אומרים ב", "כוונת הברכה", "שיעור על תפילה"],
        "structure": "נוסח → מקור → פירוש → כוונה",
        "best_bands": ["a-c", "d-f", "g-i", "j-l"],
    },
    {
        "slug": "machshava", "title": "מחשבה ואמונה",
        "short": "רעיון אמוני/השקפי — שאלה, מקורות, עמדות ויישום",
        "gates": ["השאלה / הרעיון", "מקורות מכוננים", "עמדות ופיתוח", "היישום בחיים"],
        "keywords": ["מחשבה", "אמונה", "השקפה", "בחירה חופשית", "השגחה", "רעיון", "עולם הזה"],
        "ex_topics": ["בחירה חופשית", "אמונה והשגחה", "צלם אלוקים", "שכר ועונש", "אהבת ה'"],
        "ex_queries": ["שיעור על אמונה", "רעיון במחשבה", "שאלה השקפית"],
        "structure": "השאלה/הרעיון → מקורות → עמדות ופיתוח → יישום",
        "best_bands": ["g-i", "j-l"],
    },
    {
        "slug": "mussar", "title": "מוסר ומידות",
        "short": "עבודת המידות — הכרת המידה, מקורה, סיפור/משל ותיקון מעשי",
        "gates": ["הכרת המידה", "המקור", "סיפור / משל", "התיקון והיישום"],
        "keywords": ["מוסר", "מידות", "דרך ארץ", "ענווה", "כעס", "חסד", "תיקון המידות"],
        "ex_topics": ["מידת הענווה", "מידת הכעס", "מידת החסד", "אמת ושקר", "סבלנות"],
        "ex_queries": ["שיעור על מידה", "מידת ה", "חינוך לערכים", "עבודת המידות"],
        "structure": "הכרת המידה → מקור → סיפור/משל → תיקון ויישום",
        "best_bands": ["a-c", "d-f", "g-i", "j-l"],
    },
    {
        "slug": "chassidut", "title": "חסידות ופנימיות",
        "short": "מושג בעבודת ה' — שאלה פנימית, מאמר, והעבודה למעשה",
        "gates": ["המושג", "השאלה הפנימית", "המאמר / המקור", "העבודה למעשה"],
        "keywords": ["חסידות", "פנימיות", "עבודת ה'", "דבקות", "שמחה", "מאמר", "התבוננות"],
        "ex_topics": ["שמחה בעבודת ה'", "דבקות", "אהבה ויראה", "התבוננות", "ביטול"],
        "ex_queries": ["שיעור בחסידות", "מושג בעבודת ה'", "רעיון חסידי"],
        "structure": "המושג → השאלה הפנימית → המאמר → העבודה למעשה",
        "best_bands": ["g-i", "j-l"],
    },
    {
        "slug": "aggada", "title": "אגדה ומדרש",
        "short": "אגדתא / מדרש — הקושי, פירושי חז\"ל, והרעיון והמסר",
        "gates": ["האגדה / המדרש", "הקושי / התמיהה", "פירוש חז\"ל / מפרשים", "הרעיון והמסר"],
        "keywords": ["אגדה", "מדרש", "אגדתא", "חז\"ל", "משל", "רעיון", "מסר"],
        "ex_topics": ["אגדות רבה בר בר חנה", "תנורו של עכנאי", "הלל והנכרי", "כמשל"],
        "ex_queries": ["שיעור על אגדה", "מדרש על", "פירוש האגדה"],
        "structure": "האגדה → הקושי → פירושי חז\"ל → הרעיון והמסר",
        "best_bands": ["d-f", "g-i", "j-l"],
    },
]


def gates_for(genre: dict, band_slug: str) -> list[str]:
    g = genre["gates"]
    if band_slug == "a-c":
        return [g[0], "סיפור / תמונה / המחשה", g[-1]]
    if band_slug == "j-l":
        return g + ["העמקה — אחרון / מבוא לחקירה"]
    return g


def yamlq(s: str) -> str:
    return '"' + s.replace('"', '\\"') + '"'


def manifest(genre: dict, band: dict) -> str:
    tid = f"school-{genre['slug']}-{band['slug']}"
    title = f"{genre['title']} — כיתות {band['grades']} ({band['label']})"
    gates = gates_for(genre, band["slug"])
    kw = genre["keywords"] + [
        "בית ספר", "תלמידים", f"כיתות {band['grades']}", band["label"], f"גיל {band['age']}",
        "דף עבודה" if band["slug"] in ("d-f", "g-i") else "הוראה מפורשת",
        "חברותא" if band["slug"] in ("g-i", "j-l") else "הצגה וסיפור",
    ]
    suited = band["slug"] in genre["best_bands"]
    suit_note = ("" if suited else
                 f" (הערה: ז'אנר זה נלמד בדרך כלל בשכבות בוגרות יותר; זו גרסה מותאמת ומופשטת לגיל {band['age']}.)")
    desc = (
        f"שיעור {genre['title']} לתלמידי בית ספר בכיתות {band['grades']} (גיל {band['age']}, {band['label']}). "
        f"{genre['short']}. מבנה פדגוגי (הוראה מפורשת: הדגמה → תרגול מודרך → תרגול עצמאי), מותאם לשלב "
        f"ההתפתחות: {band['dev']} משך משוער {band['duration']}.{suit_note}"
    )
    when = (
        f"בחר תבנית זו כאשר מכינים שיעור {genre['title']} לתלמידי בית ספר בכיתות {band['grades']} "
        f"(גיל {band['age']}) — שיעור כיתתי מובנה ומותאם־גיל (ולא שיעור עיון לבני ישיבה). "
        f"מתאים לרמת {band['label']}: {band['questioning']}"
    )
    q = "\n".join(f"  - {yamlq(x)}" for x in (
        genre["ex_queries"] + [f"שיעור {genre['title']} לכיתה {band['grades']}"]
    ))
    return (
        "# manifest.yaml — מטא-דאטה לאחזור התבנית ב-RAG של התבניות (קהל: בית ספר).\n"
        f"id: {tid}\n"
        f"title: {yamlq(title)}\n"
        f"genre: school-{genre['slug']}\n"
        "audience: school\n"
        f"subject: {genre['slug']}\n"
        f"grade_band: {band['slug']}\n"
        f"age_range: {yamlq(band['grades'] + ' — גיל ' + band['age'] + ' (' + band['label'] + ')')}\n"
        "mode: lesson\n"
        f"description: >\n  {desc}\n"
        f"when_to_use: >\n  {when}\n"
        f"keywords: [{', '.join(kw)}]\n"
        f"structure: {yamlq(' → '.join(gates))}\n"
        "files:\n"
        "  source_sheet: TEMPLATE_source_sheet.md\n"
        "  lesson_flow: TEMPLATE_lesson_flow.md\n"
        "  full_lesson: TEMPLATE_full_lesson.md\n"
        f"example_topics: [{', '.join(genre['ex_topics'])}]\n"
        "example_queries:\n" + q + "\n"
    )


def source_sheet(genre: dict, band: dict) -> str:
    gates = gates_for(genre, band["slug"])
    rows = "\n".join(
        f"## {i}. {g}\n- **[{i}]** — [המקור בשלמותו; למטה־גיל יש לצרף פרפרזה/תרגום מפושט של המילים הקשות.]\n"
        for i, g in enumerate(gates, 1)
    )
    return (
        f"<!--\nתבנית: דף מקורות — {genre['title']} · כיתות {band['grades']} ({band['label']})  |  Chavruta.AI\n"
        "המקורות מסודרים לפי סדר הלימוד בשיעור. המודל הוא המלמד; אין API חיצוני.\n-->\n\n"
        f"# דף מקורות — [נושא השיעור]  ·  כיתות {band['grades']}\n\n"
        "| | |\n|---|---|\n"
        f"| **קהל יעד** | תלמידי בית ספר, כיתות {band['grades']} (גיל {band['age']}) |\n"
        f"| **משך משוער** | {band['duration']} |\n"
        f"| **מהלך השיעור** | [lesson_flow.md](lesson_flow.md) |\n\n"
        f"> **הערת מקורות לשלב זה:** {band['sources']}\n\n"
        "---\n\n" + rows + "\n"
        "---\n\n### הערת שקיפות\n"
        "המקורות נשלפו מהראג של Chavruta.AI (bge-m3 + Qdrant, אחזור בלבד). דף המקורות והשיעור נכתבו "
        "על־ידי המודל מן המקורות — **ללא שימוש ב-API של מודל חיצוני**.\n"
    )


def lesson_flow(genre: dict, band: dict) -> str:
    gates = gates_for(genre, band["slug"])
    src_line = ", ".join(f"[{i+1}]" for i in range(len(gates)))
    return f"""<!--
תבנית: מהלך השיעור — {genre['title']} · כיתות {band['grades']} ({band['label']})  |  Chavruta.AI
מלווה את דף המקורות ומפנה אליו במספרי המקורות [N]. מבנה הוראה מפורשת (הדגמה → תרגול מודרך → תרגול עצמאי).
-->

# מהלך השיעור — [נושא השיעור]  ·  כיתות {band['grades']}

| | |
|---|---|
| **דף מקורות נלווה** | [source_sheet.md](source_sheet.md) |
| **משך משוער** | {band['duration']} |
| **קהל יעד** | כיתות {band['grades']} (גיל {band['age']} · {band['label']}) |
| **שלב התפתחות** | {band['dev']} |

> **מטרות למידה:** [1–2 מטרות מדידות — "התלמיד יסביר…", "התלמיד ידגים…".]

---

## 0. פתיחה — עוררות ומטרה  *(≈{'5' if band['slug']=='a-c' else '7'} דק')*
- **הוק:** {band['hook']}
- **חיבור לידע קודם / תרגול־אחזור:** [שאלה קצרה על השיעור הקודם — לחזק זיכרון לפני שמוסיפים חדש.]
- **מה נשיג היום:** [מטרת השיעור במשפט אחד, בשפת התלמיד.]

## 1. הקנייה — המורה מדגים (I do)  *(≈{'7' if band['slug']=='a-c' else '10'} דק')*
- **[1]** — {band['ido']}

## 2. תרגול מודרך — יחד (We do)  *(≈{'8' if band['slug']=='a-c' else '12'} דק')*
- **[2]** — {band['wedo']}
- *עצירת בדיקה (CFU):* [שאלה קצרה לכל הכיתה לוודא הבנה לפני שממשיכים.]

## 3. העמקה — {gates[2] if len(gates) > 2 else gates[-1]}  *(≈{'6' if band['slug']=='a-c' else '10'} דק')*
- **[3]** — [המקור/הדעה הבאה; {band['questioning']}]

## 4. תרגול עצמאי (You do)  *(≈{'7' if band['slug']=='a-c' else '10'} דק')*
- **המשימה:** {band['youdo']}
- **הבחנה (דיפרנציאציה):** [משימת בסיס לכולם + הרחבה למתקדמים + פיגום למתקשים.]

## 5. סיכום והערכה מעצבת  *(≈5 דק')*
- **סיכום בשפת התלמיד:** [הרעיון המרכזי במשפט אחד; לקשר בחזרה למטרה.]
- **הערכה מעצבת:** {band['assess']}
- **שלוש שאלות לחזרה:** [1) זכירה · 2) הבנה · 3) חיבור אישי/יישום.]

---

### הערת פדגוגיה ({band['label']})
- **שפה:** {band['language']}
- **מקורות בשיעור זה:** {src_line} (ראו דף המקורות).
- המהלך נכתב על־ידי המודל מן המקורות — **ללא API של מודל חיצוני**. יש להתאים תזמון ורמה לכיתה.
"""


def full_lesson(genre: dict, band: dict) -> str:
    gates = gates_for(genre, band["slug"])
    deep = ""
    if band["slug"] != "a-c":
        cmp_ = ("מעמידים שני צדדים (צד א׳ מול צד ב׳) וכל תלמיד מנמק"
                if band["slug"] in ("g-i", "j-l") else "משווים בין שתי הדעות בטבלה")
        extra = " ואת המקור הנוסף" if len(gates) > 3 else ""
        deep = (f"## העמקה — {gates[2]}\n[מביאים את **[3]**{extra}; {band['questioning']} {cmp_}.]\n")
    bridge = ""
    if band["slug"] == "j-l":
        bridge = (f"## מבוא לחקירה / העמקה  *(תיכון)*\n[מביאים את **[{len(gates)}]** — אחרון/מבוא לחקירה "
                  "שמחדד את שורש המחלוקת; מנסחים את החקירה ואת הנפקא מינה. הגשר אל עיון בית־מדרש.]\n")
    young = "מספרים אותו כסיפור עם המחשה" if band["slug"] == "a-c" else "מסבירים צעד־אחר־צעד מה כתוב ומה השאלה שהוא מעורר"
    wedo_do = "מציגים/משחקים את הרעיון יחד" if band["slug"] == "a-c" else "הכיתה מנתחת יחד עם המורה, ומשווה"
    last_link = ("מה לוקחים ללב וליישום ביום־יום" if genre["slug"] in ("halacha", "moadim", "tefila", "mussar")
                 else "הרעיון/המסר שנשאר איתנו")
    return f"""<!--
תבנית: השיעור המלא — {genre['title']} · כיתות {band['grades']} ({band['label']})  |  Chavruta.AI
פרוזה של שיעור לדוגמה בגובה העיניים של הגיל, לפי מבנה הוראה מפורשת. הסוגריים [ ] = למילוי מן המקורות.
-->

# [נושא השיעור] — שיעור לכיתות {band['grades']}

**קהל:** גיל {band['age']} ({band['label']}) · **משך:** {band['duration']} · **מקצוע:** {genre['title']}

---

## פתיחה
{band['hook']}
[פותחים בסיפור/שאלה/המחשה קונקרטית ומחברים לעולם של התלמיד. מסיימים ב: "היום נגלה ש…".]

## הקנייה — {gates[0]}  *(המורה מדגים)*
{band['ido']}
[מביאים את **[1]**, קוראים, ו{young}.]

## תרגול מודרך — {gates[1]}  *(יחד)*
{band['wedo']}
[מביאים את **[2]**; {wedo_do} — ומוודאים הבנה בשאלת בדיקה.]

{deep}{bridge}## תרגול עצמאי  *(כל תלמיד)*
{band['youdo']}
[משימה קצרה שמיישמת את הרעיון; מוסיפים הבחנה: בסיס לכולם, הרחבה למתקדמים, פיגום למתקשים.]

## סיכום ומסר
[חוזרים על הרעיון המרכזי במשפט אחד בשפת התלמיד, ומחברים ל{gates[-1]} — {last_link}.]

**שלוש שאלות לחזרה:** [1) זכירה · 2) הבנה · 3) חיבור/יישום.]

---

### הערת שקיפות
השיעור נכתב על־ידי המודל (Claude) מתוך מקורות שנשלפו מהראג של Chavruta.AI — **ללא שימוש ב-API של מודל חיצוני**.
מותאם לכיתות {band['grades']}; יש לכוונן לרמת הכיתה.
"""


def main() -> None:
    # clean out ALL previous school-* folders so the set matches the genres exactly
    removed = 0
    for d in TDIR.glob("school-*"):
        if d.is_dir():
            shutil.rmtree(d); removed += 1
    if removed:
        print(f"removed {removed} old school-* folders\n")

    count = 0
    for genre in GENRES:
        for band in BANDS:
            d = TDIR / f"school-{genre['slug']}-{band['slug']}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "manifest.yaml").write_text(manifest(genre, band), encoding="utf-8")
            (d / "TEMPLATE_source_sheet.md").write_text(source_sheet(genre, band), encoding="utf-8")
            (d / "TEMPLATE_lesson_flow.md").write_text(lesson_flow(genre, band), encoding="utf-8")
            (d / "TEMPLATE_full_lesson.md").write_text(full_lesson(genre, band), encoding="utf-8")
            count += 1
    print(f"✅ generated {count} school templates ({len(GENRES)} genres × {len(BANDS)} bands)")


if __name__ == "__main__":
    main()
