# Chavruta.AI — Master Plan

> חברותא וירטואלית מבוססת **RAG על כל ספריא**, דו-לשונית (עברית/אנגלית), מוגשת על
> **Nebius Serverless** וגם מסוגלת לרוץ **לגמרי offline** על מחשב מקומי.

מסמכים נלווים: [DECISIONS.md](DECISIONS.md) (החלטות טכניות) · [CORPUS.md](CORPUS.md) (היקף הטקסטים).

---

## 1. החזון
המשתמש שואל שאלה בתורה (עברית או אנגלית). המערכת **מאחזרת את המקורות הנכונים מספריא**,
ומודל שפה מנסח תשובה **מעוגנת, עם ציטוטים ו-deep-links** — בלי הזיות. כמו חברותא: מצטט
מקור, מסביר, ומפנה אותך פנימה.

**עיקרון יסוד:** הידע מגיע מ-**אחזור (RAG)**, לא מהמשקלים. אף מודל לא משנן את כל ספריא
בצורה אמינה. fine-tuning, אם בכלל, משמש רק ל*סגנון* — לא לידע.

---

## 2. התאמה לתחרות (Nebius Serverless AI Builders Challenge)
התחרות מתגמלת: **build something real · document clearly · share openly · become a
reference example** — ומעל הכל, להציג את **Nebius Serverless** ("run a job, serve a
model, pay only for what you use").

| מה התחרות רוצה | איך הפרויקט נותן |
|----------------|------------------|
| something real | חברותא עובדת על כל ספריא, עם ציטוטים |
| showcases Nebius | embedding job + serving + (אופ') training job — הכל serverless |
| reference example | RAG עברי פתוח ומתועד שכל בונה AI יהודי יחזור אליו |

**מסקנה אסטרטגית:** הליבה היא RAG. אימון כבד הוא הכיוון הלא נכון לתחרות הזו.

---

## 3. ארכיטקטורה — שש שכבות
```
[משתמש] שאלה (עברית/אנגלית)
   ▼
① Query        שכתוב/הרחבת שאלה, זיהוי הפניות
   ▼
② Retrieval    אחזור היברידי: וקטורי (bge-m3) + Sefaria Linker API + הרחבת קישורים
   ▼
③ Ranking      דמיון סמנטי + סיווג מקור ראשי/משני + רלוונטיות → top-K
   ▼
④ Generation   מודל מוגש (Nebius serverless / Ollama מקומי) מנסח מהמקורות
   ▼
⑤ Verify/Cite  בדיקת עיגון + ציטוטים + deep-links + שכבת בטיחות
   ▼
[תשובה + מקורות]

⑥ (אופציונלי) LoRA — כיוונון סגנון "רב" כ-Nebius training job
```
פירוט מלא של כל שכבה: ראה את גוף ה-README העתידי. ההחלטות הטכניות לכל שכבה: [DECISIONS.md](DECISIONS.md).

---

## 4. שני פרופילי הרצה (Deployment Profiles)
הליבה **אגנוסטית לפריסה** — מחליפים backend דרך config בלבד.

| רכיב | פרופיל ☁️ Nebius (תחרות, scale) | פרופיל 💻 Local (offline, כללי) |
|------|-------------------------------|-------------------------------|
| Embedding | bge-m3 (job/endpoint) | bge-m3 מקומי |
| Vector store | Qdrant server | Qdrant embedded |
| LLM | מודל גדול, serverless inference | Qwen קטן דרך Ollama |
| הפניות | Sefaria Linker API (online) | קישורים שהורדו מראש (offline) |

> דרישה #8: **כן — המערכת תרוץ לגמרי בלי אינטרנט.** כל הרכיבים בפרופיל המקומי רצים על
> ה-CPU/GPU שלך; הקורפוס והקישורים מורדים פעם אחת. הדבר היחיד שדורש רשת (Linker API)
> מוחלף ב-offline בקישורים מחושבים-מראש.

---

## 5. תמיכה דו-לשונית (דרישה #5)
- **אחזור:** bge-m3 רב-לשוני — שאלה בעברית מוצאת מקור עברי, שאלה באנגלית מוצאת תרגום.
- **גנרציה:** מודל רב-לשוני + prompt שעונה בשפת השאלה ומצטט מקור עברי.
- **קורפוס:** כל טקסט נשמר בעברית ובאנגלית (ספריא מספקת את שניהם).

---

## 6. מפת דרכים מדורגת (תמיד מערכת עובדת)
- **שלב 0 — בסיס:** ה-RAG הקיים (5 חומשים+רש"י+רמב"ן). החלפה ל-embedding עברי (bge-m3). → MVP עובד.
- **שלב 1 — אחזור חכם:** Sefaria Linker API + דירוג מקור ראשי/משני.
- **שלב 2 — הגשה על Nebius:** גנרציה דרך Nebius serverless inference. → ההדגמה המרכזית.
- **שלב 3 — הרחבת קורפוס:** תנ"ך מלא + המפרשים (ראה [CORPUS.md](CORPUS.md)).
- **שלב 4 — ליטוש לתחרות:** תיעוד, repo פתוח, נוטבוק משחזר, demo.
- **שלב 5 (אופ') — LoRA סגנון** כ-Nebius job.

---

## 7. מה ממחזרים מהקיים
- `data/processed/all_chunks.json` + לוגיקת chunking → קורפוס התחלתי.
- `src/rag_pipeline.py` → שלד שכבות 1–5.
- `app.py` (Streamlit) → ה-demo.
- ה-LoRA + הדאטהסט (`torah_mixed_*`) → רכיב הסגנון האופציונלי (שלב 5).

---

## 8. סטטוס החלטות
כל ההחלטות הגדולות נעולות ב-[DECISIONS.md](DECISIONS.md). היקף הטקסטים ב-[CORPUS.md](CORPUS.md).
