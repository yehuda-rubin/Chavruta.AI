# Chavruta.AI — Corpus Scope

היקף הטקסטים שהמערכת מאחזרת מהם. מקור: **Sefaria** (API + bulk export). כל טקסט נשמר
**בעברית ובאנגלית** (דרישה #5).

> **מצב נוכחי (עודכן 2026-06-29):** הקורפוס גדל מבסיס התנ"ך המאומת אל **כל ספריית Sefaria
> (14 קטגוריות)**. השליפה בצד שרת מתבצעת מ-**אינדקס Qdrant היברידי חי בן ~449k נקודות**
> (תנ"ך + משנה + תלמוד + שו"ת), וההלכה נטענת בהדרגה. ראה §0 ו-§6.

---

## 0. תמונת מצב — כל ספריית הבית מדרש

הטקסטים נמשכים מ-Sefaria דרך הסקריפטים `scripts/fetch_*.py`, מוטמעים ב-**Nebius GPU jobs**,
ומופצים כ-**מאגר Hugging Face לכל קטגוריה** (`chavruta-index-<slug>` — ראה
[memory: rag-index-distribution]). הטעינה ל-Qdrant היא תוספתית (verify → embed → upload → load)
ולא מוחקת את מה שכבר טעון.

| קטגוריה | מצב | היקף (משוער) |
|---------|-----|---------------|
| **תנ"ך** (Tanakh) | ✅ מוטמע ומאומת | 126,738 chunks (ראה §1–§2) |
| **משנה** (Mishnah) | ✅ נמשך + מוטמע | כל ששת הסדרים + מפרשים |
| **תלמוד בבלי** (Talmud) | ✅ נמשך + מוטמע (תיקון daf-shift) | כל הש"ס + רש"י/תוספות וכו' |
| **שו"ת** (Responsa) | ✅ נמשך + מוטמע | ~147K קטעים · 102 חיבורים |
| **הלכה** (Halacha) | ⏳ מוטמע, נטען בהדרגה | ~594,400 קטעים · 44 חלקים (שו"ע + מ"ב + …) |
| **מדרש, קבלה, מחשבה, ליטורגיקה, מוסר, דקדוק, ועוד** | ✅ נמשך (כל 14 הקטגוריות) | משתנה לפי קטגוריה |

> **קומנטרים מלאים:** תנ"ך/גמרא/משנה נמשכו מחדש עם **כל המפרשים שב-Sefaria**
> (`fetch_full_dynamic.py`) — פי ~2.5 מהמשיכה הראשונית.

---

## 1. כתבי הקודש — כל התנ"ך (24 ספרים) — הבסיס המאומת

| חלק | ספרים |
|-----|-------|
| **תורה** (5) | בראשית · שמות · ויקרא · במדבר · דברים |
| **נביאים** (8) | יהושע · שופטים · שמואל · מלכים · ישעיהו · ירמיהו · יחזקאל · תרי-עשר |
| **כתובים** (11) | תהילים · משלי · איוב · שיר השירים · רות · איכה · קהלת · אסתר · דניאל · עזרא-נחמיה · דברי הימים |

---

## 2. מפרשים ותרגומים (תנ"ך)

### תרגומים לארמית
| מפרש | כיסוי | הערה |
|------|-------|------|
| תרגום אונקלוס | תורה | התרגום הארמי הקלאסי |
| תרגום יונתן | נביאים | (וגם "יונתן" על התורה) |

### מפרשי הליבה
| מפרש | כיסוי עיקרי |
|------|-------------|
| רש"י | **כל התנ"ך** (תורה + רוב נ"ך) |
| רמב"ן | תורה (+ איוב) |
| אבן עזרא | תורה + חלקים נרחבים מנ"ך |
| בעל הטורים | תורה |
| ספורנו | תורה |
| **רשב"ם** | תורה — פשט קלאסי, משלים את רש"י |
| **אור החיים** | תורה — עומק ודרש |
| **רד"ק** | **נביאים + כתובים** (+תורה) — ⭐ המפרש המרכזי לנ"ך |
| **מלבי"ם** | **כל התנ"ך** (בעיקר נ"ך) |
| **מצודת דוד / ציון** | **נביאים + כתובים** — הפירוש הסטנדרטי ללימוד נ"ך |

כך מתקבל כיסוי מלא: רש"י/רשב"ם/אבן-עזרא/רמב"ן/ספורנו/בעה"ט/אוה"ח לתורה, ורד"ק/מצודות/מלבי"ם/רש"י לנ"ך.

---

## 3. זמינות ב-Sefaria ושליפה
- **Texts API** — `GET /api/v3/texts/{ref}` → טקסט עברי+אנגלי לכל הפניה.
- **Links API / Linker** — קישורים והפניות בין מקורות (לשכבת האחזור והרחבת הקישורים).
- **Bulk export** — מאגר Sefaria-Export (GitHub) להורדה חד-פעמית → תומך בפרופיל ה-offline (#8).
- כיסוי משתנה: לא לכל פסוק/קטע יש כל מפרש (למשל ספורנו/אוה"ח = תורה בלבד). זה תקין — מאחזרים מה שקיים.

---

## 4. היקף (Scale)

| | תנ"ך (מאומת) | כלל הבית מדרש |
|---|---|---|
| פסוקים/קטעי-בסיס | 23,206 | מאות אלפים (לפי קטגוריה) |
| chunks | **126,738** | ההלכה לבדה ~594K; אינדקס חי ~449K נקודות |

הטמעת קורפוס בסדר גודל כזה = **Nebius embedding job** (חד-פעמי, pay-per-use) לכל קטגוריה.
מקומית ניתן להטמיע בהדרגה (קטגוריה-קטגוריה) על ה-CPU.

---

## 5. סקריפטי משיכה (scripts/)
- `fetch_corpus.py` — תנ"ך (הבסיס).
- `fetch_full_dynamic.py` — משיכה מחדש עם **כל** המפרשים של Sefaria (תנ"ך/גמרא/משנה).
- `fetch_category.py` — משיכת קטגוריה שלמה (כל 14 הקטגוריות).
- `fetch_mishnah.py` · `fetch_gemara.py` · `fetch_halacha.py` · `fetch_shut.py` — משיכות ייעודיות.
- `fix_daf_shift.py` — תיקון היסט הדף בתלמוד.

---

## 6. הפצה וטעינה (RAG Index Distribution)
1. לכל קטגוריה נבנה **מאגר HF נפרד** `chavruta-index-<slug>` (vectors + payload).
2. תהליך: **verify → embed (Nebius GPU) → upload (HF) → load (Qdrant server)**.
3. הטעינה תוספתית — לא מוחקת את מה שכבר באינדקס.
4. מדריך מלא לדוגמת ההלכה (בלי Docker): [NEBIUS_HALACHA_JOB.md](NEBIUS_HALACHA_JOB.md).

### מאגרי ה-HF (namespace: [🤗 Yehuda-Rubin](https://huggingface.co/Yehuda-Rubin))

אינדקסים מוכנים (datasets) — לטעינה ל-Qdrant ללא הטמעה מחדש:

| slug | מאגר |
|------|------|
| tanakh | [chavruta-index-tanakh](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-tanakh) |
| mishnah | [chavruta-index-mishnah](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-mishnah) |
| gemara | [chavruta-index-gemara](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-gemara) |
| shut | [chavruta-index-shut](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-shut) |
| halacha | [chavruta-index-halacha](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-halacha) |
| midrash | [chavruta-index-midrash](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-midrash) |
| kabbalah | [chavruta-index-kabbalah](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-kabbalah) |
| musar | [chavruta-index-musar](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-musar) |
| liturgy | [chavruta-index-liturgy](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-liturgy) |
| jewish_thought | [chavruta-index-jewish_thought](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-jewish_thought) |
| chasidut | [chavruta-index-chasidut](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-chasidut) |
| tosefta | [chavruta-index-tosefta](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-tosefta) |
| reference | [chavruta-index-reference](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-reference) |
| second_temple | [chavruta-index-second_temple](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-second_temple) |

**דאטה לאימון LoRA:** [chavruta-torah-mixed](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-torah-mixed).
