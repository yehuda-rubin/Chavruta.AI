# מיפוי מקורות חוקיים לספרים החסרים בקורפוס

**תאריך:** 2026-10-20
**היקף:** מחקר בלבד. לא שונה קוד, נתונים או הגדרות. הקובץ היחיד שנוצר הוא דוח זה.
**מקורות שנפתחו בפועל:** עמודי Sefaria API (`/api/v2/index/…`, `/api/texts/…`), עמודי Hebrew Wikisource, GitHub של Sefaria-Export (LICENSE.md), והשוואה ל-`src/chavruta/corpus/data/licenses.json` (5,828 כותרות).

---

## 0. ממצאים מרכזיים

1. **רוב הרשימה כבר בקורפוס.** לפי `licenses.json`, קיימים הכותרות: Beit Yosef, Tur, Turei Zahav (הט"ז, כל ארבעת החלקים), Siftei Kohen (הש"ך, על התורה וביורה דעה וחושן משפט), Rif (51 כותרות), Ran (15), Ritva (18), Meiri (13), Rabbeinu Bahya, Kuzari, Duties of the Heart (חובות הלבבות), Derekh Hashem, Bereshit/Shemot/Vayikra/Bamidbar/Devarim Rabbah, Abarbanel on Torah, Chizkuni, Rashbam (על התורה), Likutei Moharan, Sefat Emet, Noam Elimelekh, Kedushat Levi.
2. **הפערים האמיתיים:** הגהות הרמ"א על השולחן ערוך (אין כותרת "Mapah" ב-Sefaria API, ואין "Mapah"/"Rema" ב-`licenses.json` מלבד "Responsa of Rema"), שך על אורח חיים, Torah Or (לא נמצא כלל), Beit HaBechirah (הכותרת לא נמצאה ב-API), Likutei Torah (לא נמצא ב-`licenses.json`), וחלקי מסכתות חסרים ב-Ran, Ritva, Rif, Meiri.
3. **שדה "Public Domain" ב-Sefaria אינו תמיד חוקי מלא.** דוגמאות בקורפוס עצמו: `Gur Aryeh on Shemot` מסומן PD עם המהדורה "Machon Yerushalyim, 1989-1995", ו-`Likutei Moharan` באנגלית הוא CC-BY-NC (Mykoff). מהדורה מודרנית עם עריכה אינה בהכרח PD גם כשהטקסט הקלאסי כן.
4. **ה-GitHub של Sefaria-Export לא מציין רישיון אחד.** הדף מפנה ל-LICENSE.md, שנאמר בו: "Each text is licensed separately, so there is no overall license for this repository" ו"You can find the license for each text in their JSON versions under the `license` field". הערכים האפשריים: "Public Domain", "CC0", "CC-BY", "CC-BY-SA", "CC-BY-NC".
5. **Hebrew Wikisource:** בכל העמודים שנפתחו הכיתוב בתחתית הוא "הטקסט מוגש בכפוף לרישיון Creative Commons ייחוס-שיתוף זהה 4.0; ייתכן שישנם תנאים נוספים." ובדף "ויקיטקסט:זכויות יוצרים": "זכות היוצרים על יצירה פוקעת בתום 70 שנים ממות המחבר." (life+70).
6. **Tanya** לא הוצעה, כמבוקש.

---

## 1. טבלת מקורות

הערה לעמודה "stated licence": הציטוט הוא מה שהעמוד עצמו אומר. כשלא נמצא שדה רישיון בעמוד, כתוב "לא נמצא בעמוד". "בקורפוס" מתייחס למה שנרשם ב-`licenses.json` (לא לנתוני ה-HF שטעונים בפועל).

| work | best source | URL opened | stated licence | verdict | notes |
|---|---|---|---|---|---|
| הגהות הרמ"א (Mapah) על שו"ע | Hebrew Wikisource (מחבר) | https://he.wikisource.org/wiki/מחבר:רמ"א | "הטקסט מוגש בכפוף לרישיון Creative Commons ייחוס-שיתוף זהה 4.0; ייתכן שישנם תנאים נוספים." | NEEDS LAWYER | הרמ"א נפטר 1572 (PD). העמוד מציין "הגהות הרמ"א" כיצירה, אך לא נפתח דף טקסט של ההגהות. ב-Sefaria: `api/v2/index/Mapah` → "No book named 'Mapah'", ואין כותרת "Rema" (`api/v2/index/Rema` → "No book named 'Rema'"). שם הכותרת ב-Sefaria לא אומת. |
| שולחן ערוך (המקור) | Hebrew Wikisource | https://he.wikisource.org/wiki/שולחן_ערוך | "הטקסט מוגש בכפוף לרישיון Creative Commons ייחוס-שיתוף זהה 4.0" | USABLE | העמוד קיים. יש בו קישורים לארבעת החלקים. התוכן עצמו לא נפתח. |
| בית יוסף | Sefaria API | https://www.sefaria.org/api/v2/index/Beit_Yosef,_Orach_Chayim | לא נמצא בעמוד (האינדקס בלי שדה רישיון) | USABLE | כבר בקורפוס: `licenses.json["Beit Yosef"]` he=Public Domain (Vilna 1923), en=CC0. |
| טור | Sefaria API | https://www.sefaria.org/api/v2/index/Tur,_Orach_Chayim | לא נמצא בעמוד | USABLE | כבר בקורפוס: `licenses.json["Tur"]` he=Public Domain (Orach Chaim, Vilna 1923). בדקנו רק את הכותרת. |
| ט"ז (Taz) | Sefaria (כותרת קיימת בקורפוס) | לא נפתח עמוד API (הבקשה נכשלה על שם הכותרת) | לא נמצא בעמוד; בקורפוס: he=Public Domain | USABLE | `licenses.json["Turei Zahav on Shulchan Arukh, Orach Chayim"]`: he=PD (Maginei Eretz, Lemberg 1893). קיימים גם YD, EH, CM. |
| ש"ך (Shakh) | Sefaria (כותרת קיימת בקורפוס) | לא נפתח עמוד API | לא נמצא בעמוד; בקורפוס: he=Public Domain | USABLE (חלקי) | `Siftei Kohen on Torah` (PD, Warsaw 1883), `…Yoreh De'ah` ו-`…Choshen Mishpat` קיימים. **שך על אורח חיים לא נמצא ב-`licenses.json`.** |
| רי"ף (Rif) | Sefaria (כותרות קיימות) | לא נפתח עמוד API (שם ה-ref נכשל) | בקורפוס: he=Public Domain (Vilna) | USABLE (חלקי) | 51 כותרות "Rif …" בקורפוס. לא נבדקה שלמות כל המסכתות. |
| ר"ן (Ran) | Sefaria (כותרות קיימות) | https://www.sefaria.org/api/texts/Ran_on_Nedarim.2a (נכשל) ו-"Ran on Yoma" בקורפוס | בקורפוס: he=Public Domain (Vilna), en="" | USABLE (חלקי) | 15 כותרות. בחלק מהן אין רישיון אנגלי, אך העברית PD. |
| מאירי (Beit HaBechirah) | Sefaria | https://www.sefaria.org/api/texts/Beit_HaBechirah_on_Berakhot.2a (נכשל: "Could not find title") | בקורפוס "Meiri on Berakhot"/"Meiri on Shabbat": he="" (ריק), en=CC0 | NEEDS LAWYER | 13 כותרות "Meiri on …" אבל **הרישיון העברי ריק** ב-Berakhot וב-Shabbat. שם הכותרת הנכון ב-Sefaria לא אומת. |
| ריטב"א (Ritva) | Sefaria (כותרות קיימות) | לא נפתח עמוד API | בקורפוס: "Ritva on Berakhot" he=Public Domain (Warsaw 1863) | USABLE (חלקי) | 18 מסכתות בקורפוס. לא נבדקה שלמות. |
| רבנו בחיי | Sefaria API | https://www.sefaria.org/api/texts/Rabbeinu_Bahya,_Genesis.1.1?lang=he&context=0&commentary=0 | Hebrew: "Public Domain" ("Vocalized Edition", Warsaw 1878); English (Munk): "CC-BY" | USABLE | כבר בקורפוס (he=PD). אם נשתמש באנגלית של מונק, נדרש ייחוס ל-CC-BY. |
| הכוזרי (Kuzari) | Sefaria API | https://www.sefaria.org/api/texts/Kuzari.1.1?lang=he&context=0&commentary=0 | אנגלית (Hirschfeld 1905): "Public Domain"; עברית (Ben-Yehuda, תרגום אבן תיבון): "CC-BY-SA"; Even Shmuel 1973: "unknown" | USABLE | כבר בקורפוס (PD). **לא להשתמש ב-Even Shmuel 1973.** עמוד Ben-Yehuda (https://bybe.benyehuda.org/read/7575) לא נפתח. |
| חובות הלבבות (Chovot HaLevavot) | Sefaria; Hebrew Wikisource | https://www.sefaria.org/api/v2/index/Chovot_HaLevavot (מחזיר "Duties of the Heart"); https://he.wikisource.org/wiki/חובות_הלבבות | Wikisource: "הטקסט מוגש בכפוף לרישיון Creative Commons ייחוס-שיתוף זהה 4.0; ייתכן שישנם תנאים נוספים." | USABLE | בקורפוס כ-"Duties of the Heart" (he=PD, Vocalized Edition; en=PD, Hyamson 1925). Wikisource: דף חלקי (פתיחה ותוכן עניינים). המחבר בחיי אבן פקודה, התרגום יהודה אבן תיבון. |
| דרך ה' (Ramchal) | Sefaria API | https://www.sefaria.org/api/v2/index/Derekh_Hashem | לא נמצא בעמוד (אין שדה רישיון) | USABLE | כבר בקורפוס: `licenses.json["Derekh Hashem"]` he=Public Domain ("Handwritten Manuscript EH 47 C 32. 1896"), en=CC0. המחבר משה חיים לוצאטו. |
| אורות / הרב קוק (Orot) | Sefaria; Hebrew Wikisource | לא נפתח עמוד Sefaria נפרד | בקורפוס: `Orot` he=CC-BY-SA ("Wikisource"); `Orot HaTeshuvah` he="" (ריק), en=CC0 | NEEDS LAWYER | הרב קוק נפטר 1935, והטקסט הקלאסי עבר את life+70. אבל מהדורות מוסד הרב קוק (ובמיוחד עריכות מודרניות) עלולות להיות מוגנות. הרישיון העברי של "Orot HaTeshuvah" ריק. |
| בראשית רבה (וכל הרבות) | Sefaria API; Hebrew Wikisource | https://www.sefaria.org/api/texts/Bereshit_Rabbah.1.1?lang=he&context=0&commentary=0 | Sefaria-English: "CC-BY" (2022); Hebrew Torat Emet: "unknown"; Hebrew Wikisource: "CC-BY-SA"; Wünsche (German, 1881): "Public Domain" | USABLE | כבר בקורפוס: בראשית, שמות, ויקרא, במדבר, דברים רבה (he="Daat", PD). לא לשאוב מ-Torat Emet (unknown). |
| מכילתא | Sefaria | https://www.sefaria.org/api/texts/Mekhilta_DeRabbi_Ishmael,_Bachodesh.1 (נכשל: 400) | בקורפוס "Mekhilta DeRabbi Yishmael": en=CC0, **he=""** | NEEDS LAWYER | העברית ריקה ברישיון. יש להשלים את בדיקת "Mekhilta DeRabbi Yishmael" העברית לפני הכנסה. |
| אברבנאל על התורה | Sefaria API | https://www.sefaria.org/api/texts/Abarbanel_on_Torah,_Genesis.1.1?lang=he&context=0&commentary=0 | Hebrew: "Public Domain" (Warsaw 1862, NLI); English: "CC0" | USABLE | כבר בקורפוס. |
| חזקוני | Sefaria API | https://www.sefaria.org/api/texts/Chizkuni,_Genesis.1.1?lang=he&context=0&commentary=0 | Hebrew: "Public Domain" (source sefaria.org); English (Munk, Urim): "CC-BY" | USABLE | כבר בקורפוס (he=PD). |
| רשב"ם על התורה | Sefaria (כותרות קיימות) | https://www.sefaria.org/api/texts/Rashbam_on_Genesis.1.1 (נכשל: 400) | בקורפוס: he="daat" (לא אומת), en=CC0 | NEEDS LAWYER | הרישיון העברי תלוי בשם המקור "daat" שאינו מאומת. בדיקת דף Daat נדרשת. |
| ליקוטי מוהר"ן | Sefaria API | https://www.sefaria.org/api/texts/Likutei_Moharan.1.1?lang=he&context=0&commentary=0 | Hebrew (rabenubook.com): "Public Domain"; English (Mykoff): **"CC-BY-NC"**; English (Sefaria Community): "CC0" | USABLE (עברית בלבד) | כבר בקורפוס. **לא להשתמש בתרגום Mykoff (CC-BY-NC).** |
| ליקוטי תורה (Alter Rebbe) | לא נבדק | — | לא נבדק | NEEDS LAWYER | לא נמצא ב-`licenses.json`. לא נפתח שום מקור. |
| תורה אור | לא נבדק (ויקיטקסט "תורה_אור" → 404) | https://he.wikisource.org/wiki/תורה_אור (404) | לא נמצא | NEEDS LAWYER | לא נמצא בקורפוס וגם לא בעמוד ויקיטקסט שנפתח. נדרש מקור חלופי ובדיקת מהדורה. |
| שפת אמת (Sefat Emet) | Sefaria API | https://www.sefaria.org/api/v2/index/Sefat_Emet | לא נמצא בעמוד | USABLE | כבר בקורפוס: he=PD ("Piotrków, 1905-1908"), en=CC0. המחבר נפטר 1905. |
| נועם אלימלך | Sefaria (קיים בקורפוס) | לא נפתח עמוד API | בקורפוס: he=Public Domain ("Lvov, 1788") | USABLE | `licenses.json["Noam Elimelekh"]`. |
| קדושת לוי | Sefaria (קיים בקורפוס) | לא נפתח עמוד API | בקורפוס: he=Public Domain ("Munkatch 1939"), en=CC0 | USABLE | `licenses.json["Kedushat Levi"]`. |

**לא נעשה:** Project Ben-Yehuda, Open Siddur, Dicta/Library, Wikimedia Commons, HebrewBooks, Daat, Mechon Mamre, Al-Hatorah, HuggingFace datasets. לא נפתחו כדי לחסוך זמן מחקר. Dicta לא נבדק לאיכות; לפי זיכרון המשתמש יש לבדוק תגובות לפני כל ספר.

---

## 2. רשימת עדיפויות: 5 ספרים ראשונים לקליטה

הדירוג משלב ערך לשיעורי ישיבה וביטחון משפטי. רוב הפערים הם חלקיים, ולכן כל פריט מתחיל בבדיקה.

1. **הגהות הרמ"א על השולחן ערוך (Mapah).** ערך גבוה ביותר לשיעורי הלכה (רמ"א מכריע במנהג אשכנז). הפער מאומת בקורפוס. מקור ויקיטקסט נפתח והרישיון מוצהר CC-BY-SA, אבל שם הכותרת ב-Sefaria לא אומת, ודף ההגהות עצמו לא נפתח. **הצעד הראשון:** לאתר את הדף בוויקיטקסט ולבדוק שהטקסט מלא. ביטחון משפטי: NEEDS LAWYER עד שהטקסט נפתח.
2. **שך על אורח חיים (Siftei Kohen OC).** פער מאומת: הש"ך על יורה דעה וחושן משפט קיים, על אורח חיים לא נמצא. הרישיון העברי של המהדורה הקיימת PD. **הצעד הראשון:** לאתר את הכותרת ב-Sefaria או בוויקיטקסט.
3. **מאירי על ש"ס (Beit HaBechirah), בעיקר העברית.** 13 מסכתות קיימות באנגלית, אבל הרישיון העברי ריק בברכות ובשבת. זה מונע ניקוד בטוח. **הצעד הראשון:** לברר את שם הכותרת הנכון ב-Sefaria ולאמת את המהדורה העברית.
4. **מכילתא דרבי ישמעאל (עברית).** הכותרת קיימת באנגלית (CC0), אך העברית ריקה ברישיון. המכילתא חשובה לשיעורי תורה בלי תלות ב-Dicta. **הצעד הראשון:** לבדוק את Sefaria-Export או את העמוד בדף ה-JSON שלה.
5. **תורה אור ו-ליקוטי תורה (חסרים לחלוטין).** שניהם חסרים בקורפוס, ואין עדיין מקור מאומת. זה המקור הגדול הבא לביסוס, אם יימצא מקור PD עם רישיון ברור. יש לבדוק קודם את Sefaria (כותרות "Torah Or" ו-"Likutei Torah") ואת Hebrew Wikisource.

**הערה:** הרשימה לא כוללת ספרים שכבר בקורפוס עם רישיון PD מאומת (בית יוסף, טור, ט"ז, רבנו בחיי, הכוזרי, חובות הלבבות, דרך ה', שפת אמת, נועם אלימלך, קדושת לוי, מדרשי הרבות, אברבנאל, חזקוני).
