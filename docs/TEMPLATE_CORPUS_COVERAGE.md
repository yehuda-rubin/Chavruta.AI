# כיסוי הקורפוס לתבניות השיעור: `chavruta_commercial`

**נבדק:** 2026-10-20 · **אוסף:** `chavruta_commercial` (2,494,931 נקודות, סטטוס green)
**שיטה:** בדיקה לקריאה בלבד על השרת (Nebius VM), דרך REST של Qdrant. כל בדיקה היא התאמה מדויקת (exact match) לשדה `ref` דרך האינדקס המילולי (MatchAny), ללא וקטורים, ללא טקסט ובלי סריקה מלאה. הצורות שנבדקו נגזרו מכללי `corpus/refs.py` (`<Title>_on_<Base>.<k>`, שם הקומנטטור מתוך מחרוזת ה-ref). מכיוון שהבדיקה מתבססת על שמות מוערכים, **ABSENT פירושו: לא נמצא באף אחת מצורות השם שנוסו**, לא הוכחה היעדר מוחלט. הכיסוי של כל קומנטטור: מספר ה-ref שנמצאו מתוך מספר שנוסו.

| סוג מקור | סטטוס | דוגמאות ref | הערות |
|---|---|---|---|
| בסיס: בראשית א:א–ג | PRESENT | `Genesis.1.1`, `Genesis.1.2` (+ `Genesis.1.3`) | 3/3 נמצאו |
| בסיס: שמות כ:א–ג | PRESENT | `Exodus.20.1`, `Exodus.20.2` (+ `Exodus.20.3`) | 3/3 נמצאו |
| רש"י על בראשית/שמות (פרשה) | PARTIAL | `Rashi_on_Genesis.1.1.1`, `Rashi_on_Exodus.20.1.1` | 16/48 נמצאו. בראשית א:א ✓, א:ב ✓, א:ג ✗. שמות כ:א–ג ✓ |
| אבן עזרא (פרשה) | PRESENT | `Ibn_Ezra_on_Genesis.1.1.1`, `Ibn_Ezra_on_Exodus.20.1.1` | 22/48 נמצאו. כל שישה הפסוקים מכוסים |
| רשב"ם (פרשה) | PARTIAL | `Rashbam_on_Exodus.20.3.1` | 1/48 בלבד. כמעט נעדר |
| רמב"ן (פרשה) | PARTIAL | `Ramban_on_Genesis.1.1.1`, `Ramban_on_Genesis.1.3.1` | 6/48. בראשית א:א ✓, א:ג ✓, א:ב ✗, שמות כ ✗ |
| ספורנו (פרשה) | PRESENT | `Sforno_on_Genesis.1.1.1`, `Sforno_on_Exodus.20.2.1` | 17/48. כל שישה הפסוקים מכוסים |
| אברבנאל (פרשה) | ABSENT | — | 0/48 (שם שנוסה: `Abarbanel`) |
| חזקוני (פרשה) | ABSENT | — | 0/48 (שם שנוסה: `Chizkuni`) |
| אור החיים (פרשה) | PARTIAL | `Or_HaChaim_on_Genesis.1.1.1`, `Or_HaChaim_on_Exodus.20.1.1` | 32/48. שמות כ:א–ג מכוסים (8 לכל פסוק). בראשית: רק א:א (8 ref), א:ב ו-א:ג ✗ |
| בראשית רבה | ABSENT | — | 0/7 צורות (`Bereshit_Rabbah`, `Bereishit_Rabbah`, פסוקים 1.1–1.3) |
| ספרי | ABSENT | — | 0/9 בביקורת (`Sifrei_Numbers`, `Sifrei_Bamidbar`, `Sifrei_Deuteronomy`). ספרי אינו מכסה בראשית/שמות, ולכן ABSENT כצפוי |
| מכילתא דרבי ישמעאל (הקשר שמות כ) | ABSENT | — | 0/6 צורות (`Mekhilta_DeRabbi_Yishmael`, `Mekhilta_d'Rabbi_Yishmael`) |
| בסיס: בבא מציעא ב' א (`Bava_Metzia.3.1`–`3.5`) | PRESENT | `Bava_Metzia.3.1`, `Bava_Metzia.3.2` | 5/5 נמצאו. סטטוס: מיפוי אמוד-לינארי, N = 2·2−1 = 3 |
| בסיס: סנהדרין כ"ה א (`Sanhedrin.49.1`–`49.5`) | PRESENT | `Sanhedrin.49.1`, `Sanhedrin.49.5` | 5/5 נמצאו. סטטוס: N = 2·25−1 = 49 |
| רש"י על בבא מציעא | PARTIAL | `Rashi_on_Bava_Metzia.3.1.1`, `Rashi_on_Bava_Metzia.3.2.1` | 7/90. מקטעים 3.1–3.4 בלבד |
| תוספות על בבא מציעא | PARTIAL | `Tosafot_on_Bava_Metzia.3.1.1`, `Tosafot_on_Bava_Metzia.3.2.1` | 3/90 |
| רשב"א על בבא מציעא | PARTIAL | `Rashba_on_Bava_Metzia.3.1`, `Rashba_on_Bava_Metzia.3.6` | 6/90, רק בצורה ברמת דף (`.3.k`). לא נמצאו ברמת מקטע |
| רא"ש על בבא מציעא | PARTIAL | `Rosh_on_Bava_Metzia.3.1.1`, `Rosh_on_Bava_Metzia.3.5.2` | 7/90 |
| ר"ן / ריטב"א / רמב"ן על בבא מציעא | ABSENT | — | 0/90 לכל אחד. נוסו צורות ברמת מקטע וברמת דף |
| רי"ף / מאירי על בבא מציעא | ABSENT | — | 0/90 לכל אחד |
| רמב"ם הלכות גזילה ואבידה (בבא מציעא) | PRESENT | `Mishneh_Torah,_Robbery_and_Lost_Property.1.1`, `Mishneh_Torah,_Robbery_and_Lost_Property.1.13` | 13/15 נמצאו בפרק א (1.1–1.13). 1.14 ו-1.15 לא נמצאו |
| רש"י על סנהדרין | PARTIAL | `Rashi_on_Sanhedrin.49.1.1`, `Rashi_on_Sanhedrin.49.5.2` | 4/90 |
| תוספות על סנהדרין | PARTIAL | `Tosafot_on_Sanhedrin.49.5.1` | 1/90 |
| רשב"א, ר"ן, ריטב"א, רמב"ן, רא"ש, רי"ף, מאירי על סנהדרין | ABSENT | — | 0/90 לכל אחד |
| רמב"ם הלכות סנהדרין (תחת השם שנוסה) | ABSENT | — | 0/36 תחת `Mishneh_Torah,_Sanhedrin_and_the_Penalties_Imposed_Therein` (פרקים 1–2). מצאתי רק רמב"ם גזילה ואבידה, שנכלל באותה קבוצה בדיקה. שם אחר לא נבדק |
| טור או"ח סימן א | PARTIAL | `Tur,_Orach_Chayim.1.1` | 1/6 (סעיפים 1.1–1.5 נוסו; רק 1.1 נמצא) |
| בית יוסף או"ח סימן א | PARTIAL | `Beit_Yosef,_Orach_Chayim.1.1.1` | 1/6. רק ref אחד |
| שולחן ערוך או"ח סימן א | PRESENT | `Shulchan_Arukh,_Orach_Chayim.1.1`, `Shulchan_Arukh,_Orach_Chayim.1.5` | 5/5 |
| רמ"א על או"ח א | ABSENT | — | 0/16 (גם `Mapah_on_…` נוסה) |
| משנה ברורה על או"ח א | ABSENT | — | 0/18 צורות. בקובץ `eval_results/ws_works_scan.json` (סריקת Wikisource) מופיע שם המשנה ברורה, אבל זה לא מאגר הקורפוס ולא נספר |
| שולחן ערוך יו"ד סימן א | PRESENT | `Shulchan_Arukh,_Yoreh_De'ah.1.1`, `Shulchan_Arukh,_Yoreh_De'ah.1.5` | 5/5. הכתיב עם גרש (`De'ah`), לא `Deah` |
| ט"ז על יו"ד א | ABSENT | — | 0/16 (`Taz_on_…`, `Turei_Zahav_on_…`) |
| ש"ך על יו"ד א | PARTIAL | `Siftei_Kohen_on_Shulchan_Arukh,_Yoreh_De'ah.1.1.1` | 1/16 בלבד |
| מהר"ל (נטיבות/גבורות/תפארת ישראל) | PRESENT | `Netzach_Yisrael.1.1`, `Tiferet_Yisrael.1.1`, `Gevurot_Hashem.1.1` | 9/23. נמצאו 3 ספרים, כל אחד בסעיפים 1.1–1.3. דרך החיים, באר הגולה, נתיבות עולם, גור אריה לא נמצאו |
| רמח"ל: מסילת ישרים | PRESENT | `Mesillat_Yesharim.1.1`, `Mesillat_Yesharim.2.1` | 3/3 מהצורות שנבדקו (1.1, 1.2, 2.1) |
| רמח"ל: דרך השם | ABSENT | — | 0/4 צורות (`Derekh_Hashem`, `Derech_Hashem`) |
| ספר החינוך | ABSENT | — | 0/4 |
| חובות הלבבות | ABSENT | — | 0/6 (כולל `Duties_of_the_Heart`) |
| רבנו בחיי | ABSENT | — | 0/13 (`Rabbeinu_Bahya` ו-`Rabbeinu_Bachya`) |
| הכוזרי | ABSENT | — | 0/5 |
| הרב קוק (אורות) | ABSENT | — | 0/6 (`Orot`, `Orot_HaKodesh`, `Orot_HaTeshuvah`). תואם את הציפייה |
| ליקוטי מוהר"ן | ABSENT | — | 0/5 |
| ליקוטי תורה | ABSENT | — | 0/4 |
| תורה אור | ABSENT | — | 0/4 |
| שפת אמת | ABSENT | — | 0/4 |
| נועם אלימלך | ABSENT | — | 0/3 |
| קדושת לוי | ABSENT | — | 0/4 |
| תניא (ביקורת: מחיקה מכוונת) | ABSENT | — | 0/6 (`Tanya,_Part_I`, `Tanya`, `Likutei_Amarim`). אושר: 0 |

## סיכום לתבניות

| תבנית | התמיכה בקורפוס |
|---|---|
| parasha-iyun-kushya | חלקית. רש"י, אבן עזרא, ספורנו ואור החיים מכוסים על חלק מהפסוקים. רמב"ן ורשב"ם חלקיים מאוד. אברבנאל, חזקוני, בראשית רבה וספרי אינם קיימים |
| parasha-questions-sheet | חלקית. הטקסט המקראי מלא, ולכן שאלות על הפשט נתמכות. פירושי הפסוק נתמכים רק בחלק מהקומנטטורים |
| daf-insights | חלקית. רש"י, תוספות ורא"ש קיימים בחלק מהמקטעים. רשב"א חלקי. ר"ן, ריטב"א, רמב"ן, רי"ף ומאירי אינם קיימים בבדיקה |
| daf-halacha-outline | חלקית מאוד. רמב"ם גזילה ואבידה קיים לבבא מציעא, אבל רמב"ם סנהדרין לא נמצא בשם שנוסה. שולחן ערוך קיים, ובית יוסף וטור חלקיים. רמ"א, משנה ברורה וט"ז אינם קיימים |
| machshava-close-reading | חלקית. מהר"ל (3 ספרים) ומסילת ישרים קיימים. דרך השם, ספר החינוך, חובות הלבבות, רבנו בחיי והכוזרי אינם קיימים |
| chassidut-maamar-chapter | לא נתמך. כל מקורות החסידות שנבדקו (ליקוטי מוהר"ן, ליקוטי תורה, תורה אור, שפת אמת, נועם אלימלך, קדושת לוי) הם ABSENT |
| chassidut-sichah | לא נבדק. סיחות לא נכללו ברשימת הבדיקה. מכיוון שמקורות החסידות שנבדקו אינם נמצאים במאגר, לא ניתן להניח תמיכה |

---

## תיקון (בדיקה שנייה, ידנית)

הבדיקה לעיל חיפשה רק רפים בצורת Sefaria (`Rashi_on_...`). חלק מהספרים נמצאים בשכבת ויקיטקסט העברי תחת
תוויות עבריות (ללא `_on_`), ולכן סומנו בטעות "חסר": לפי `eval_results/ws_works_scan.json` קיימים בקורפוס
**משנה ברורה על אורח חיים** (≈695 פריטים בסריקה), **חידושי הריטב"א על הש"ס** (≈262), **ספר החינוך** (≈108)
ועוד. לא נמצאו שם: רמ"א, בית יוסף, ט"ז, כוזרי, רבנו בחיי, רי"ף, ר"ן. מצד שני אומתו בבדיקה ישירה (חיפוש
`ref` מדויק ב-VM, קריאה בלבד): `Rashi_on_Genesis.1.1.1`, `Ramban_on_Genesis.1.1.1`, `Or_HaChaim_on_Genesis.1.1.1`,
`Rosh_on_Bava_Metzia.1.1.1`, `Rashba_on_Bava_Metzia.3.1`, `Tosafot_on_Bava_Metzia.3.1.1`, `Rashi_on_Bava_Metzia.3.1.1`,
`Sifrei_Devarim.1.1`. לא נמצאו בצורות שנוסו: `Mishnah_Berurah.*`, בראשית רבה. המסקנה: הסימון "חלקי" נובע מרמת
הקטע (`.1` ברמת מילה/ד"ה), ו"חסר" אינו הוכחה.
