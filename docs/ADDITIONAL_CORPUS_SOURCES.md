# מקורות קורפוס נוספים — מחקר רישיונות (לא מורשה לקוד)

**תאריך:** 2026-10-27
**היקף:** מחקר בלבד. לא שונה קוד, נתונים או הגדרות. נוצר קובץ זה בלבד.
**כלל:** המוצר בתשלום, לכן מותר רק PD / CC0 / CC-BY / CC-BY-SA. NC, all-rights-reserved ו-"unknown" נחשבים אסורים.
**כללי הפסיקה:** USABLE = רישיון נקרא מהדף עצמו ומתאים לכלל. NEEDS LAWYER = רישיון לא ברור, או מהדורה מודרנית שייתכן שהיא מוגנת. NO = רישיון לא מתאים, לא נקרא, או לא נמצא.
**"לא אומת"** = לא נפתח הדף, או הדף לא החזיר את התוכן הנדרש. לא נטען רישיון מזיכרון.

---

## 0. ממצאים עיקריים

1. **רוב הפערים אינם דורשים מקור חדש.** בטבלת `docs/LOADED_VS_LICENSED.md` יש כותרות שמופיעות כ"מורשות ולא טעונות", כלומר כבר מותרות ב-Sefaria וטרם נטענו: **Abarbanel על הנביאים (15)**, **Meiri (11)**, **Mekhilta DeRabbi Yishmael (1)**, **Duties of the Heart (1)**, **Kuzari (1)**. ההחלטה למשוך אותן היא עניין של צינור הטעינה, לא של מקור חיצוני. **נוסף:** הטבלה מסמנת את Kuzari כ"לא נטען", אבל `docs/MISSING_BOOKS_SOURCING.md` כותב שהוא "כבר בקורפוס (PD)". יש סתירה שצריך לפתור לפני פעולה.
2. **לא נמצא מאגר עברי רחב שמתאים לכלל.** Otzaria (קוד עם רישיון אישי בלבד, וספרייה עם זכויות שמורות בחלק), Al-HaTorah, Daat, Dicta, Bar-Ilan ו-Torat Emet — כולם NO.
3. **Project Ben-Yehuda** הוא המועמד היחיד עם טקסט עברי מלא ו-dump נגיש. אבל האתר לא נותן רישיון, והדאמפ נושא רק הצהרה של המעלה ("כל היצירות בנחלת הכלל"). לכן NEEDS LAWYER.
4. **הדאמפ של Sefaria-Export** מתאים לכלל רק לפי השדה `license` של כל טקסט (ראו §1). **HF `mehdie/sefaria` הוא עותק של אותו מקור** ואינו מוסיף כלום.

---

## 1. הטבלה

| מאגר | מה יכול להיכנס לקורפוס | כתובת שנפתחה בפועל | ציטוט רישיון (מילולי מהדף) | פסיקה | איך להוריד |
|---|---|---|---|---|---|
| **Project Ben-Yehuda** (אתר) | טקסטים עבריים מלאים של מחברים רבים (כולל ספרות ישראלית). מעט מאוד מהם תורניים; הערכה לגבי כיסוי הספרים החסרים: **לא אומת** | https://benyehuda.org/page/license (נפתח, אין בו רישיון) | אין רישיון באתר. נאמר רק: "אנו מתחייבים שאתר הפרויקט לעולם יישאר חופשי בשימוש ונקי מפרסומות." ליד מחברים מופיע התיוג "נחלת הכלל", וגם "יצירות מסוימות מונגשות ברשות" עם ההסבר "רשות לכותרים מסוימים בלבד". באחד הביוגרפיות: "זכויות היוצרים שלו עודן בתוקף". | **NEEDS LAWYER** | אין API מתועד. הדאמפ מופיע ב-HF (ראו שורה הבאה). לא נמצא GitHub רשמי: https://github.com/benyehuda-org נפתח והחזיר 404. |
| **Project Ben-Yehuda — דאמפ HF** (`hebrew_projectbenyehuda`) | כ-10,078 קבצי טקסט פשוט UTF-8 (עם ובלי ניקוד) ומטא-דאטה של כותרים, מחברים וז'אנרים (CSV). מכיל ספרות כללית, לא ממוקד בתורה | https://tensorflow.google.cn/datasets/community_catalog/huggingface/hebrew_projectbenyehuda (נפתח; הקישור ל-HF: https://huggingface.co/datasets/hebrew_projectbenyehuda — לא נפתח) | "All these works are in the public domain, so you are free to make any use of them, and do not need to ask for permission." רישיון במטא-דאטה: "无已知许可" (אין רישיון ידוע). | **NEEDS LAWYER** — הצהרת מעלה בלבד, לא רישיון. נדרשת בדיקה לכל מחבר לפי תאריך פטירה | `datasets.load_dataset("hebrew_projectbenyehuda")` מ-HF, או הורדה ישירה מה-HF. |
| **Sefaria-Export** (GitHub / bucket `gs://sefaria-export/`) | כל טקסטי Sefaria בפורמטי JSON, TXT ו-CLTK. כבר נמשך ומשמש את הקורפוס | https://github.com/Sefaria/Sefaria-Export (נפתח); https://raw.githubusercontent.com/Sefaria/Sefaria-Export/master/LICENSE.md (נפתח) | "Each text is licensed separately, so there is no overall license for this repository." / "You can find the license for each text in their JSON versions under the `license` field." / "This is generally either "Public Domain", "CC0", "CC-BY", "CC-BY-SA" or "CC-BY-NC"." | **USABLE** לפי השדה `license` של כל טקסט בלבד. מי שמושך את הכותרים החסרים מ-Sefaria צריך לסנן לפי השדה, לא לפי שם הספר | `git clone` או `gsutil` מהדלי; קובץ JSON לכל כותרת. |
| **Mechon Mamre** (mechon-mamre.org) | תנ"ך ורמב"ם מנוקדים, ללא מפרשים מלאים | https://www.mechon-mamre.org/ (נפתח; אין בו טקסט זכויות). https://www.mechon-mamre.org/copyright.htm — **403** | **לא אומת** מהמקור. הערה שמצוטטת בתיעוד הריפו (`docs/CORPUS_SOURCES_CANDIDATES.md`, שורה 168): "מותר רק ל'לימוד פרטי והוראה', אסור לפרסם בשום צורה כולל אתר". לא נקרא בסבב הזה. | **NO** (לפי הציטוט שנרשם בריפו, אם הוא נכון — אסור לפרסם. לא אומת) | לא רלוונטי כרגע. |
| **Open Siddur Project** (opensiddur.org, GitHub `opensiddur/opensiddur`) | ליטורגיה (הגדות, סידורים, ברכונים) בפורמט TEI XML. **לא תורה / הלכה / מפרשים** — לא מכסה אף פער מהרשימה | https://www.opensiddur.org/ (נפתח); https://github.com/opensiddur/opensiddur (נפתח) | לא נקרא טקסט הרישיון. ב-repo מופיעים קבצים בשם: CC-BY, CC-BY-SA, CC0, GPL-3, LGPL-3, PERMISSIVE. **לא אומת** איזה רישיון חל על איזה טקסט. | **NO** (לא רלוונטי לפערים; לא אומת) | — |
| **Wikimedia Commons** | תמונות וסריקות, לא טקסט תורני מסודר | https://commons.wikimedia.org/wiki/Commons:Licensing (נפתח) | "Media licensed exclusively under non-commercial only licenses (like CC BY-NC-SA) are not accepted either." ו-"non-commercial and/or non-derivative content cannot be uploaded to Wikimedia Commons." מקובלים: "Material released under a license like CC0 is considered the equivalent of public domain material". | **USABLE** למדיה בלבד (PD / CC0 / CC-BY / CC-BY-SA). לא מקור טקסט לפערים | Commons API או הורדה ישירה לפי קובץ. |
| **Hebrew Wikisource (מכילתא)** | מכילתא דרבי ישמעאל (הכותרת החסרה ב-Sefaria HE) | https://he.wikisource.org/wiki/מכילתא_דרבי_ישמעאל (נפתח) | בתחתית העמוד: "Creative Commons ייחוס-שיתוף זהה 4.0" ו"additional terms may apply". העמוד מסומן "לא נבדק". הנוסח: מהדורת Horovitz-Rabin עם ניקוד של הרב דן ברי (מודרני). | **NEEDS LAWYER** — הטקסט הקלאסי PD, אבל ניקוד ועריכה מודרניים אולי מוגנים. דרושה בדיקה לפי מהדורה | ויקיטקסט: API של MediaWiki, או ייצוא דרך `action=query` לעמוד. |
| **Internet Archive (archive.org)** | סריקות של מהדורות ישנות. ייתכן OCR | https://archive.org/about/terms.php (נפתח; החזיר רק כותרת — **לא אומת**). https://archive.org/advancedsearch.php?q=mekilta+AND+mediatype%3Atexts (נפתח, JSON). | לא נקרא ציטוט רישיון. בחיפוש "mekilta" נמצאו 12 פריטים באנגלית (למשל `mekiltaderabbiis0001unse`, 1976) — **לא נמצאה מהדורת פרידמן 1870 (לא אומת)**. ב-JSON לא הוחזר שדה `licenseurl`. | **NEEDS LAWYER** — בדיקה לכל פריט בנפרד (תאריך פרסום, שדה rights, ומהדורה) | `https://archive.org/advancedsearch.php?...&output=json` לרשימה; `https://archive.org/download/<id>/<id>_djvu.txt` לטקסט OCR. |
| **HathiTrust** | סריקות ציבוריות + OCR | https://www.hathitrust.org/terms-of-use — **403** | **לא אומת** | **NO** (לא אומת) | — |
| **National Library of Israel** (ספרייה דיגיטלית) | סריקות ישנות | https://www.nli.org.il/en/copyright — **403**; https://www.nli.org.il/he/copyright — **403** | **לא אומת** | **NO** (לא אומת) | — |
| **Daat (דעת, הרצוג)** | דף אחד מכיל לימוד ומאמרים; לא נמצא טקסט מלא מצוטט | https://www.daat.ac.il/ (נפתח חלקית; גוף המאמר לא הוחזר) | "© 2010". אין טקסט תנאי שימוש (קישורים למדיניות פרטיות ונגישות בלבד, שלא נפתחו). | **NO** (אין רישיון; "unknown" = אסור לפי `rights.py`) | — |
| **Torat Emet** (תורת אמת) | לא אומת | https://www.toratemet.org/ נפתח — **אתר של קהילה, לא של תורת אמת**. הדומיין הנכון לא אותר בחיפוש. | **לא אומת.** בדף Wikisource משנת 2006 (שלא נחשב מקור מחייב) מופיע שטקסט מסוים "נחשב PD" — לא נאמת. | **NO** (לא אומת) | — |
| **Al-HaTorah** | מקורות תורניים רבים: מקראות גדולות, משנה, תוספתא, רי"ף, טור, שולחן ערוך, רמב"ם | https://www.alhatorah.org/ (נפתח) | "© 2011–2026 ALHATORAH.ORG". "Terms of Use" מופיע בתפריט אך טקסטו לא הוחזר. אין הצהרת רישיון בדף. | **NO** (copyright שמור לאתר; אין רישיון לתוכן) | — |
| **Otzaria** (GitHub `Otzaria/otzaria`; ספרייה `SeforimLibrary`) | ספרייה גדולה של קבצי TXT (מתוך Sefaria, Dicta, Orayta, Tora.ws, תורת אמת, הספרייה הלאומית, ויקיטקסט ועוד) | https://github.com/Otzaria/otzaria (נפתח; הקישור לספרייה: github.com/Otzaria/SeforimLibrary/releases — לא נפתח) | קוד הפרויקט: "Personal Use License 1.0 — שימוש אישי בלבד" ו"אסור כל שימוש ציבורי — בין מסחרי ובין במסגרת תוכנה חינמית/קוד פתוח — ללא רשות מפורשת בכתב". ספרים מסוימים: "Machon Beit Aharon VeYisrael, whose rights are reserved." | **NO** (רישיון אישי בלבד, ו"rights are reserved" בחלק מהספרים) | — |
| **Dicta** (Library, Nakdan, מודלים) | טקסטים מנוקדים ומתויגים; בנוסף מודלי LM | לא נפתח דף רישיון. נמצא דרך חיפוש בלבד: `dicta-il/dictalm2.0-quant-calib-dataset` עם `odc-by`; DictaLM 3.0 — "commercial rights for that data are unclear" (מתוך מאמר arXiv שנמצא בחיפוש) | לא נקרא רישיון לספריית הטקסטים | **NO** (לפי הכלל שבפרויקט: Dicta לא נכנס כשהרישיון לא ברור; איכות בעייתית: ראו `docs/CORPUS_SOURCES_CANDIDATES.md` §7.3) | — |
| **Bar-Ilan Responsa Project** | שו"ת מסוגים רבים | https://www.biu.ac.il/en/responsa-project — **404**. הוצג דרך חיפוש בלבד. | לא נמצא רישיון רשמי. רישיון של מנוי באוניברסיטה אחרת (לא של בר-אילן) אומר: "It is strictly forbidden to change, rewrite, systematically copy, redistribute, sell, publish or in any way use the material in commercial purposes." | **NO** | — |
| **HebrewBooks** (hebrewbooks.org) | סריקות רבות של ספרים עבריים ישנים | https://hebrewbooks.org/ — **403** | **לא אומת** | **NO** (לא אומת) | — |
| **Machon Yerushalayim / Mossad HaRav Kook** (מהדורות מודרניות) | מהדורות מדויקות של ספרים קלאסיים (למשל שולחן ערוך, תורת חיים) | חיפוש בלבד; אתרי המוסדות לא נפתחו | לא נמצא בחיפוש שום הצהרת רישיון. | **NEEDS LAWYER** — מהדורה מודרנית מוגנת לפי ההלכה במדינה; הטקסט הקלאסי PD | — |
| **Hugging Face `mehdie/sefaria`** | עותק של Sefaria export | https://huggingface.co/datasets/mehdie/sefaria (נפתח; viewer נכשל) | license: "cc-by-4.0". "This Dataset is a Hugging Face interface to the Sefaria database export". אין הצהרה על רישיון לטקסטים בודדים. | **NO** (כפילות של Sefaria-Export; תג CC-BY-4.0 לא גובר על הרישיון של כל טקסט) | — |
| **Hugging Face `NuBerea/jastrow-lexicon`** | מילון ג'סטרו (ארמית וכו'). **מילון, לא טקסט** — לא ממלא פער | https://huggingface.co/datasets/NuBerea/jastrow-lexicon (נפתח) | license: "cc-by-4.0". המקור: "complete Public-Domain ingest" של המילון (London/New York 1903). תנאי גישה: "you have to accept the conditions to access its files and content." | **USABLE** למילון בלבד (לא פער). דורש קבלת תנאים ב-HF | HF parquet, אחרי אישור. |
| **Hugging Face — Otzaria embedding** | מודל, לא טקסט | לא נפתח; מופיע בחיפוש | לפי תיאור החיפוש: שימוש אישי / אקדמי / לא מסחרי בלבד | **NO** | — |
| **chaver.com — Mishnah JSON (Zenodo DOI 10.5281/zenodo.20179532)** | המשנה המלאה, 524 פרקים, JSON. **המשנה כבר בקורפוס (PD)** — לא פער | https://chaver.com/Mishnah-New/Hebrew/Text/mishnah-data (נפתח). הקובץ: https://chaver.com/Mishnah-New/English/mishnah_db.json | "The dataset is released under a Creative Commons Attribution license (CC-BY)." | **USABLE** (אין פער; ייחוס נדרש). אפשרות להשוואה מבנית מול הקורפוס | הורדה ישירה מהקישור או מ-Zenodo. |
| **Kaggle** | לא נמצא דאטהסט תורני עברי בחיפוש | לא נפתח אתר Kaggle; חיפוש בלבד | לא נמצא | **לא אומת** | — |

---

## 2. חמש הצעדים הבאים (לפי הסבירות להשלמת פערים)

הפערים מהבקשה מופיעים לפי הטבלה `docs/LOADED_VS_LICENSED.md`. "מורשה ולא נטען" = כבר מותר ב-Sefaria, צריך רק למשוך.

1. **למשוך את הכותרים המורשים שטרם נטענו (לא מקור חדש).**
   - **Abarbanel על הנביאים (15 כותרים: Amos, Ezekiel, Hosea, Kings, Samuel, Isaiah, Jeremiah, Joel, Jonah, Joshua, Judges, Obadiah, Zechariah ועוד)** — מחבר נפטר 1508, PD. רישיון ב-Sefaria מורשה.
   - **Meiri (11 כותרים: Avodah Zarah, Bava Kamma, Bava Metzia, Berakhot, Pesachim, Rosh Hashanah, Sanhedrin, Shabbat, Sotah, Yevamot, Yoma)** — הטבלה מסמנת כמורשים.
   - **Duties of the Heart (1)**, **Kuzari (1, לבדוק סתירה)**, **Mekhilta DeRabbi Yishmael (1)**.
   - פעולה: `notebooks/fetch_licensed_kaggle.ipynb` או סקריפט דומה, עם בדיקת `license` לכל כותר לפני טעינה.

2. **Mekhilta DeRabbi Yishmael בעברית — לאמת את המקור.** הטבלה מסמנת אותו כמורשה, אבל `docs/MISSING_BOOKS_SOURCING.md` כותב שבעברית הרישיון ב-Sefaria ריק. לפני טעינה: לאתר מהדורת פרידמן 1870 (מחבר נפטר לפני 1956 → PD) בסריקה ב-Internet Archive או HebrewBooks, ולבדוק את שדה ה-rights של הפריט. **לא אומת** שפרידמן זמין בשום מאגר פתוח.

3. **הגהות הרמ"א (Mapah) — לפתוח את עמוד ויקיטקסט.** ב-Sefaria ה-Mapah מאופס (0 מורשים). הרמ"א נפטר 1572 → הטקסט PD. ויקיטקסט העברי מציין CC-BY-SA, אבל לא פתחנו את עמוד ההגהות ולכן לא ידוע שהוא מלא. **NEEDS LAWYER** עד שהעמוד נפתח ומוודא שהמהדורה אינה מודרנית.

4. **שך על אורח חיים (Siftei Kohen OC), Maharal, Radak — סריקות של מחברים קדמונים.** בטבלה: Siftei Kohen מופיע רק על יורה דעה וחושן משפט; Maharal בעשרה כותרים מורשים בלבד (5 טעונים, 0 חסרים). המחברים PD (שך נפטר 1662, מהר"ל 1609, רד"ק 1235). **המאגר המועמד: Internet Archive או HebrewBooks — לא נפתח.** כל פריט דורש בדיקת rights נפרדת.

5. **Ben-Yehuda — לבדוק לפי מחבר, לא לפי האתר.** הדאמפ ב-HF הוא המקור היחיד שנמצא עם טקסט עברי מלא ב-dump אחד. צריך לוודא (א) שכל טקסט הוא של מחבר שנפטר לפני 1956 (הכלל הישראלי: life + 70), ו-(ב) שהטקסט לא עבר עריכה מודרנית. **NEEDS LAWYER** עד שהבדיקה נעשית. לא נמצא בו ספר מן הפערים; הכיסוי התורני לא אומת.

---

## 3. מה לא נבדק (ומה נדרש כדי לסגור)

- **Mechon Mamre**: נדרש לפתוח את דף הזכויות האמיתי (לא נפתח; 403). עד אז הציטוט מהריפו לא מאומת.
- **HathiTrust, NLI, HebrewBooks, Torat Emet, Kaggle**: לא נפתחו דפי הרישיון (403, דומיין שגוי, או לא נפתח). דרוש פתיחה ישירה.
- **Internet Archive**: לא נמצאה מהדורת פרידמן 1870 בחיפוש. נדרש חיפוש לפי מזהה ובדיקת rights לכל פריט.
- **Ben-Yehuda HF**: לא נבדק שהדאמפ מכיל את הכותרים הספציפיים מן הפערים.
- **Machon Yerushalayim / Mossad HaRav Kook**: לא נמצא רישיון מודרני לאף מהדורה.
- **זיכרון**: אף רישיון כאן לא נטען מזיכרון. כל ציטוט מסומן במקור שממנו נלקח. תאריכי הפטירה שמוזכרים בשלבים (אבר בנאל 1508, רמ"א 1572, שך 1662, מהר"ל 1609, רד"ק 1235, מייר 1315) הם מידע כללי ולא אומתו מהמקורות בסבב הזה; לפני כל שימוש הם צריכים אימות.
