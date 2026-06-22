# תוכנית עבודה — שיעורים מבוססי-תבניות (Lesson Templates RAG)

**יעד:** שיעור ייבנה כ**קשת לימודית** — פתיחה ממקור הסוגיא → הסתעפות לכמה כיווני
חשיבה/דעות → התכנסות למסקנות/פסק (או נשאר פתוח) — באמצעות **קורפוס תבניות קטן**
(RAG שני) שמספק את ה**שלד**, שממולא ב**מקורות מעוגנים** מהקורפוס הראשי הקיים.

נגזר מ-[FOLLOWUPS.md #2](../FOLLOWUPS.md). מבוסס על ניתוח מבנה שיעורים אמיתיים
(עולמות / כרם ביבנה) — **רק הדפוס המבני, ללא העתקת תוכן מוגן**.

> **סטטוס:** Phase 1–3 **בוצעו** (95 טסטים עוברים).
> - **P1:** 4 תבניות + סכמה + אחזור-לפי-נושא
>   ([templates.py](../../src/chavruta/lessons/templates.py), [YAML](../../data/lesson_templates.yaml)).
> - **P2:** `build_lesson_from_template` ([builder.py](../../src/chavruta/lessons/builder.py)) —
>   ממפה hits לקשת (opening→branches→convergence), `is_open` לסוגיא פתוחה; שדות `role`/`template_id`/`is_open` ב-schema.
> - **P3:** חיווט ב-[pipeline.ask](../../src/chavruta/pipeline/pipeline.py) — LESSON בונה שיעור מתבנית (fallback לישן).
>
> נותר: **P4** אחזור מודע-שלב (דורש backend חי), **P5** בחירת-תבנית ע"י ה-LLM planner, **P6** סט-הערכה לשיעורים.

---

## הרקע (המצב כיום)
`build_lesson_plan` ([grounded.py](../../src/chavruta/generation/grounded.py)) מקבץ את
ה-hits לפי עוגן ומחזיר סקשנים שטוחים (פסוק + מפרשיו לכל עוגן). **אין קשת** — אין פתיחה,
אין הסתעפות מכוונת, אין התכנסות. השיעור מרגיש כרשימת-מקורות, לא כסוגיא נמסרת.

## העיקרון (שני RAG-ים)
1. **קורפוס תבניות** (קטן, ~עשרות): כל תבנית = שלד מבני מופשט (כתוב במילים שלנו).
   נאחזר ממנו לפי הנושא.
2. **זרימת "אחזור-שלד ואז עיגון-תוכן":**
   `סיווג נושא → אחזור התבנית המתאימה → מילוי כל שלב במקורות מעוגנים מהקורפוס הראשי
   (עם query-understanding + LinkExpander) → גנרציה לפי הקשת`.

זה מנצל את כל מה שכבר נבנה (Qdrant, hybrid, anchoring, LinkExpander, Phase 5 planner)
ומוסיף רק שכבת-שלד. עקרון העיגון נשמר: השלד מנחה, אבל כל **תוכן** מצוטט מהמקורות שלנו.

## עמדת זכויות יוצרים
התבניות נכתבות כ**הפשטה מבנית מקורית** (גוזרים את הדפוס מדוגמאות — לא מעתיקים ניסוח).
שום טקסט מוגן של עולמות/כרם-ביבנה לא נכנס לקורפוס. אם בעתיד נרצה תוכן בפועל — מסלול
רישוי נפרד (פנייה לבעלי האתרים).

---

## מודל הנתונים (Template)
קובץ נתונים `data/lesson_templates.yaml` (הרחבה קלה — data/config):
```yaml
- template_id: halachic_sugya
  name_he: "סוגיא הלכתית"
  when_to_use: "שאלת 'מה הדין' / בירור הלכה מהמקורות ועד הפסיקה"   # מוטמע לאחזור
  stages:
    - key: opening      ; title_he: "פתיחה — מקור הסוגיא"  ; source_kinds: [pasuk, mishnah, gemara]
    - key: branch       ; title_he: "שיטות הראשונים"        ; source_kinds: [rishonim]
    - key: branch       ; title_he: "דיון האחרונים"          ; source_kinds: [acharonim]
    - key: convergence  ; title_he: "להלכה"                  ; source_kinds: [pesak, shulchan_aruch]
```
סוגי-שלבים: `opening` (יחיד) · `branch` (כמה) · `convergence` (אחד או כלום — סוגיא פתוחה).

## שינויי סכמה
[schema.py](../../src/chavruta/corpus/schema.py): להוסיף ל-`LessonSection` שדה
`role: str` (`opening|branch|convergence`) ול-`LessonPlan` שדה `template_id` ו-`is_open: bool`
(סוגיא שלא מתכנסת).

---

## שלבים

### Phase 1 — קורפוס תבניות + אחזור (in-memory)
- `chavruta/lessons/templates.py` (חדש): סכמת `Template`/`Stage`, טעינה מ-YAML, ואחזור
  `select_template(topic, embedding) -> Template` (cosine מעל `when_to_use`; N קטן → brute-force).
- `data/lesson_templates.yaml`: **5–6 תבניות זרועות** (ראו למטה).
- טסטים: טעינה, בחירת-תבנית נכונה לפי נושא (עם embedding מזויף מ-conftest).

### Phase 2 — בונה-שיעור מבוסס-תבנית
- `build_lesson_from_template(topic, template, hits) -> LessonPlan` שמסדר את ה-hits
  לשלבי הקשת לפי `source_kinds` (פתיחה=עוגן/פסוק; הסתעפות=ראשונים/דעות; התכנסות=אחרונים/פסק).
- שלבים ריקים → או מושמטים, או מסומנים כ"לא נמצא מקור" (עיגון כן). `is_open=True` אם אין convergence.
- טסטים: hits לדוגמה → LessonPlan עם opening/branch/convergence ו-citations בכל שלב.

### Phase 3 — חיווט ל-pipeline (מסלול LESSON)
- ב-[pipeline.ask](../../src/chavruta/pipeline/pipeline.py): עבור `Intent.LESSON` →
  `select_template` → `build_lesson_from_template`. במקום `build_lesson_plan` הישן (לשמור fallback).
- ה-`opening` משתמש ב-`named_refs`/anchor מ-query-understanding כדי לפתוח **בדיוק במקור הסוגיא**.

### Phase 4 — אחזור מודע-שלב
- לכל שלב לאחזר ממוקד: פתיחה→fetch_by_refs על העוגן; הסתעפות→LinkExpander (מפרשים/דעות);
  התכנסות→אחרונים/פסק (כשייטען קורפוס הלכה). מנצל Phase 4 של ספק 002 (גרף הקישורים).

### Phase 5 — בחירת-תבנית חכמה (אופציונלי)
- ה-LLM planner (ספק 002 Phase 5) מסווג נושא→`type` כשהאחזור הסמנטי לא חד-משמעי.

### Phase 6 — מדידה
- `tests/eval/lessons.jsonl`: כמה נושאים → לוודא שהקשת כוללת opening+≥1 branch, וש-convergence
  קיים/`is_open` מסומן, וש**כל שלב מעוגן**. שער-רגרסיה כמו ב-002.
- (אם קורפוס-התבניות יגדל — להעביר ל-collection שני ב-Qdrant `lesson_templates`.)

---

## תבניות לזריעה (Phase 1)
| type | מתי | קשת |
|------|-----|-----|
| `halachic_sugya` | "מה הדין" | פסוק/גמרא → ראשונים → אחרונים → פסק |
| `machloket_rishonim` | מחלוקת מפרשים על פסוק | פסוק → שיטה א' → שיטה ב' → נפק"מ/הכרעה |
| `talmudic_sugya` | סוגיית גמרא | משנה → שקלא-וטריא → אביי/רבא → מסקנת הסוגיא (לעיתים פתוח) |
| `parsha_iyun` | עיון בפרשה | פסוק → פשט (רש"י/ראב"ע) → דרש/רמב"ן → רעיון מרכזי |
| `machshava_mussar` | מחשבה/מוסר | מקור → שאלה/קושי → כיווני הסבר → מסר |

## הגדרת "בוצע"
שאלת "הכן שיעור על שניים אוחזין" מחזירה `LessonPlan` עם **פתיחה** (ב"מ ב' ע"א),
**≥2 הסתעפויות** מעוגנות (רש"י/תוס'/רמב"ם), ו**התכנסות** (או `is_open`), כל שלב עם ציטוטים.

## שאלות פתוחות
- כמה תבניות באמת צריך? (מתחילים ב-5–6, מרחיבים לפי צורך.)
- האם להטמיע גם את שמות-השלבים בעברית כברירת-מחדל לפלט, או לתת ל-LLM לנסח כותרות.
- מתי להפעיל `is_open` (סוגיא שלא נפסקת) — לפי ה-type או לפי תוכן האחזור.
